# ── mlb_features.py ───────────────────────────────────────────────────────────
# Engineers features from raw MLB game data.
# Usage: python mlb_features.py

import sqlite3
import pandas as pd
import numpy as np
from mlb_config import MLB_DB_PATH, ROLLING_SHORT, ROLLING_LONG

def get_conn():
    return sqlite3.connect(MLB_DB_PATH)

def load_games(conn):
    df = pd.read_sql("""
        SELECT * FROM mlb_games
        WHERE home_score IS NOT NULL AND away_score IS NOT NULL
        ORDER BY game_date ASC
    """, conn, parse_dates=["game_date"])
    df["home_win"] = (df["home_score"] > df["away_score"]).astype(int)
    df["run_diff"] = df["home_score"] - df["away_score"]
    print(f"  Loaded {len(df):,} games | Home win rate: {df['home_win'].mean():.1%}")
    return df

def add_rolling_features(df):
    print(f"  Rolling features (windows: {ROLLING_SHORT}, {ROLLING_LONG})...")
    df = df.sort_values(["home_team","game_date"]).reset_index(drop=True)
    for team_col, score_col, allowed_col, prefix in [
        ("home_team","home_score","away_score","home"),
        ("away_team","away_score","home_score","away"),
    ]:
        for window in [ROLLING_SHORT, ROLLING_LONG]:
            df[f"{prefix}_runs_scored_last{window}"] = (
                df.groupby(team_col)[score_col]
                .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
            )
            df[f"{prefix}_runs_allowed_last{window}"] = (
                df.groupby(team_col)[allowed_col]
                .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
            )
            if prefix == "home":
                df[f"{prefix}_win_last{window}"] = (
                    df.groupby(team_col)["home_win"]
                    .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
                )
                df[f"{prefix}_run_diff_last{window}"] = (
                    df.groupby(team_col)["run_diff"]
                    .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
                )
            else:
                df[f"{prefix}_win_last{window}"] = (
                    df.groupby(team_col)["home_win"]
                    .transform(lambda x: (1-x).shift(1).rolling(window, min_periods=1).mean())
                )
                df[f"{prefix}_run_diff_last{window}"] = (
                    df.groupby(team_col)["run_diff"]
                    .transform(lambda x: (-x).shift(1).rolling(window, min_periods=1).mean())
                )
    return df

def add_rest_days(df):
    print("  Calculating rest days...")
    for team_col, prefix in [("home_team","home"),("away_team","away")]:
        df = df.sort_values([team_col,"game_date"])
        df[f"{prefix}_prev_game"] = df.groupby(team_col)["game_date"].shift(1)
        df[f"{prefix}_rest_days"] = (
            df["game_date"] - df[f"{prefix}_prev_game"]
        ).dt.days.fillna(4).clip(upper=10)
    return df

def add_streaks(df):
    print("  Calculating win streaks...")
    def calc_streak(series):
        streaks, current = [], 0
        for val in series.shift(1):
            if pd.isna(val): streaks.append(0)
            elif val == 1: current = max(current+1,1); streaks.append(current)
            else: current = min(current-1,-1); streaks.append(current)
        return streaks
    df["home_win_streak"] = df.groupby("home_team")["home_win"].transform(calc_streak)
    df["away_win_streak"] = df.groupby("away_team")["home_win"].transform(
        lambda x: calc_streak(1-x))
    return df

def add_season_win_pct(df):
    print("  Calculating season win pct...")
    df = df.sort_values(["home_team","season","game_date"])
    df["home_season_win_pct"] = (
        df.groupby(["home_team","season"])["home_win"]
        .transform(lambda x: x.shift(1).expanding().mean())
    ).fillna(0.5)
    df["away_season_win_pct"] = (
        df.groupby(["away_team","season"])["home_win"]
        .transform(lambda x: (1-x).shift(1).expanding().mean())
    ).fillna(0.5)
    return df

