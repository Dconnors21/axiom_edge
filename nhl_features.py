# ── nhl_features.py ───────────────────────────────────────────────────────────
# Engineers features from raw NHL game data.
# Usage: python nhl_features.py

import sqlite3
import pandas as pd
import numpy as np
from nhl_config import NHL_DB_PATH, ROLLING_SHORT, ROLLING_LONG

def get_conn():
    return sqlite3.connect(NHL_DB_PATH)

def load_games(conn):
    df = pd.read_sql("""
        SELECT * FROM nhl_games
        WHERE home_score IS NOT NULL AND away_score IS NOT NULL
        ORDER BY game_date ASC
    """, conn, parse_dates=["game_date"])
    df["home_win"]   = (df["home_score"] > df["away_score"]).astype(int)
    df["goal_diff"]  = df["home_score"] - df["away_score"]
    df["total_goals"]= df["home_score"] + df["away_score"]
    print(f"  Loaded {len(df):,} games | Home win rate: {df['home_win'].mean():.1%}")
    return df

def add_rolling_goals(df):
    print(f"  Rolling goal features (windows: {ROLLING_SHORT}, {ROLLING_LONG})...")
    for team_col, scored_col, allowed_col, prefix in [
        ("home_team", "home_score", "away_score", "home"),
        ("away_team", "away_score", "home_score", "away"),
    ]:
        for window in [ROLLING_SHORT, ROLLING_LONG]:
            df[f"{prefix}_goals_scored_last{window}"] = (
                df.groupby(team_col)[scored_col]
                .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
            )
            df[f"{prefix}_goals_allowed_last{window}"] = (
                df.groupby(team_col)[allowed_col]
                .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
            )
            # Win rate
            if prefix == "home":
                df[f"{prefix}_win_last{window}"] = (
                    df.groupby(team_col)["home_win"]
                    .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
                )
                df[f"{prefix}_goal_diff_last{window}"] = (
                    df.groupby(team_col)["goal_diff"]
                    .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
                )
            else:
                df[f"{prefix}_win_last{window}"] = (
                    df.groupby(team_col)["home_win"]
                    .transform(lambda x: (1 - x).shift(1).rolling(window, min_periods=1).mean())
                )
                df[f"{prefix}_goal_diff_last{window}"] = (
                    df.groupby(team_col)["goal_diff"]
                    .transform(lambda x: (-x).shift(1).rolling(window, min_periods=1).mean())
                )
    return df

def add_rolling_shots(df):
    print("  Rolling shot features...")
    # home_sog / away_sog columns from boxscore (may be NULL for older games)
    for team_col, sog_col, sog_against_col, prefix in [
        ("home_team", "home_sog", "away_sog", "home"),
        ("away_team", "away_sog", "home_sog", "away"),
    ]:
        for window in [ROLLING_SHORT, ROLLING_LONG]:
            df[f"{prefix}_shots_last{window}"] = (
                df.groupby(team_col)[sog_col]
                .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
            )
            df[f"{prefix}_shots_against_last{window}"] = (
                df.groupby(team_col)[sog_against_col]
                .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
            )
    return df

def add_special_teams(df):
    print("  Special teams features (PP%, PK%, SV%)...")
    PP_WINDOW = 10

    # Power play %
    df["home_pp_pct"] = np.where(
        df["home_pp_opp"].fillna(0) > 0,
        df["home_pp_goals"].fillna(0) / df["home_pp_opp"].fillna(1),
        np.nan,
    )
    df["away_pp_pct"] = np.where(
        df["away_pp_opp"].fillna(0) > 0,
        df["away_pp_goals"].fillna(0) / df["away_pp_opp"].fillna(1),
        np.nan,
    )

    for team_col, pp_col, prefix in [
        ("home_team", "home_pp_pct", "home"),
        ("away_team", "away_pp_pct", "away"),
    ]:
        df[f"{prefix}_pp_pct_last{PP_WINDOW}"] = (
            df.groupby(team_col)[pp_col]
            .transform(lambda x: x.shift(1).rolling(PP_WINDOW, min_periods=1).mean())
        )

    # PK% = 1 - opponent PP%   (when home team is on PK they're defending away PP)
    df["home_pk_pct"] = np.where(
        df["away_pp_opp"].fillna(0) > 0,
        1 - df["away_pp_goals"].fillna(0) / df["away_pp_opp"].fillna(1),
        np.nan,
    )
    df["away_pk_pct"] = np.where(
        df["home_pp_opp"].fillna(0) > 0,
        1 - df["home_pp_goals"].fillna(0) / df["home_pp_opp"].fillna(1),
        np.nan,
    )
    for team_col, pk_col, prefix in [
        ("home_team", "home_pk_pct", "home"),
        ("away_team", "away_pk_pct", "away"),
    ]:
        df[f"{prefix}_pk_pct_last{PP_WINDOW}"] = (
            df.groupby(team_col)[pk_col]
            .transform(lambda x: x.shift(1).rolling(PP_WINDOW, min_periods=1).mean())
        )

    # Save % (shots against - goals allowed) / shots against
    df["home_save_pct"] = np.where(
        df["away_sog"].fillna(0) > 0,
        (df["away_sog"].fillna(0) - df["away_score"]) / df["away_sog"].fillna(1),
        np.nan,
    )
    df["away_save_pct"] = np.where(
        df["home_sog"].fillna(0) > 0,
        (df["home_sog"].fillna(0) - df["home_score"]) / df["home_sog"].fillna(1),
        np.nan,
    )
    for team_col, sv_col, prefix in [
        ("home_team", "home_save_pct", "home"),
        ("away_team", "away_save_pct", "away"),
    ]:
        df[f"{prefix}_save_pct_last5"] = (
            df.groupby(team_col)[sv_col]
            .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
        )
    return df

