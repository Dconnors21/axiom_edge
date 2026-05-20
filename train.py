# ── train.py ──────────────────────────────────────────────────────────────────
# Trains an XGBoost classifier to predict NBA game outcomes.
# Evaluates on held-out season, saves model + feature list to disk.
#
# Usage: python train.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from pathlib import Path
from xgboost import XGBClassifier
from sklearn.model_selection import cross_val_score
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score, log_loss, brier_score_loss, roc_auc_score
)
from config import DB_PATH

def get_conn():
    return sqlite3.connect(DB_PATH)

# ── Feature selection ─────────────────────────────────────────────────────────

# These are features available BEFORE the game starts
# Excludes anything that requires knowing the game outcome
FEATURE_COLS = [
    # Rolling scoring
    "home_pts_last5", "home_pts_last10",
    "away_pts_last5", "away_pts_last10",
    "home_opp_pts_last5", "home_opp_pts_last10",
    "away_opp_pts_last5", "away_opp_pts_last10",

    # H2H features
    "h2h_home_win_rate",
    "h2h_avg_point_diff",
    "h2h_meetings",
    "h2h_home_avg_pts",
    "h2h_away_avg_pts",
    "h2h_home_cover_rate",
    "h2h_last3_pdiff",

    # Rolling shooting
    "home_fg_pct_last5",  "home_fg_pct_last10",
    "away_fg_pct_last5",  "away_fg_pct_last10",
    "home_fg3_pct_last5", "home_fg3_pct_last10",
    "away_fg3_pct_last5", "away_fg3_pct_last10",

    # Rolling win rates
    "home_win_last5", "home_win_last10",
    "away_win_last5", "away_win_last10",

    # Rolling other stats
    "home_reb_last10", "away_reb_last10",
    "home_ast_last10", "away_ast_last10",
    "home_tov_last10", "away_tov_last10",
    "home_stl_last10", "away_stl_last10",

    # Rest
    "home_rest_days", "away_rest_days",
    "home_is_b2b",    "away_is_b2b",

    # Streak
    "home_win_streak", "away_win_streak",

    # Season standing
    "home_season_win_pct", "away_season_win_pct",

    # Pace
    "home_pace_last5", "away_pace_last5",

    # Differential features (most predictive)
    "pts_diff_last5",       "pts_diff_last10",
    "pdiff_diff_last5",     "pdiff_diff_last10",
    "win_rate_diff_last5",  "win_rate_diff_last10",
    "season_win_pct_diff",
    "rest_days_diff",
    "streak_diff",
    "fg_pct_diff",
    "fg3_pct_diff",
    "tov_diff",
    "ast_diff",
    "reb_diff",
    "pace_diff",

    # Home court
    "home_advantage",
]

TARGET = "home_win"

# ── Load and prepare data ─────────────────────────────────────────────────────

def load_matchups(conn):
    df = pd.read_sql("SELECT * FROM matchups", conn, parse_dates=["game_date"])

    # Only keep columns that exist in this dataset
    available = [c for c in FEATURE_COLS if c in df.columns]
    missing   = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        print(f"  Note: {len(missing)} feature(s) not found, skipping: {missing[:5]}...")

    df = df.dropna(subset=[TARGET])
    df[available] = df[available].fillna(df[available].median())
    return df, available

# ── Train / test split ────────────────────────────────────────────────────────

def split_by_season(df):
    train = df[df["season"].isin(["2023-24", "2024-25"])].copy()
    test  = df[df["season"] == "2025-26"].copy()
    return train, test

# ── Model training ────────────────────────────────────────────────────────────

