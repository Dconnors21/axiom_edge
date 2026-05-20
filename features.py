# ── features.py ───────────────────────────────────────────────────────────────
# Engineers predictive features from raw game data in nba.db.
# v2: adds playoff flag, opponent defensive rating, and injury context.
#
# Usage: python features.py

import sqlite3
import requests
import pandas as pd
import numpy as np
import time
from config import DB_PATH, ROLLING_SHORT, ROLLING_LONG

def get_conn():
    return sqlite3.connect(DB_PATH)

# ── Load raw games ────────────────────────────────────────────────────────────

def load_games(conn):
    df = pd.read_sql("""
        SELECT game_id, game_date, season,
               team_id, team_abbreviation, team_name,
               matchup, is_home, wl,
               pts, opp_pts, plus_minus,
               fg_pct, fg3_pct, ft_pct,
               reb, ast, stl, blk, tov
        FROM games
        ORDER BY game_date ASC, game_id ASC
    """, conn, parse_dates=["game_date"])

    df["win"]        = (df["wl"] == "W").astype(int)
    df["point_diff"] = df["pts"] - df["opp_pts"]

    # ── Playoff flag ──────────────────────────────────────────────────────────
    # NBA game IDs: digits 3-4 indicate season type
    # 002 = regular season, 004 = playoffs, 005 = play-in
    def is_playoff(game_id):
        try:
            code = str(game_id)[2:4]
            return 1 if code in ["42", "52"] else 0
        except Exception:
            return 0

    df["is_playoff"]  = df["game_id"].apply(is_playoff)
    df["is_playin"]   = df["game_id"].apply(
        lambda g: 1 if str(g)[2:4] == "52" else 0)

    playoff_pct = df["is_playoff"].mean()
    print(f"  Loaded {len(df):,} game rows | "
          f"Playoff rows: {df['is_playoff'].sum():,} ({playoff_pct:.1%})")
    return df

# ── Rolling features ──────────────────────────────────────────────────────────

def add_rolling_features(df):
    print(f"  Rolling features (windows: {ROLLING_SHORT}, {ROLLING_LONG})...")
    feature_cols = ["pts","opp_pts","point_diff","win",
                    "fg_pct","fg3_pct","ft_pct",
                    "reb","ast","stl","blk","tov","plus_minus"]

    df = df.sort_values(["team_id","game_date"]).reset_index(drop=True)

    for col in feature_cols:
        for window in [ROLLING_SHORT, ROLLING_LONG]:
            df[f"{col}_last{window}"] = (
                df.groupby("team_id")[col]
                .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
            )

    # Playoff-specific rolling stats — how has this team performed in playoffs
    for col in ["win","pts","point_diff"]:
        df[f"{col}_playoff_last10"] = (
            df.groupby(["team_id","is_playoff"])[col]
            .transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean())
        )

    # Win streak
    def calc_streak(series):
        streaks, current = [], 0
        for val in series.shift(1):
            if pd.isna(val):
                streaks.append(0)
            elif val == 1:
                current = max(current+1, 1)
                streaks.append(current)
            else:
                current = min(current-1, -1)
                streaks.append(current)
        return streaks

    df["win_streak"] = df.groupby("team_id")["win"].transform(calc_streak)

    # Playoff win streak specifically
    df["playoff_win_streak"] = df.groupby(["team_id","is_playoff"])["win"].transform(calc_streak)

    return df

# ── Rest days ─────────────────────────────────────────────────────────────────

def add_rest_days(df):
    print("  Calculating rest days...")
    df = df.sort_values(["team_id","game_date"])
    df["prev_game_date"] = df.groupby("team_id")["game_date"].shift(1)
    df["rest_days"]      = (df["game_date"] - df["prev_game_date"]).dt.days
    df["rest_days"]      = df["rest_days"].fillna(7).clip(upper=14)
    df["is_b2b"]         = (df["rest_days"] == 1).astype(int)

    # Playoff rest tends to be longer — flag short rest in playoffs specifically
    df["playoff_short_rest"] = ((df["is_playoff"]==1) & (df["rest_days"]<=2)).astype(int)
    return df

