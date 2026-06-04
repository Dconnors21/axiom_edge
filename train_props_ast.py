# train_props_ast.py
# Trains an XGBoost regression model to predict NBA player assists per game.
# Mirror of train_props_reb.py — same architecture, target column = ast.
#
# Usage: python train_props_ast.py
# Output: props_ast_model.pkl, props_ast_features.json, props_ast_model_std.json

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

MIN_GAMES   = 10
MIN_MINUTES = 10.0


def get_conn():
    return sqlite3.connect(DB_PATH)


def build_features(conn) -> pd.DataFrame:
    logs = pd.read_sql("""
        SELECT player_id, player_name, team_abbreviation, game_id,
               game_date, season, matchup, is_home, wl, min_played, ast
        FROM player_game_logs
        WHERE ast IS NOT NULL
        ORDER BY player_id, game_date ASC
    """, conn)

    if logs.empty:
        return pd.DataFrame()

    logs["game_date"] = pd.to_datetime(logs["game_date"])

    def_stats = pd.read_sql("""
        SELECT season, team_name, opp_pts, def_rtg, pace
        FROM team_season_stats
    """, conn)

    team_abbrev = pd.read_sql("""
        SELECT DISTINCT team_abbreviation, team_name FROM games
    """, conn).drop_duplicates("team_abbreviation")
    abbrev_map = team_abbrev.set_index("team_name")["team_abbreviation"].to_dict()
    def_stats["team_abbrev"] = def_stats["team_name"].map(abbrev_map)
    def_stats = def_stats.dropna(subset=["team_abbrev"])
    def_lookup = def_stats.set_index(["season", "team_abbrev"]).to_dict("index")

    rows = []
    for player_id, grp in logs.groupby("player_id"):
        grp = grp.sort_values("game_date").reset_index(drop=True)

        for i in range(MIN_GAMES, len(grp)):
            cur  = grp.iloc[i]
            hist = grp.iloc[:i]

            if cur["min_played"] < MIN_MINUTES:
                continue

            ast_l3   = hist["ast"].tail(3).mean()
            ast_l5   = hist["ast"].tail(5).mean()
            ast_l10  = hist["ast"].tail(10).mean()
            ast_std  = hist["ast"].tail(10).std()
            min_l5   = hist["min_played"].tail(5).mean()
            season_ast = hist[hist["season"] == cur["season"]]["ast"].mean()

            home_hist = hist[hist["is_home"] == 1]["ast"]
            away_hist = hist[hist["is_home"] == 0]["ast"]
            ast_home_l5 = home_hist.tail(5).mean() if len(home_hist) >= 3 else ast_l5
            ast_away_l5 = away_hist.tail(5).mean() if len(away_hist) >= 3 else ast_l5

            if i > 0:
                prev_date = grp.iloc[i-1]["game_date"]
                days_rest = (cur["game_date"] - prev_date).days
            else:
                days_rest = 3
            days_rest = min(days_rest, 7)

            matchup  = str(cur.get("matchup", ""))
            parts    = matchup.replace("vs.", "@").split("@")
            opp_abbr = parts[-1].strip() if len(parts) == 2 else ""
            opp_key  = (cur["season"], opp_abbr)
            opp_info = def_lookup.get(opp_key, {})
            opp_def_rtg = opp_info.get("def_rtg",  108.0)
            opp_pace    = opp_info.get("pace",      100.0)
            opp_opp_pts = opp_info.get("opp_pts",   110.0)

            rows.append({
                "player_id":   player_id,
                "game_id":     cur["game_id"],
                "game_date":   cur["game_date"],
                "season":      cur["season"],
                "ast_l3":      ast_l3,
                "ast_l5":      ast_l5,
                "ast_l10":     ast_l10,
                "ast_std":     ast_std if not np.isnan(ast_std) else 0.0,
                "min_l5":      min_l5,
                "season_ast":  season_ast if not np.isnan(season_ast) else ast_l10,
                "ast_home_l5": ast_home_l5,
                "ast_away_l5": ast_away_l5,
                "is_home":     int(cur["is_home"]),
                "days_rest":   days_rest,
                "opp_def_rtg": opp_def_rtg,
                "opp_pace":    opp_pace,
                "opp_opp_pts": opp_opp_pts,
                "target_ast":  cur["ast"],
            })

    return pd.DataFrame(rows)


FEATURE_COLS = [
    "ast_l3", "ast_l5", "ast_l10", "ast_std",
    "min_l5", "season_ast",
    "ast_home_l5", "ast_away_l5",
    "is_home", "days_rest",
    "opp_def_rtg", "opp_pace", "opp_opp_pts",
]


if __name__ == "__main__":
    print("\n-- Train Props: Player Assists Model --------------------------------")

    conn = get_conn()
    print("  Building training features from player_game_logs...")
    df = build_features(conn)
    conn.close()

    if df.empty:
        print("  No data — run python collect_props.py first.")
        exit(1)

    df = df.dropna(subset=FEATURE_COLS + ["target_ast"])
    print(f"  Training rows: {len(df):,} | Players: {df['player_id'].nunique()}")

    X = df[FEATURE_COLS].values
    y = df["target_ast"].values

    model = XGBRegressor(
        n_estimators=400,
        max_depth=4,
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
    print(f"  CV RMSE: {cv_rmse:.2f} ast")

    model.fit(X, y)
    train_preds = model.predict(X)
    train_rmse  = math.sqrt(mean_squared_error(y, train_preds))
    print(f"  Train RMSE: {train_rmse:.2f} ast")

    fi = sorted(zip(FEATURE_COLS, model.feature_importances_),
                key=lambda x: x[1], reverse=True)
    print("  Top features:")
    for name, imp in fi[:5]:
        print(f"    {name:<22} {imp:.4f}")

    with open("props_ast_model.pkl", "wb") as f:
        pickle.dump(model, f)
    with open("props_ast_features.json", "w") as f:
        json.dump(FEATURE_COLS, f)
    with open("props_ast_model_std.json", "w") as f:
        json.dump({"rmse": train_rmse, "cv_rmse": cv_rmse}, f)

    print(f"\n  Saved: props_ast_model.pkl | sigma={train_rmse:.2f} ast")