def train_model(X_train, y_train):
    print("  Training XGBoost classifier...")

    model = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        gamma=0.1,
        reg_alpha=0.1,
        reg_lambda=1.0,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )

    # Cross-validation on training set
    cv_scores = cross_val_score(model, X_train, y_train, cv=5,
                                scoring="roc_auc", n_jobs=-1)
    print(f"  CV ROC-AUC: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

    # Calibrate probabilities — important for EV calculations
    # Raw XGBoost probabilities can be overconfident
    calibrated = CalibratedClassifierCV(model, cv=5, method="isotonic")
    calibrated.fit(X_train, y_train)

    return calibrated

# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate(model, X_test, y_test, feature_cols):
    probs = model.predict_proba(X_test)[:, 1]
    preds = (probs >= 0.5).astype(int)

    acc      = accuracy_score(y_test, preds)
    ll       = log_loss(y_test, probs)
    brier    = brier_score_loss(y_test, probs)
    auc      = roc_auc_score(y_test, probs)

    print(f"\n── Test set performance (2024-25 season) ────────────────")
    print(f"  Accuracy       : {acc:.1%}")
    print(f"  ROC-AUC        : {auc:.4f}  (0.5 = random, 1.0 = perfect)")
    print(f"  Log loss       : {ll:.4f}   (lower = better)")
    print(f"  Brier score    : {brier:.4f} (lower = better)")

    # Feature importance from the base estimator
    try:
        base_model = model.estimator if hasattr(model, 'estimator') else model.calibrated_classifiers_[0].estimator
        importances = pd.Series(
            base_model.feature_importances_,
            index=feature_cols
        ).sort_values(ascending=False)

        print(f"\n── Top 15 most important features ───────────────────────")
        for feat, imp in importances.head(15).items():
            bar = "█" * int(imp * 200)
            print(f"  {feat:<35} {imp:.4f} {bar}")
    except Exception:
        print("  (Feature importance not available for calibrated model)")

    return acc, auc, probs

# ── Simulate value betting on test set ───────────────────────────────────────

def simulate_value_bets(df_test, probs, min_edge=0.03):
    """
    Quick backtest: if we had used this model on 2024-25 games,
    how would value bets have performed?
    We use a synthetic line of -110 (52.4% implied) as a proxy
    since we don't have historical odds stored for all games.
    """
    df = df_test.copy()
    df["model_prob"] = probs
    df["implied_prob"] = 0.524   # -110 line standard vig
    df["edge"] = df["model_prob"] - df["implied_prob"]
    df["value_bet"] = df["edge"] > min_edge

    value = df[df["value_bet"]].copy()
    if len(value) == 0:
        print("  No value bets found in test set.")
        return

    wins    = value["home_win"].sum()
    total   = len(value)
    win_pct = wins / total

    # Simulate flat $100 bets at -110 (win $90.91 or lose $100)
    profit = wins * 90.91 - (total - wins) * 100
    roi    = profit / (total * 100) * 100

    print(f"\n── Value bet simulation (2025-26, edge > {min_edge:.0%}) ─────")
    print(f"  Flagged bets   : {total}")
    print(f"  Win rate       : {win_pct:.1%}  (need >52.4% to beat -110)")
    print(f"  Simulated ROI  : {roi:+.1f}%  (flat $100 bets at -110)")
    print(f"  Avg model edge : {value['edge'].mean():.1%}")
    print(f"  Avg model prob : {value['model_prob'].mean():.1%}")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n── NBA Train ────────────────────────────────────────────")

    conn = get_conn()
    df, feature_cols = load_matchups(conn)

    print(f"  Total matchups : {len(df):,}")
    print(f"  Features used  : {len(feature_cols)}")

    train_df, test_df = split_by_season(df)
    print(f"  Train set      : {len(train_df):,} games ({train_df['season'].unique()})")
    print(f"  Test set       : {len(test_df):,} games ({test_df['season'].unique()})")

    X_train = train_df[feature_cols]
    y_train = train_df[TARGET]
    X_test  = test_df[feature_cols]
    y_test  = test_df[TARGET]

    # Train
    model = train_model(X_train, y_train)

    # Evaluate
    acc, auc, probs = evaluate(model, X_test, y_test, feature_cols)

    # Value bet simulation
    simulate_value_bets(test_df, probs)

    # Save model and feature list
    print(f"\n── Saving model ─────────────────────────────────────────")
    with open("model.pkl", "wb") as f:
        pickle.dump(model, f)
    with open("features.json", "w") as f:
        json.dump(feature_cols, f)

    print(f"  Saved model.pkl and features.json")
    print(f"\nNext step: python predict.py\n")

    conn.close()