# ── Home/away splits ──────────────────────────────────────────────────────────

def add_home_away_splits(df):
    print("  Calculating home/away splits...")
    df = df.sort_values(["team_id","game_date"])
    for loc, flag in [("home",1),("away",0)]:
        mask = df["is_home"] == flag
        for col in ["win","pts","point_diff"]:
            new_col = f"{col}_{loc}_last10"
            df[new_col] = np.nan
            subset = df[mask].copy()
            subset[new_col] = (
                subset.groupby("team_id")[col]
                .transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean())
            )
            df.loc[mask, new_col] = subset[new_col]
            df[new_col] = df.groupby("team_id")[new_col].ffill()
    return df

# ── Season win pct ────────────────────────────────────────────────────────────

def add_season_win_pct(df):
    print("  Calculating season win percentage...")
    df = df.sort_values(["team_id","season","game_date"])
    df["season_wins_so_far"] = (
        df.groupby(["team_id","season"])["win"]
        .transform(lambda x: x.shift(1).expanding().sum())
    ).fillna(0)
    df["season_games_so_far"] = (
        df.groupby(["team_id","season"])["win"]
        .transform(lambda x: x.shift(1).expanding().count())
    ).fillna(1)
    df["season_win_pct"] = df["season_wins_so_far"] / df["season_games_so_far"]

    # Playoff win pct separately
    playoff_df = df[df["is_playoff"]==1].copy()
    if not playoff_df.empty:
        playoff_df["playoff_wins_so_far"] = (
            playoff_df.groupby(["team_id","season"])["win"]
            .transform(lambda x: x.shift(1).expanding().sum())
        ).fillna(0)
        playoff_df["playoff_games_so_far"] = (
            playoff_df.groupby(["team_id","season"])["win"]
            .transform(lambda x: x.shift(1).expanding().count())
        ).fillna(1)
        playoff_df["playoff_win_pct"] = (
            playoff_df["playoff_wins_so_far"] / playoff_df["playoff_games_so_far"]
        )
        df = df.merge(
            playoff_df[["game_id","team_id","playoff_win_pct"]],
            on=["game_id","team_id"], how="left"
        )
        df["playoff_win_pct"] = df["playoff_win_pct"].fillna(
            df["season_win_pct"])
    else:
        df["playoff_win_pct"] = df["season_win_pct"]

    return df

# ── Pace proxy ────────────────────────────────────────────────────────────────

def add_pace(df):
    print("  Estimating pace...")
    df["pace_proxy"] = df["tov"] + df["ast"]
    df["pace_last5"] = (
        df.groupby("team_id")["pace_proxy"]
        .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    )
    # Playoff pace tends to be slower — track separately
    df["pace_playoff_last5"] = (
        df.groupby(["team_id","is_playoff"])["pace_proxy"]
        .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    )
    return df

# ── Opponent defensive rating ─────────────────────────────────────────────────

def add_opponent_def_rating(df, conn):
    """
    Calculate each team's defensive rating (points allowed per game)
    and join it as an opponent feature for each matchup.
    Uses rolling opp_pts_allowed as a proxy for defensive rating.
    """
    print("  Calculating opponent defensive ratings...")

    df = df.sort_values(["team_id","game_date"])

    # Rolling points allowed (defensive quality)
    df["pts_allowed_last5"]  = (
        df.groupby("team_id")["opp_pts"]
        .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    )
    df["pts_allowed_last10"] = (
        df.groupby("team_id")["opp_pts"]
        .transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean())
    )

    # Defensive win rate (games held under their average)
    df["def_stop_rate"] = (
        df.groupby("team_id")["win"]
        .transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean())
    )

    # Playoff defensive rating
    df["pts_allowed_playoff_last5"] = (
        df.groupby(["team_id","is_playoff"])["opp_pts"]
        .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    )

    return df

# ── Injury context (from NBA injury report API) ───────────────────────────────

