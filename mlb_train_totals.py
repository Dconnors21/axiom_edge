# ── mlb_train_totals.py ────────────────────────────────────────────────────────
# Trains an XGBoost regressor to predict MLB total runs scored (home + away).
# Used by mlb_totals_predict.py to estimate P(over/under) via Normal CDF.
#
# Usage: python mlb_train_totals.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from xgboost import XGBRegressor
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from mlb_config import MLB_DB_PATH

# Totals-focused features — scoring rates, pitching, park effects
# Drops win-rate/differential features that capture team quality, not run volume
FEATURE_COLS = [
    # Offensive run production
    "home_runs_scored_last5",  "home_runs_scored_last15",
    "away_runs_scored_last5",  "away_runs_scored_last15",

    # Defensive runs allowed
    "home_runs_allowed_last5", "home_runs_allowed_last15",
    "away_runs_allowed_last5", "away_runs_allowed_last15",

    # Starting pitcher (biggest driver of run environment)
    "home_sp_era_season",  "away_sp_era_season",
    "home_sp_whip_season", "away_sp_whip_season",

    # Bullpen
    "home_bullpen_era_last7", "away_bullpen_era_last7",

    # Park factor (Coors vs pitcher-friendly parks)
    "park_factor",

    # Rest / fatigue
    "home_rest_days", "away_rest_days",

    # Home advantage
    "home_advantage",
]

TARGET = "total_runs"


def get_conn():
    return sqlite3.connect(MLB_DB_PATH)


def load_data(conn):
    df = pd.read_sql("SELECT * FROM mlb_games_featured", conn)

    if "home_score" in df.columns and "away_score" in df.columns:
        df[TARGET] = df["home_score"] + df["away_score"]
    elif "home_runs_scored" in df.columns and "away_runs_scored" in df.columns:
        df[TARGET] = df["home_runs_scored"] + df["away_runs_scored"]
    else:
        raise ValueError("Cannot find score columns. Run mlb_features.py first.")

    df = df.dropna(subset=[TARGET])

    available = [c for c in FEATURE_COLS if c in df.columns]
    missing   = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        print(f"  Note: {len(missing)} feature(s) not found, skipping: {missing[:5]}...")

    df[available] = df[available].fillna(df[available].median())
    return df, available


def split_by_season(df):
    if "season" not in df.columns:
        n = int(len(df) * 0.8)
        return df.iloc[:n].copy(), df.iloc[n:].copy()
    train = df[df["season"].isin(["2023", "2024"])].copy()
    test  = df[df["season"] == "2025"].copy()
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
    print(f"  CV RMSE: {-cv_rmse.mean():.2f} +/- {cv_rmse.std():.2f} runs")

    model.fit(X_train, y_train)
    return model


def evaluate(model, X_test, y_test, feature_cols):
    preds = model.predict(X_test)

    mae  = mean_absolute_error(y_test, preds)
    rmse = mean_squared_error(y_test, preds) ** 0.5
    r2   = r2_score(y_test, preds)

    print(f"\n-- Test set performance ─────────────────────────────────")
    print(f"  MAE  (avg error) : {mae:.2f} runs")
    print(f"  RMSE             : {rmse:.2f} runs  <- used as sigma in P(over/under)")
    print(f"  R2               : {r2:.4f}")
    print(f"  Avg predicted total: {preds.mean():.1f}")
    print(f"  Avg actual total   : {y_test.mean():.1f}")

    try:
        importances = pd.Series(
            model.feature_importances_, index=feature_cols
        ).sort_values(ascending=False)
        print(f"\n-- Top 10 most important features ───────────────────────")
        for feat, imp in importances.head(10).items():
            bar = "#" * int(imp * 200)
            print(f"  {feat:<35} {imp:.4f} {bar}")
    except Exception:
        pass

    return rmse, preds


if __name__ == "__main__":
    print("\n-- MLB Totals Train ─────────────────────────────────────")

    conn = get_conn()
    df, feature_cols = load_data(conn)

    print(f"  Total games     : {len(df):,}")
    print(f"  Avg total runs  : {df[TARGET].mean():.1f}")
    print(f"  Std total runs  : {df[TARGET].std():.2f}")
    print(f"  Features used   : {len(feature_cols)}")

    train_df, test_df = split_by_season(df)
    print(f"  Train set       : {len(train_df):,} games")
    print(f"  Test set        : {len(test_df):,} games")

    if train_df.empty:
        print("  ERROR: No training data. Run mlb_collect.py + mlb_features.py first.")
        conn.close()
        exit(1)

    X_train = train_df[feature_cols]
    y_train = train_df[TARGET]
    X_test  = test_df[feature_cols]
    y_test  = test_df[TARGET]

    model = train_model(X_train, y_train)

    if not test_df.empty:
        rmse, _ = evaluate(model, X_test, y_test, feature_cols)
    else:
        train_preds = model.predict(X_train)
        rmse = mean_squared_error(y_train, train_preds) ** 0.5
        print(f"  No test data -- using train RMSE as sigma: {rmse:.2f}")

    print(f"\n-- Saving model ─────────────────────────────────────────")
    with open("mlb_totals_model.pkl", "wb") as f:
        pickle.dump(model, f)
    with open("mlb_totals_features.json", "w") as f:
        json.dump(feature_cols, f)
    with open("mlb_totals_model_std.json", "w") as f:
        json.dump({"rmse": float(rmse)}, f)

    print(f"  Saved mlb_totals_model.pkl, mlb_totals_features.json, mlb_totals_model_std.json")
    print(f"  sigma (RMSE) = {rmse:.2f} runs -- used in P(over/under) Normal CDF")
    print(f"\nNext step: python mlb_totals_predict.py\n")

    conn.close()
