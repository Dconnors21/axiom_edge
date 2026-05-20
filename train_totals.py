# --train_totals.py ────────────────────────────────────────────────────────────
# Trains an XGBoost regressor to predict NBA total game score (home + away pts).
# Used by totals_predict.py to estimate P(over/under) via Normal CDF.
#
# Usage: python train_totals.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from pathlib import Path
from xgboost import XGBRegressor
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from config import DB_PATH

# Totals-focused features — scoring rates, pace, efficiency, rest
# Drops win-rate/differential features that capture relative strength, not total volume
FEATURE_COLS = [
    # Scoring rates (offense)
    "home_pts_last5", "home_pts_last10",
    "away_pts_last5", "away_pts_last10",

    # Scoring rates (defense — points allowed)
    "home_opp_pts_last5", "home_opp_pts_last10",
    "away_opp_pts_last5", "away_opp_pts_last10",

    # Shooting efficiency
    "home_fg_pct_last5",  "home_fg_pct_last10",
    "away_fg_pct_last5",  "away_fg_pct_last10",
    "home_fg3_pct_last5", "home_fg3_pct_last10",
    "away_fg3_pct_last5", "away_fg3_pct_last10",

    # Possessions / hustle
    "home_tov_last10", "away_tov_last10",
    "home_reb_last10", "away_reb_last10",
    "home_ast_last10", "away_ast_last10",

    # Pace
    "home_pace_last5", "away_pace_last5",

    # Rest / fatigue
    "home_rest_days", "away_rest_days",
    "home_is_b2b",    "away_is_b2b",

    # H2H scoring history
    "h2h_home_avg_pts", "h2h_away_avg_pts",
    "h2h_meetings",

    # Home court (affects pace/game plan)
    "home_advantage",
]

TARGET = "total_pts"


def get_conn():
    return sqlite3.connect(DB_PATH)


def load_matchups(conn):
    df = pd.read_sql("SELECT * FROM matchups", conn, parse_dates=["game_date"])

    if "home_pts" in df.columns and "away_pts" in df.columns:
        df[TARGET] = df["home_pts"] + df["away_pts"]
    else:
        raise ValueError("Cannot find home_pts/away_pts columns. Run features.py first.")

    df = df.dropna(subset=[TARGET])

    available = [c for c in FEATURE_COLS if c in df.columns]
    missing   = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        print(f"  Note: {len(missing)} feature(s) not in matchups, skipping: {missing[:5]}...")

    df[available] = df[available].fillna(df[available].median())
    return df, available


def split_by_season(df):
    train = df[df["season"].isin(["2023-24", "2024-25"])].copy()
    test  = df[df["season"] == "2025-26"].copy()
    return train, test


def train_model(X_train, y_train):
    print("  Training XGBoost regressor...")

    model = XGBRegressor(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        gamma=0.1,
        reg_alpha=0.1,
        reg_lambda=1.0,
        eval_metric="rmse",
        random_state=42,
        n_jobs=-1,
    )

    cv_rmse = cross_val_score(model, X_train, y_train, cv=5,
                              scoring="neg_root_mean_squared_error", n_jobs=-1)
    print(f"  CV RMSE: {-cv_rmse.mean():.2f} ± {cv_rmse.std():.2f} pts")

    model.fit(X_train, y_train)
    return model


def evaluate(model, X_test, y_test, feature_cols):
    preds = model.predict(X_test)

    mae  = mean_absolute_error(y_test, preds)
    rmse = mean_squared_error(y_test, preds) ** 0.5
    r2   = r2_score(y_test, preds)

    print(f"\n--Test set performance (2025-26 season) ────────────────")
    print(f"  MAE  (avg error) : {mae:.2f} pts")
    print(f"  RMSE             : {rmse:.2f} pts  ← used as σ in P(over/under)")
    print(f"  R²               : {r2:.4f}")
    print(f"  Avg predicted total: {preds.mean():.1f}")
    print(f"  Avg actual total  : {y_test.mean():.1f}")

    try:
        importances = pd.Series(
            model.feature_importances_, index=feature_cols
        ).sort_values(ascending=False)
        print(f"\n--Top 10 most important features ───────────────────────")
        for feat, imp in importances.head(10).items():
            bar = "█" * int(imp * 200)
            print(f"  {feat:<35} {imp:.4f} {bar}")
    except Exception:
        pass

    return rmse, preds


if __name__ == "__main__":
    print("\n--NBA Totals Train ─────────────────────────────────────")

    conn = get_conn()
    df, feature_cols = load_matchups(conn)

    print(f"  Total matchups  : {len(df):,}")
    print(f"  Avg total score : {df[TARGET].mean():.1f} pts")
    print(f"  Std total score : {df[TARGET].std():.2f} pts")
    print(f"  Features used   : {len(feature_cols)}")

    train_df, test_df = split_by_season(df)
    print(f"  Train set       : {len(train_df):,} games")
    print(f"  Test set        : {len(test_df):,} games")

    if train_df.empty:
        print("  ERROR: No training data. Run collect.py + features.py first.")
        conn.close()
        exit(1)

    X_train = train_df[feature_cols]
    y_train = train_df[TARGET]
    X_test  = test_df[feature_cols]
    y_test  = test_df[TARGET]

    model = train_model(X_train, y_train)

    if not test_df.empty:
        rmse, preds = evaluate(model, X_test, y_test, feature_cols)
    else:
        train_preds = model.predict(X_train)
        rmse = mean_squared_error(y_train, train_preds) ** 0.5
        print(f"  No test data — using train RMSE as σ: {rmse:.2f}")

    print(f"\n--Saving model ─────────────────────────────────────────")
    with open("totals_model.pkl", "wb") as f:
        pickle.dump(model, f)
    with open("totals_features.json", "w") as f:
        json.dump(feature_cols, f)
    with open("totals_model_std.json", "w") as f:
        json.dump({"rmse": float(rmse)}, f)

    print(f"  Saved totals_model.pkl, totals_features.json, totals_model_std.json")
    print(f"  σ (RMSE) = {rmse:.2f} pts — used in P(over/under) Normal CDF")
    print(f"\nNext step: python totals_predict.py\n")

    conn.close()