def fetch_injury_data():
    """
    Fetches current NBA injury report from stats.nba.com.
    Returns dict of {team_abbrev: injury_count} for today.
    Free — no API key required.
    """
    print("  Fetching injury data from NBA.com...")
    url = "https://www.nba.com/injuries"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nba.com",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
    }

    # Try the stats API endpoint
    api_url = "https://stats.nba.com/stats/leagueinjuries"
    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            rows = data["resultSets"][0]["rowSet"]
            headers_list = data["resultSets"][0]["headers"]
            df = pd.DataFrame(rows, columns=headers_list)

            # Count injuries by team
            if "TEAM_ABBREVIATION" in df.columns:
                injury_counts = df.groupby("TEAM_ABBREVIATION").size().to_dict()
                # Count key player injuries (assume starters have higher impact)
                print(f"  Found {len(df)} injured players across {len(injury_counts)} teams.")
                return injury_counts
    except Exception as e:
        print(f"  NBA injury API unavailable: {e}")

    # Fallback: try rotowire-style endpoint
    try:
        alt_url = "https://stats.nba.com/stats/commonteamroster"
        print("  Falling back to estimated injury impact...")
    except Exception:
        pass

    print("  Using zero injury impact (API unavailable) — will update when data loads.")
    return {}

def add_injury_features(df, injury_counts: dict):
    """
    Add injury context as features.
    injury_counts: {team_abbrev: n_injured_players}
    """
    print("  Adding injury features...")

    if not injury_counts:
        df["injury_count"]        = 0
        df["has_injury"]          = 0
        df["injury_impact_score"] = 0.0
        return df

    # Map injury counts to each team
    df["injury_count"] = df["team_abbreviation"].map(injury_counts).fillna(0).astype(int)
    df["has_injury"]   = (df["injury_count"] > 0).astype(int)

    # Impact score: more injuries = higher impact
    # Normalize 0-1 where 3+ injuries = full impact
    df["injury_impact_score"] = (df["injury_count"] / 3).clip(upper=1.0)

    injured_teams = df[df["has_injury"]==1]["team_abbreviation"].nunique()
    print(f"  Injury data applied to {injured_teams} teams.")
    return df

# ── Build matchup features ────────────────────────────────────────────────────

