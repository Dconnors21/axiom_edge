# ── train_spread.py ────────────────────────────────────────────────────────────
# Trains an XGBoost regressor to predict NBA home point differential (home margin).
# Used by spread_predict.py to estimate cover probability via Normal CDF.
#
# Usage: python train_spread.py

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

# Same features as the moneyline model — all pre-game, no outcome leakage
FEATURE_COLS = [
    "home_pts_last5", "home_pts_last10",
    "away_pts_last5", "away_pts_last10",
    "home_opp_pts_last5", "home_opp_pts_last10",
    "away_opp_pts_last5", "away_opp_pts_last10",
    "h2h_home_win_rate",
    "h2h_avg_point_diff",
    "h2h_meetings",
    "h2h_home_avg_pts",
    "h2h_away_avg_pts",
    "h2h_home_cover_rate",
    "h2h_last3_pdiff",
    "home_fg_pct_last5",  "home_fg_pct_last10",
    "away_fg_pct_last5",  "away_fg_pct_last10",
    "home_fg3_pct_last5", "home_fg3_pct_last10",
    "away_fg3_pct_last5", "away_fg3_pct_last10",
    "home_win_last5", "home_win_last10",
    "away_win_last5", "away_win_last10",
    "home_reb_last10", "away_reb_last10",
    "home_ast_last10", "away_ast_last10",
    "home_tov_last10", "away_tov_last10",
    "home_stl_last10", "away_stl_last10",
    "home_rest_days", "away_rest_days",
    "home_is_b2b",    "away_is_b2b",
    "home_win_streak", "away_win_streak",
    "home_season_win_pct", "away_season_win_pct",
    "home_pace_last5", "away_pace_last5",
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
    "home_advantage",
]

TARGET = "home_margin"


def get_conn():
    return sqlite3.connect(DB_PATH)


def load_matchups(conn):
    df = pd.read_sql("SELECT * FROM matchups", conn, parse_dates=["game_date"])

    # Derive home margin from actual game pts columns
    if "home_pts" in df.columns and "away_pts" in df.columns:
        df[TARGET] = df["home_pts"] - df["away_pts"]
    elif "home_point_diff" in df.columns:
        # point_diff is pts - opp_pts for the home team, same thing
        df[TARGET] = df["home_point_diff"]
    else:
        raise ValueError("Cannot find pts columns to compute home margin. Run features.py first.")

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
    print(f"  CV RMSE: {-cv_rmse.mean():.2f} ± {cv_rmse.std():.2f} points")

    model.fit(X_train, y_train)
    return model


def evaluate(model, X_test, y_test, feature_cols):
    preds = model.predict(X_test)

    mae  = mean_absolute_error(y_test, preds)
    rmse = mean_squared_error(y_test, preds) ** 0.5
    r2   = r2_score(y_test, preds)

    print(f"\n── Test set performance (2025-26 season) ────────────────")
    print(f"  MAE  (avg error) : {mae:.2f} points")
    print(f"  RMSE             : {rmse:.2f} points  ← used as σ in P(cover)")
    print(f"  R²               : {r2:.4f}  (0 = mean-only baseline)")

    # Direction accuracy: how often does model predict correct winner?
    dir_acc = ((preds > 0) == (y_test > 0)).mean()
    print(f"  Direction acc    : {dir_acc:.1%}")

    # Feature importance
    try:
        importances = pd.Series(
            model.feature_importances_, index=feature_cols
        ).sort_values(ascending=False)
        print(f"\n── Top 15 most important features ───────────────────────")
        for feat, imp in importances.head(15).items():
            bar = "█" * int(imp * 200)
            print(f"  {feat:<35} {imp:.4f} {bar}")
    except Exception:
        pass

    return rmse, preds


def simulate_ats(df_test, preds, rmse):
    """Quick backtest using synthetic -110 lines (no historical spreads stored)."""
    from scipy.stats import norm

    df = df_test.copy()
    df["pred_margin"] = preds
    # Synthetic spread = 0 (pick'em) to isolate model vs fair line
    # In practice, book spread will vary. This just shows raw P(cover) quality.
    df["synthetic_spread"] = 0.0
    df["p_cover"] = norm.cdf((df["pred_margin"] - df["synthetic_spread"]) / rmse)
    df["implied_vig"] = 0.5238   # -110 standard
    df["ats_edge"]    = df["p_cover"] - df["implied_vig"]
    df["value"]       = df["ats_edge"] > 0.03

    value = df[df["value"]]
    if value.empty:
        print("  No ATS value bets in test set at synthetic pick'em line.")
        return

    actual_covers = (value["home_margin"] > value["synthetic_spread"]).mean()
    model_prob    = value["p_cover"].mean()

    print(f"\n── ATS simulation (synthetic pick'em, edge > 3%) ─────────")
    print(f"  Flagged bets     : {len(value)}")
    print(f"  Avg model P(cvr) : {model_prob:.1%}")
    print(f"  Actual cover rate: {actual_covers:.1%}")
    print(f"  Avg pred margin  : {value['pred_margin'].mean():+.1f} pts")


if __name__ == "__main__":
    print("\n── NBA Spread Train ─────────────────────────────────────")

    conn = get_conn()
    df, feature_cols = load_matchups(conn)

    print(f"  Total matchups : {len(df):,}")
    print(f"  Avg home margin: {df[TARGET].mean():+.2f} pts (home court advantage)")
    print(f"  Std home margin: {df[TARGET].std():.2f} pts")
    print(f"  Features used  : {len(feature_cols)}")

    train_df, test_df = split_by_season(df)
    print(f"  Train set      : {len(train_df):,} games")
    print(f"  Test set       : {len(test_df):,} games")

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
        simulate_ats(test_df, preds, rmse)
    else:
        # No 2025-26 test data — compute RMSE on training set as fallback σ estimate
        train_preds = model.predict(X_train)
        rmse = mean_squared_error(y_train, train_preds) ** 0.5
        print(f"  No test data — using train RMSE as σ: {rmse:.2f}")

    print(f"\n── Saving model ─────────────────────────────────────────")
    with open("spread_model.pkl", "wb") as f:
        pickle.dump(model, f)
    with open("spread_features.json", "w") as f:
        json.dump(feature_cols, f)
    with open("spread_model_std.json", "w") as f:
        json.dump({"rmse": float(rmse)}, f)

    print(f"  Saved spread_model.pkl, spread_features.json, spread_model_std.json")
    print(f"  σ (RMSE) = {rmse:.2f} pts — used in P(cover) Normal CDF")
    print(f"\nNext step: python spread_predict.py\n")

    conn.close()