def add_home_away_splits(df):
    print("  Calculating home/away splits...")
    home_games = df.copy()
    home_games["home_win_pct_home"] = (
        home_games.groupby("home_team")["home_win"]
        .transform(lambda x: x.shift(1).rolling(20,min_periods=1).mean())
    ).fillna(0.5)
    away_view = df.copy()
    away_view["away_win_as_away"] = 1 - away_view["home_win"]
    away_view["away_win_pct_away"] = (
        away_view.groupby("away_team")["away_win_as_away"]
        .transform(lambda x: x.shift(1).rolling(20,min_periods=1).mean())
    ).fillna(0.5)
    df["home_win_pct_home"] = home_games["home_win_pct_home"]
    df["away_win_pct_away"] = away_view["away_win_pct_away"]
    return df

def add_h2h_features(df):
    print("  Building H2H features...")
    df = df.sort_values("game_date").reset_index(drop=True)
    N = 8
    h2h_rows = []
    for idx, row in df.iterrows():
        home=row["home_team"]; away=row["away_team"]; gdate=row["game_date"]
        prev = df[
            (df["game_date"] < gdate) &
            (((df["home_team"]==home)&(df["away_team"]==away)) |
             ((df["home_team"]==away)&(df["away_team"]==home)))
        ].tail(N)
        if prev.empty:
            h2h_rows.append({"h2h_home_win_rate":0.5,"h2h_avg_run_diff":0.0})
            continue
        home_view = prev[prev["home_team"]==home]
        away_view = prev[prev["home_team"]==away]
        home_wins  = (home_view["home_win"]==1).sum()
        home_wins += (away_view["home_win"]==0).sum()
        total      = len(prev)
        win_rate   = home_wins/total
        h_diffs    = home_view["run_diff"].tolist()
        a_diffs    = [-x for x in away_view["run_diff"].tolist()]
        avg_diff   = np.mean(h_diffs+a_diffs) if (h_diffs+a_diffs) else 0.0
        h2h_rows.append({
            "h2h_home_win_rate": round(win_rate,4),
            "h2h_avg_run_diff":  round(avg_diff,2),
        })
        if (idx+1) % 1000 == 0:
            print(f"  H2H: {idx+1:,}/{len(df):,}...")
    h2h_df = pd.DataFrame(h2h_rows, index=df.index)
    df["h2h_home_win_rate"] = h2h_df["h2h_home_win_rate"]
    df["h2h_avg_run_diff"]  = h2h_df["h2h_avg_run_diff"]
    return df

def add_park_factors(df):
    park_factors = {
        "COL":1.18,"BOS":1.08,"CIN":1.07,"TEX":1.06,"PHI":1.05,
        "NYY":1.04,"BAL":1.03,"ATL":1.02,"CHC":1.01,"MIL":1.00,
        "STL":1.00,"MIN":0.99,"LAD":0.99,"HOU":0.98,"TBR":0.98,
        "NYM":0.97,"SFG":0.97,"OAK":0.97,"SEA":0.96,"MIA":0.96,
        "SDP":0.96,"PIT":0.96,"DET":0.96,"CHW":0.95,"LAA":0.95,
        "CLE":0.95,"KCR":0.94,"TOR":0.94,"WSN":0.94,"ARI":0.97,
    }
    df["park_factor"] = df["home_team"].map(park_factors).fillna(1.0)
    return df

