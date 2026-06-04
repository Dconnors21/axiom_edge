# ── mlb_train_spread.py ───────────────────────────────────────────────────────
# Trains an XGBoost regressor to predict MLB home run differential.
# Used by mlb_spread_predict.py to estimate run line cover probability.
#
# Usage: python mlb_train_spread.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from xgboost import XGBRegressor
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from mlb_config import MLB_DB_PATH, FEATURE_COLS, WEIGHT_HALF_LIFE
from datetime import date as _date
_CURRENT_SEASON = str(_date.today().year)

TARGET = "home_run_margin"


def get_conn():
    return sqlite3.connect(MLB_DB_PATH)


def load_data(conn):
    df = pd.read_sql("SELECT * FROM mlb_games_featured", conn,
                     parse_dates=["game_date"])

    # Derive home run margin from actual scores
    if "home_score" in df.columns and "away_score" in df.columns:
        df[TARGET] = df["home_score"] - df["away_score"]
    elif "run_diff" in df.columns:
        df[TARGET] = df["run_diff"]
    elif "home_runs_scored" in df.columns and "away_runs_scored" in df.columns:
        df[TARGET] = df["home_runs_scored"] - df["away_runs_scored"]
    else:
        raise ValueError(
            "Cannot compute home run margin — need home_score / away_score columns. "
            "Run mlb_collect.py + mlb_features.py first."
        )

    df = df.dropna(subset=[TARGET])

    available = [c for c in FEATURE_COLS if c in df.columns]
    missing   = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        print(f"  Note: {len(missing)} feature(s) missing, skipping: {missing[:5]}...")

    df[available] = df[available].fillna(df[available].median())
    return df, available


def _time_weights(dates):
    today    = pd.Timestamp.today().normalize()
    days_old = (today - pd.to_datetime(dates)).dt.days.clip(lower=0).values
    return np.exp(-np.log(2) / WEIGHT_HALF_LIFE * days_old)


def split(df):
    train = df[df["season"].isin(["2023", "2024", "2025"])].copy()
    test  = df[df["season"] == _CURRENT_SEASON].copy()
    return train, test


def train_model(X_train, y_train, sample_weight=None):
    print("  Training XGBoost regressor...")
    model = XGBRegressor(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.04,
        subsample=0.8,
        colsample_bytree=0.75,
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
    print(f"  CV RMSE: {-cv_rmse.mean():.2f} ± {cv_rmse.std():.2f} runs")
    model.fit(X_train, y_train, sample_weight=sample_weight)
    return model


def evaluate(model, X_test, y_test, feature_cols):
    preds = model.predict(X_test)
    mae   = mean_absolute_error(y_test, preds)
    rmse  = mean_squared_error(y_test, preds) ** 0.5
    r2    = r2_score(y_test, preds)
    dir_acc = ((preds > 0) == (y_test > 0)).mean()

    print(f"\n── Test set performance (2026 season) ───────────────────")
    print(f"  MAE  (avg error) : {mae:.2f} runs")
    print(f"  RMSE             : {rmse:.2f} runs  <- used as sigma in P(cover)")
    print(f"  R2               : {r2:.4f}")
    print(f"  Direction acc    : {dir_acc:.1%}")

    try:
        imps = pd.Series(model.feature_importances_, index=feature_cols)\
                 .sort_values(ascending=False)
        print(f"\n── Top 12 features ──────────────────────────────────────")
        for feat, imp in imps.head(12).items():
            bar = "x" * int(imp * 300)
            print(f"  {feat:<38} {imp:.4f} {bar}")
    except Exception:
        pass

    return rmse, preds


if __name__ == "__main__":
    print("\n── MLB Run Line Train ───────────────────────────────────")

    conn = get_conn()
    df, feature_cols = load_data(conn)

    print(f"  Total games    : {len(df):,}")
    print(f"  Avg home margin: {df[TARGET].mean():+.2f} runs")
    print(f"  Std home margin: {df[TARGET].std():.2f} runs")
    print(f"  Features used  : {len(feature_cols)}")

    train_df, test_df = split(df)
    print(f"  Train set      : {len(train_df):,} games")
    print(f"  Test set       : {len(test_df):,} games")

    if train_df.empty:
        print("  ERROR: No training data. Run mlb_collect.py + mlb_features.py first.")
        conn.close()
        exit(1)

    X_train = train_df[feature_cols]
    y_train = train_df[TARGET]
    w_train = _time_weights(train_df["game_date"])
    print(f"  Weight range   : {w_train.min():.3f} – {w_train.max():.3f} (decay half-life={WEIGHT_HALF_LIFE}d)")

    model = train_model(X_train, y_train, sample_weight=w_train)

    if not test_df.empty:
        rmse, _ = evaluate(model, test_df[feature_cols], test_df[TARGET], feature_cols)
    else:
        train_preds = model.predict(X_train)
        rmse = mean_squared_error(y_train, train_preds) ** 0.5
        print(f"  No test data — using train RMSE as sigma: {rmse:.2f}")

    print(f"\n── Saving model ─────────────────────────────────────────")
    with open("mlb_spread_model.pkl", "wb") as f:
        pickle.dump(model, f)
    with open("mlb_spread_features.json", "w") as f:
        json.dump(feature_cols, f)
    with open("mlb_spread_model_std.json", "w") as f:
        json.dump({"rmse": float(rmse)}, f)

    print(f"  Saved mlb_spread_model.pkl, mlb_spread_features.json, mlb_spread_model_std.json")
    print(f"  sigma (RMSE) = {rmse:.2f} runs")
    print(f"\nNext step: python mlb_spread_predict.py\n")
    conn.close()
