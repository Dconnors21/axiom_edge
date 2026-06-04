# ── nhl_train_spread.py ───────────────────────────────────────────────────────
# Trains XGBoost puck-line model (home team covers ±1.5 spread).
# Usage: python nhl_train_spread.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from xgboost import XGBClassifier
from sklearn.model_selection import cross_val_score
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, roc_auc_score
from nhl_config import NHL_DB_PATH, FEATURE_COLS, TARGET, WEIGHT_HALF_LIFE

SPREAD_TARGET = "home_covered_puckline"  # home won by 2+ goals

def get_conn():
    return sqlite3.connect(NHL_DB_PATH)

def load_data(conn):
    df = pd.read_sql("SELECT * FROM nhl_games_featured", conn,
                     parse_dates=["game_date"])
    available = [c for c in FEATURE_COLS if c in df.columns]
    df = df.dropna(subset=["home_score", "away_score"])

    # Puck line: home covers if home wins by 2+ goals
    # If home wins by exactly 1 (regulation) or OT, home LOSES the puckline
    df["goal_diff_abs"] = df["home_score"] - df["away_score"]
    df[SPREAD_TARGET]   = (df["goal_diff_abs"] >= 2).astype(int)

    df = df.dropna(subset=[SPREAD_TARGET])
    df[available] = df[available].fillna(df[available].median())

    cover_rate = df[SPREAD_TARGET].mean()
    print(f"  Loaded {len(df):,} games | Puck line cover rate: {cover_rate:.1%}")
    return df, available

def _time_weights(dates):
    today    = pd.Timestamp.today().normalize()
    days_old = (today - pd.to_datetime(dates)).dt.days.clip(lower=0).values
    return np.exp(-np.log(2) / WEIGHT_HALF_LIFE * days_old)


def split(df):
    train = df[df["season"].isin(["20222023", "20232024", "20242025"])].copy()
    test  = df[df["season"] == "20252026"].copy()
    return train, test

def train_model(X_train, y_train, sample_weight=None):
    print("  Training XGBoost (puck line)...")
    model = XGBClassifier(
        n_estimators=350,
        max_depth=4,
        learning_rate=0.04,
        subsample=0.8,
        colsample_bytree=0.75,
        min_child_weight=6,
        gamma=0.15,
        reg_alpha=0.1,
        reg_lambda=1.2,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    cv = cross_val_score(model, X_train, y_train, cv=5,
                         scoring="roc_auc", n_jobs=-1)
    print(f"  CV ROC-AUC: {cv.mean():.4f} ± {cv.std():.4f}")
    calibrated = CalibratedClassifierCV(model, cv=5, method="isotonic")
    calibrated.fit(X_train, y_train, sample_weight=sample_weight)
    return calibrated

def main():
    print("── NHL Puck Line Model Training ──────────────────────────────────────────")
    conn = get_conn()
    df, feature_cols = load_data(conn)
    conn.close()

    if df.empty or len(feature_cols) == 0:
        print("  Not enough data.")
        return

    train_df, test_df = split(df)
    w_train = _time_weights(train_df["game_date"])
    print(f"  Weight range   : {w_train.min():.3f} – {w_train.max():.3f} (decay half-life={WEIGHT_HALF_LIFE}d)")
    X_train = train_df[feature_cols].values
    y_train = train_df[SPREAD_TARGET].values
    X_test  = test_df[feature_cols].values  if len(test_df) > 0 else np.array([]).reshape(0, len(feature_cols))
    y_test  = test_df[SPREAD_TARGET].values if len(test_df) > 0 else np.array([])

    model = train_model(X_train, y_train, sample_weight=w_train)

    if len(X_test) > 0 and len(np.unique(y_test)) > 1:
        probs = model.predict_proba(X_test)[:, 1]
        acc   = accuracy_score(y_test, (probs >= 0.5).astype(int))
        auc   = roc_auc_score(y_test, probs)
        print(f"  Test Accuracy: {acc:.1%} | ROC-AUC: {auc:.4f}")

    with open("nhl_spread_model.pkl", "wb") as f:
        pickle.dump(model, f)
    meta = {"feature_cols": feature_cols, "target": SPREAD_TARGET,
            "trained_at": pd.Timestamp.now().isoformat()}
    with open("nhl_spread_model_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"  Saving nhl_spread_model.pkl ({len(feature_cols)} features)")
    print("Done.")

if __name__ == "__main__":
    main()
