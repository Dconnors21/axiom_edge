# ── nhl_train.py ──────────────────────────────────────────────────────────────
# Trains XGBoost moneyline model on NHL game data.
# Usage: python nhl_train.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from xgboost import XGBClassifier
from sklearn.model_selection import cross_val_score
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, roc_auc_score, log_loss, brier_score_loss
from nhl_config import NHL_DB_PATH, FEATURE_COLS, TARGET, WEIGHT_HALF_LIFE

def get_conn():
    return sqlite3.connect(NHL_DB_PATH)

def load_data(conn):
    df = pd.read_sql("SELECT * FROM nhl_games_featured", conn,
                     parse_dates=["game_date"])
    available = [c for c in FEATURE_COLS if c in df.columns]
    missing   = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        print(f"  Missing features: {missing[:5]}...")
    df = df.dropna(subset=[TARGET])
    df[available] = df[available].fillna(df[available].median())
    # Exclude playoffs for moneyline (optional: include for more data)
    df = df[df.get("game_type", pd.Series(2, index=df.index)) != 3] if "game_type" in df.columns else df
    print(f"  Loaded {len(df):,} games | Features: {len(available)}")
    return df, available

def _time_weights(dates):
    today    = pd.Timestamp.today().normalize()
    days_old = (today - pd.to_datetime(dates)).dt.days.clip(lower=0).values
    return np.exp(-np.log(2) / WEIGHT_HALF_LIFE * days_old)


def split(df):
    train = df[df["season"].isin(["20222023", "20232024", "20242025"])].copy()
    test  = df[df["season"] == "20252026"].copy()
    return train, test

def train(X_train, y_train, sample_weight=None):
    print("  Training XGBoost (moneyline)...")
    model = XGBClassifier(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.04,
        subsample=0.8,
        colsample_bytree=0.75,
        min_child_weight=5,
        gamma=0.1,
        reg_alpha=0.1,
        reg_lambda=1.0,
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

def evaluate(model, X_test, y_test):
    if len(X_test) == 0:
        print("  No test data (2025-26 season not started yet in DB)")
        return
    probs = model.predict_proba(X_test)[:, 1]
    preds = (probs >= 0.5).astype(int)
    acc   = accuracy_score(y_test, preds)
    auc   = roc_auc_score(y_test, probs)
    ll    = log_loss(y_test, probs)
    bs    = brier_score_loss(y_test, probs)
    print(f"\n── Test set (2025-26 season) ─────────────────────────────")
    print(f"  Accuracy    : {acc:.1%}")
    print(f"  ROC-AUC     : {auc:.4f}")
    print(f"  Log loss    : {ll:.4f}")
    print(f"  Brier score : {bs:.4f}")

def main():
    print("── NHL Moneyline Model Training ──────────────────────────────────────────")
    conn = get_conn()
    df, feature_cols = load_data(conn)
    conn.close()

    if df.empty or len(feature_cols) == 0:
        print("  Not enough data. Run nhl_collect.py + nhl_features.py first.")
        return

    train_df, test_df = split(df)
    w_train = _time_weights(train_df["game_date"])
    print(f"  Weight range   : {w_train.min():.3f} – {w_train.max():.3f} (decay half-life={WEIGHT_HALF_LIFE}d)")
    X_train = train_df[feature_cols].values
    y_train = train_df[TARGET].values
    X_test  = test_df[feature_cols].values  if len(test_df) > 0 else np.array([]).reshape(0, len(feature_cols))
    y_test  = test_df[TARGET].values if len(test_df) > 0 else np.array([])

    model = train(X_train, y_train, sample_weight=w_train)
    evaluate(model, X_test, y_test)

    # Save model + metadata
    with open("nhl_model.pkl", "wb") as f:
        pickle.dump(model, f)
    meta = {"feature_cols": feature_cols, "trained_at": pd.Timestamp.now().isoformat()}
    with open("nhl_model_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n  Saving nhl_model.pkl ({len(feature_cols)} features)")
    print("Done.")

if __name__ == "__main__":
    main()
