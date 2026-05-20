# ── mlb_train.py ──────────────────────────────────────────────────────────────
# Trains XGBoost model on MLB game data.
# Usage: python mlb_train.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from xgboost import XGBClassifier
from sklearn.model_selection import cross_val_score
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, roc_auc_score, log_loss, brier_score_loss
from mlb_config import MLB_DB_PATH, FEATURE_COLS, TARGET

def get_conn():
    return sqlite3.connect(MLB_DB_PATH)

def load_data(conn):
    df = pd.read_sql("SELECT * FROM mlb_games_featured", conn,
                     parse_dates=["game_date"])
    available = [c for c in FEATURE_COLS if c in df.columns]
    missing   = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        print(f"  Missing features: {missing[:5]}...")
    df = df.dropna(subset=[TARGET])
    df[available] = df[available].fillna(df[available].median())
    print(f"  Loaded {len(df):,} games | Features: {len(available)}")
    return df, available

def split(df):
    train = df[df["season"].isin(["2023","2024","2025"])].copy()
    test  = df[df["season"] == "2026"].copy()
    return train, test

def train(X_train, y_train):
    print("  Training XGBoost...")
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
    calibrated.fit(X_train, y_train)
    return calibrated

def evaluate(model, X_test, y_test, feature_cols):
    probs = model.predict_proba(X_test)[:,1]
    preds = (probs >= 0.5).astype(int)
    acc   = accuracy_score(y_test, preds)
    auc   = roc_auc_score(y_test, probs)
    ll    = log_loss(y_test, probs)
    bs    = brier_score_loss(y_test, probs)

    print(f"\n── Test set performance (2026 season) ───────────────────")
    print(f"  Accuracy    : {acc:.1%}")
    print(f"  ROC-AUC     : {auc:.4f}")
    print(f"  Log loss    : {ll:.4f}")
    print(f"  Brier score : {bs:.4f}")

    # Value bet simulation
    df_sim = pd.DataFrame({"prob": probs, "actual": y_test.values})
    df_sim["implied"] = 0.524
    df_sim["edge"]    = df_sim["prob"] - df_sim["implied"]
    value = df_sim[df_sim["edge"] > 0.03]
    if len(value) > 0:
        wr  = value["actual"].mean()
        roi = (value["actual"].sum() * 90.91 -
               (len(value) - value["actual"].sum()) * 100) / (len(value)*100) * 100
        print(f"\n── Value bet simulation (edge > 3%) ─────────────────────")
        print(f"  Flagged bets : {len(value)}")
        print(f"  Win rate     : {wr:.1%}")
        print(f"  Simulated ROI: {roi:+.1f}%")

    # Feature importance
    try:
        base = model.calibrated_classifiers_[0].estimator
        imps = pd.Series(base.feature_importances_, index=feature_cols)\
                 .sort_values(ascending=False)
        print(f"\n── Top 12 features ──────────────────────────────────────")
        for feat, imp in imps.head(12).items():
            bar = "█" * int(imp * 300)
            print(f"  {feat:<38} {imp:.4f} {bar}")
    except Exception:
        pass

    return auc, probs

if __name__ == "__main__":
    print("\n── MLB Train ────────────────────────────────────────────")
    conn = get_conn()
    df, feature_cols = load_data(conn)

    train_df, test_df = split(df)
    print(f"  Train: {len(train_df):,} | Test: {len(test_df):,}")

    if test_df.empty:
        print("  No 2025 data yet — run mlb_collect.py first.")
        exit()

    X_train = train_df[feature_cols]
    y_train = train_df[TARGET]
    X_test  = test_df[feature_cols]
    y_test  = test_df[TARGET]

    model = train(X_train, y_train)
    auc, probs = evaluate(model, X_test, y_test, feature_cols)

    print(f"\n── Saving ───────────────────────────────────────────────")
    with open("mlb_model.pkl","wb") as f: pickle.dump(model, f)
    with open("mlb_features.json","w") as f: json.dump(feature_cols, f)
    print(f"  Saved mlb_model.pkl and mlb_features.json")
    print(f"  Next step: python mlb_odds.py && python mlb_predict.py")
    conn.close()