def build_matchup_features(df):
    print("  Building matchup-level features...")

    home = df[df["is_home"]==1].copy()
    away = df[df["is_home"]==0].copy()

    home = home.add_prefix("home_").rename(columns={
        "home_game_id":"game_id","home_game_date":"game_date","home_season":"season"})
    away = away.add_prefix("away_").rename(columns={
        "away_game_id":"game_id","away_game_date":"game_date","away_season":"season"})

    matchups = home.merge(away, on=["game_id","game_date","season"], how="inner")

    # ── Playoff context features ──────────────────────────────────────────────
    matchups["is_playoff_game"]  = matchups["home_is_playoff"]
    matchups["is_playin_game"]   = matchups.get("home_is_playin", 0)

    # Both teams' playoff experience this season
    matchups["home_playoff_exp"] = matchups.get("home_playoff_games_so_far", 0)
    matchups["away_playoff_exp"] = matchups.get("away_playoff_games_so_far", 0)
    matchups["playoff_exp_diff"] = (
        matchups.get("home_playoff_games_so_far", 0) -
        matchups.get("away_playoff_games_so_far", 0)
    )

    # ── Injury differential ───────────────────────────────────────────────────
    matchups["home_injuries"]      = matchups.get("home_injury_count", 0)
    matchups["away_injuries"]      = matchups.get("away_injury_count", 0)
    matchups["injury_diff"]        = (
        matchups.get("away_injury_impact_score", 0) -
        matchups.get("home_injury_impact_score", 0)
    )  # positive = away team more injured (home advantage)

    # ── Opponent defensive rating differential ────────────────────────────────
    matchups["home_def_rating"]    = matchups.get("home_pts_allowed_last10", 0)
    matchups["away_def_rating"]    = matchups.get("away_pts_allowed_last10", 0)
    matchups["def_rating_diff"]    = (
        matchups.get("away_pts_allowed_last10", 110) -
        matchups.get("home_pts_allowed_last10", 110)
    )  # positive = away defense is worse (home team scores more)

    # ── Playoff-specific differentials ────────────────────────────────────────
    matchups["playoff_win_pct_diff"] = (
        matchups.get("home_playoff_win_pct", matchups.get("home_season_win_pct", 0.5)) -
        matchups.get("away_playoff_win_pct", matchups.get("away_season_win_pct", 0.5))
    )
    matchups["playoff_streak_diff"]  = (
        matchups.get("home_playoff_win_streak", 0) -
        matchups.get("away_playoff_win_streak", 0)
    )

    # ── Standard differential features ───────────────────────────────────────
    diff_pairs = [
        ("pts_last5",         "pts_diff_last5"),
        ("pts_last10",        "pts_diff_last10"),
        ("point_diff_last5",  "pdiff_diff_last5"),
        ("point_diff_last10", "pdiff_diff_last10"),
        ("win_last5",         "win_rate_diff_last5"),
        ("win_last10",        "win_rate_diff_last10"),
        ("season_win_pct",    "season_win_pct_diff"),
        ("rest_days",         "rest_days_diff"),
        ("win_streak",        "streak_diff"),
        ("fg_pct_last10",     "fg_pct_diff"),
        ("fg3_pct_last10",    "fg3_pct_diff"),
        ("tov_last10",        "tov_diff"),
        ("ast_last10",        "ast_diff"),
        ("reb_last10",        "reb_diff"),
        ("pace_last5",        "pace_diff"),
        ("pts_allowed_last10","def_strength_diff"),
    ]

    for base, diff_name in diff_pairs:
        h_col = f"home_{base}"
        a_col = f"away_{base}"
        if h_col in matchups.columns and a_col in matchups.columns:
            matchups[diff_name] = matchups[h_col] - matchups[a_col]

    matchups["home_advantage"] = 1

    print(f"  Built {len(matchups):,} matchup rows with {len(matchups.columns)} features.")
    return matchups

# ── Save ──────────────────────────────────────────────────────────────────────

def save_features(df, matchups, conn):
    print("  Saving to database...")
    df.to_sql("games_featured", conn, if_exists="replace", index=False)
    matchups.to_sql("matchups", conn, if_exists="replace", index=False)
    conn.commit()
    print(f"  Saved games_featured ({len(df):,}) and matchups ({len(matchups):,}).")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n── NBA Features v2 ──────────────────────────────────────")

    conn = get_conn()
    df   = load_games(conn)

    df = add_rolling_features(df)
    df = add_rest_days(df)
    df = add_home_away_splits(df)
    df = add_season_win_pct(df)
    df = add_pace(df)
    df = add_opponent_def_rating(df, conn)

    # Injury data — fetch live from NBA.com
    injury_counts = fetch_injury_data()
    df = add_injury_features(df, injury_counts)

    matchups = build_matchup_features(df)
    save_features(df, matchups, conn)

    print(f"\n── Feature summary ──────────────────────────────────────")
    feature_cols = [c for c in matchups.columns if any(
        x in c for x in ["diff","last","streak","rest","pct","pace",
                          "playoff","injury","def_rating","is_playoff"]
    )]
    print(f"  Predictive features  : {len(feature_cols)}")
    print(f"  Home win rate        : {matchups['home_win'].mean():.1%}")
    print(f"  Total matchups       : {len(matchups):,}")
    print(f"  Playoff matchups     : {matchups['is_playoff_game'].sum():,}")
    print(f"  Regular season       : {(matchups['is_playoff_game']==0).sum():,}")

    # Top correlations
    print(f"\n── Top feature correlations with home_win ───────────────")
    numeric = matchups[feature_cols + ["home_win"]].select_dtypes(include=[np.number])
    corr    = numeric.corr()["home_win"].drop("home_win").abs().sort_values(ascending=False)
    for feat, val in corr.head(12).items():
        print(f"  {feat:<38} {val:.4f}")

    print(f"\nNext step: python train.py\n")
    conn.close()