def add_pitcher_features(df, conn):
    print("  Adding pitcher features...")
    try:
        pitchers = pd.read_sql("""
            SELECT team, season, AVG(era) as era, AVG(whip) as whip
            FROM pitcher_season_stats
            GROUP BY team, season
        """, conn)

        if pitchers.empty:
            raise ValueError("No pitcher data in pitcher_season_stats")

        # Deduplicate before indexing
        pitchers = pitchers.drop_duplicates(subset=["team","season"])
        lookup   = pitchers.set_index(["team","season"])[["era","whip"]].to_dict("index")

        def get_era(team, season):
            return lookup.get((str(team), str(season)), {}).get("era", 4.20)

        def get_whip(team, season):
            return lookup.get((str(team), str(season)), {}).get("whip", 1.30)

        df["home_sp_era_season"]  = df.apply(lambda r: get_era(r["home_team"],  r["season"]), axis=1)
        df["away_sp_era_season"]  = df.apply(lambda r: get_era(r["away_team"],  r["season"]), axis=1)
        df["home_sp_whip_season"] = df.apply(lambda r: get_whip(r["home_team"], r["season"]), axis=1)
        df["away_sp_whip_season"] = df.apply(lambda r: get_whip(r["away_team"], r["season"]), axis=1)
        df["sp_era_diff"]         = df["away_sp_era_season"] - df["home_sp_era_season"]

        era_min = df["home_sp_era_season"].min()
        era_max = df["home_sp_era_season"].max()
        print(f"  Pitcher ERA range: {era_min:.2f} – {era_max:.2f} "
              f"(default=4.20 means team had no pitcher data)")

    except Exception as e:
        print(f"  Pitcher features failed: {e} — using league average defaults")
        df["home_sp_era_season"]  = 4.20
        df["away_sp_era_season"]  = 4.20
        df["home_sp_whip_season"] = 1.30
        df["away_sp_whip_season"] = 1.30
        df["sp_era_diff"]         = 0.0

    return df

def add_differentials(df):
    print("  Building differential features...")
    pairs = [
        ("home_runs_scored_last5",  "away_runs_scored_last5",  "runs_scored_diff_last5"),
        ("home_runs_scored_last15", "away_runs_scored_last15", "runs_scored_diff_last15"),
        ("home_runs_allowed_last5", "away_runs_allowed_last5", "runs_allowed_diff_last5"),
        ("home_run_diff_last5",     "away_run_diff_last5",     "run_diff_diff_last5"),
        ("home_run_diff_last15",    "away_run_diff_last15",    "run_diff_diff_last15"),
        ("home_win_last5",          "away_win_last5",          "win_rate_diff_last5"),
        ("home_win_last15",         "away_win_last15",         "win_rate_diff_last15"),
        ("home_season_win_pct",     "away_season_win_pct",     "season_win_pct_diff"),
        ("home_rest_days",          "away_rest_days",          "rest_days_diff"),
        ("home_win_streak",         "away_win_streak",         "streak_diff"),
    ]
    for h, a, d in pairs:
        if h in df.columns and a in df.columns:
            df[d] = df[h] - df[a]
    df["home_advantage"] = 1.0
    return df

def save_features(df, conn):
    print("  Saving mlb_games_featured...")
    df.to_sql("mlb_games_featured", conn, if_exists="replace", index=False)
    conn.commit()
    print(f"  Saved {len(df):,} rows.")

if __name__ == "__main__":
    print("\n── MLB Features ─────────────────────────────────────────")
    conn = get_conn()
    df   = load_games(conn)
    df   = add_rolling_features(df)
    df   = add_rest_days(df)
    df   = add_streaks(df)
    df   = add_season_win_pct(df)
    df   = add_home_away_splits(df)
    df   = add_h2h_features(df)
    df   = add_park_factors(df)
    df   = add_pitcher_features(df, conn)
    df   = add_differentials(df)
    save_features(df, conn)

    from mlb_config import FEATURE_COLS
    feature_cols = [c for c in FEATURE_COLS if c in df.columns]
    print(f"\n── Feature correlations with home_win ───────────────────")
    numeric = df[feature_cols + ["home_win"]].select_dtypes(include=[np.number])
    corr    = numeric.corr()["home_win"].drop("home_win").abs().sort_values(ascending=False)
    for feat, val in corr.head(10).items():
        print(f"  {feat:<38} {val:.4f}")
    print(f"\n  Next step: python mlb_train.py")
    conn.close()