def add_rest_days(df):
    print("  Calculating rest days...")
    for team_col, prefix in [("home_team", "home"), ("away_team", "away")]:
        df = df.sort_values([team_col, "game_date"])
        df[f"{prefix}_prev_game"] = df.groupby(team_col)["game_date"].shift(1)
        df[f"{prefix}_rest_days"] = (
            df["game_date"] - df[f"{prefix}_prev_game"]
        ).dt.days.fillna(3).clip(upper=10)
    return df

def add_streaks(df):
    print("  Calculating win streaks...")
    def calc_streak(series):
        streaks, current = [], 0
        for val in series.shift(1):
            if pd.isna(val):
                streaks.append(0)
            elif val == 1:
                current = max(current + 1, 1)
                streaks.append(current)
            else:
                current = min(current - 1, -1)
                streaks.append(current)
        return streaks

    df["home_win_streak"] = df.groupby("home_team")["home_win"].transform(calc_streak)
    df["away_win_streak"] = df.groupby("away_team")["home_win"].transform(
        lambda x: calc_streak(1 - x)
    )
    return df

def add_season_win_pct(df):
    print("  Calculating season win percentages...")
    for team_col, prefix in [("home_team", "home"), ("away_team", "away")]:
        cum_wins  = df.groupby([team_col, "season"])["home_win" if prefix == "home" else "home_win"].transform(
            lambda x: x.shift(1).expanding().sum()
        )
        cum_games = df.groupby([team_col, "season"])["home_win"].transform(
            lambda x: x.shift(1).expanding().count()
        )
        if prefix == "away":
            cum_wins = df.groupby([team_col, "season"])["home_win"].transform(
                lambda x: (1 - x).shift(1).expanding().sum()
            )
        df[f"{prefix}_season_win_pct"] = (cum_wins / cum_games.replace(0, np.nan)).fillna(0.5)
    return df

def add_h2h(df):
    print("  Computing H2H features...")
    h2h_records = {}

    def matchup_key(h, a):
        return tuple(sorted([h, a]))

    home_win_rates = []
    for _, row in df.iterrows():
        key  = matchup_key(row["home_team"], row["away_team"])
        hist = h2h_records.get(key, [])
        if len(hist) >= 3:
            wins_for_home = sum(1 for g in hist if g["home"] == row["home_team"] and g["hw"] == 1)
            total         = len(hist)
            home_win_rates.append(wins_for_home / total)
        else:
            home_win_rates.append(0.5)
        h2h_records.setdefault(key, []).append({
            "home": row["home_team"], "hw": row["home_win"]
        })

    df["h2h_home_win_rate"] = home_win_rates
    return df

def add_differentials(df):
    print("  Adding differential features...")
    df["goal_diff_diff_last5"]  = df["home_goal_diff_last5"]  - df["away_goal_diff_last5"]
    df["goal_diff_diff_last15"] = df["home_goal_diff_last15"] - df["away_goal_diff_last15"]
    df["win_rate_diff_last5"]   = df["home_win_last5"]  - df["away_win_last5"]
    df["win_rate_diff_last15"]  = df["home_win_last15"] - df["away_win_last15"]
    df["season_win_pct_diff"]   = df["home_season_win_pct"] - df["away_season_win_pct"]
    df["shot_diff_last5"]       = df["home_shots_last5"].fillna(0) - df["away_shots_last5"].fillna(0)
    df["home_advantage"]        = 1.0
    return df

def save_featured(df, conn):
    df.to_sql("nhl_games_featured", conn, if_exists="replace", index=False)
    print(f"  Saved {len(df):,} rows → nhl_games_featured")

def main():
    print("── NHL Feature Engineering ───────────────────────────────────────────────")
    conn = get_conn()
    df   = load_games(conn)

    if df.empty:
        print("  No games found. Run nhl_collect.py first.")
        conn.close()
        return

    df = add_rolling_goals(df)
    df = add_rolling_shots(df)
    df = add_special_teams(df)
    df = add_rest_days(df)
    df = add_streaks(df)
    df = add_season_win_pct(df)
    df = add_h2h(df)
    df = add_differentials(df)
    save_featured(df, conn)
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
