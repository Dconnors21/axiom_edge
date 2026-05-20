# train_props.py
# Trains an XGBoost regression model to predict NBA player points.
# Features are built from rolling game logs + opponent defensive context.
# Target: actual pts scored. Sigma (RMSE) is used for P(over) via Normal CDF.
#
# Usage: python train_props.py
# Output: props_points_model.pkl, props_points_features.json, props_points_model_std.json

import sqlite3
import json
import pickle
import numpy as np
import pandas as pd
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_squared_error
import math
from xgboost import XGBRegressor
from config import DB_PATH

MIN_GAMES = 10       # minimum prior games for a player-game row to be in training
MIN_MINUTES = 10.0   # skip garbage time appearances


def get_conn():
    return sqlite3.connect(DB_PATH)


def build_features(conn) -> pd.DataFrame:
    logs = pd.read_sql("""
        SELECT player_id, player_name, team_abbreviation, game_id,
               game_date, season, is_home, wl, min_played, pts, tov
        FROM player_game_logs
        ORDER BY player_id, game_date ASC
    """, conn)

    if logs.empty:
        return pd.DataFrame()

    logs["game_date"] = pd.to_datetime(logs["game_date"])

    # Opponent abbreviation from matchup in games table
    games_teams = pd.read_sql("""
        SELECT game_id, team_abbreviation, pts AS team_pts
        FROM games
    """, conn)

    # Team defensive stats (pts allowed) from team_season_stats
    def_stats = pd.read_sql("""
        SELECT season, team_name, opp_pts, def_rtg, pace
        FROM team_season_stats
    """, conn)

    # Map team_name -> abbreviation via games table
    team_abbrev = pd.read_sql("""
        SELECT DISTINCT team_abbreviation, team_name FROM games
    """, conn).drop_duplicates("team_abbreviation")
    abbrev_map = team_abbrev.set_index("team_name")["team_abbreviation"].to_dict()
    def_stats["team_abbrev"] = def_stats["team_name"].map(abbrev_map)
    def_stats = def_stats.dropna(subset=["team_abbrev"])
    def_lookup = def_stats.set_index(["season","team_abbrev"]).to_dict("index")

    rows = []
    for player_id, grp in logs.groupby("player_id"):
        grp = grp.sort_values("game_date").reset_index(drop=True)

        for i in range(MIN_GAMES, len(grp)):
            cur  = grp.iloc[i]
            hist = grp.iloc[:i]

            # Skip garbage time
            if cur["min_played"] < MIN_MINUTES:
                continue

            # Rolling averages (prior games only — no lookahead)
            pts_l5  = hist["pts"].tail(5).mean()
            pts_l10 = hist["pts"].tail(10).mean()
            min_l5  = hist["min_played"].tail(5).mean()
            pts_l3  = hist["pts"].tail(3).mean()
            pts_std = hist["pts"].tail(10).std()
            season_pts = hist[hist["season"] == cur["season"]]["pts"].mean()

            # Home/away splits
            home_hist = hist[hist["is_home"] == 1]["pts"]
            away_hist = hist[hist["is_home"] == 0]["pts"]
            pts_home  = home_hist.tail(5).mean() if len(home_hist) >= 3 else pts_l5
            pts_away  = away_hist.tail(5).mean() if len(away_hist) >= 3 else pts_l5

            # Days rest
            if i > 0:
                prev_date = grp.iloc[i-1]["game_date"]
                days_rest = (cur["game_date"] - prev_date).days
            else:
                days_rest = 3
            days_rest = min(days_rest, 7)

            # Opponent defensive rating
            # Extract opponent abbreviation from matchup ("BOS vs. LAL" → opponent = "LAL")
            matchup = str(cur.get("matchup", ""))
            parts   = matchup.replace("vs.", "@").split("@")
            opp_abbr = parts[-1].strip() if len(parts) == 2 else ""
            opp_key  = (cur["season"], opp_abbr)
            opp_info = def_lookup.get(opp_key, {})
            opp_def_rtg  = opp_info.get("def_rtg",  108.0)
            opp_pace     = opp_info.get("pace",      100.0)
            opp_opp_pts  = opp_info.get("opp_pts",   110.0)

            rows.append({
                "player_id":    player_id,
                "game_id":      cur["game_id"],
                "game_date":    cur["game_date"],
                "season":       cur["season"],
                "pts_l3":       pts_l3,
                "pts_l5":       pts_l5,
                "pts_l10":      pts_l10,
                "pts_std":      pts_std if not np.isnan(pts_std) else 0.0,
                "min_l5":       min_l5,
                "season_pts":   season_pts if not np.isnan(season_pts) else pts_l10,
                "pts_home_l5":  pts_home,
                "pts_away_l5":  pts_away,
                "is_home":      int(cur["is_home"]),
                "days_rest":    days_rest,
                "opp_def_rtg":  opp_def_rtg,
                "opp_pace":     opp_pace,
                "opp_opp_pts":  opp_opp_pts,
                "target_pts":   cur["pts"],
            })

    return pd.DataFrame(rows)


FEATURE_COLS = [
    "pts_l3", "pts_l5", "pts_l10", "pts_std",
    "min_l5", "season_pts",
    "pts_home_l5", "pts_away_l5",
    "is_home", "days_rest",
    "opp_def_rtg", "opp_pace", "opp_opp_pts",
]


if __name__ == "__main__":
    print("\n-- Train Props: Player Points Model --------------------------------")

    conn = get_conn()
    print("  Building training features from player_game_logs...")
    df = build_features(conn)
    conn.close()

    if df.empty:
        print("  No data — run python collect_props.py first.")
        exit(1)

    df = df.dropna(subset=FEATURE_COLS + ["target_pts"])
    print(f"  Training rows: {len(df):,} | Players: {df['player_id'].nunique()}")

    X = df[FEATURE_COLS].values
    y = df["target_pts"].values

    model = XGBRegressor(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
    )

    print("  Cross-validating (5-fold)...")
    cv_scores = cross_val_score(model, X, y, cv=5,
                                scoring="neg_root_mean_squared_error")
    cv_rmse = -cv_scores.mean()
    print(f"  CV RMSE: {cv_rmse:.2f} pts")

    model.fit(X, y)
    train_preds = model.predict(X)
    train_rmse  = math.sqrt(mean_squared_error(y, train_preds))
    print(f"  Train RMSE: {train_rmse:.2f} pts")

    # Feature importance
    fi = sorted(zip(FEATURE_COLS, model.feature_importances_),
                key=lambda x: x[1], reverse=True)
    print("  Top features:")
    for name, imp in fi[:5]:
        print(f"    {name:<20} {imp:.4f}")

    with open("props_points_model.pkl", "wb") as f:
        pickle.dump(model, f)
    with open("props_points_features.json", "w") as f:
        json.dump(FEATURE_COLS, f)
    with open("props_points_model_std.json", "w") as f:
        json.dump({"rmse": train_rmse, "cv_rmse": cv_rmse}, f)

    print(f"\n  Saved: props_points_model.pkl | sigma={train_rmse:.2f} pts")
