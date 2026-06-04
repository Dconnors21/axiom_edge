# ── nhl_train_totals.py ───────────────────────────────────────────────────────
# Trains XGBoost over/under model for NHL total goals.
# Usage: python nhl_train_totals.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from xgboost import XGBRegressor
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from nhl_config import NHL_DB_PATH, FEATURE_COLS, WEIGHT_HALF_LIFE
from datetime import date as _date

def _current_nhl_season() -> str:
    # NHL season spans Oct–Jun; before August belongs to the prior start-year.
    t = _date.today()
    start = t.year if t.month >= 8 else t.year - 1
    return f"{start}{start + 1}"

_CURRENT_SEASON = _current_nhl_season()

TOTALS_TARGET = "total_goals"

# Totals-specific features (remove win-based features, add goal-scoring-specific)
TOTALS_FEATURE_COLS = [
    "home_goals_scored_last5",  "home_goals_scored_last15",
    "away_goals_scored_last5",  "away_goals_scored_last15",
    "home_goals_allowed_last5", "home_goals_allowed_last15",
    "away_goals_allowed_last5", "away_goals_allowed_last15",
    "home_shots_last5",         "home_shots_last15",
    "away_shots_last5",         "away_shots_last15",
    "home_shots_against_last5", "home_shots_against_last15",
    "away_shots_against_last5", "away_shots_against_last15",
    "home_pp_pct_last10",       "away_pp_pct_last10",
    "home_save_pct_last5",      "away_save_pct_last5",
    "home_rest_days",           "away_rest_days",
    "home_win_streak",          "away_win_streak",
    "home_advantage",
]

def get_conn():
    return sqlite3.connect(NHL_DB_PATH)

def load_data(conn):
    df = pd.read_sql("SELECT * FROM nhl_games_featured", conn,
                     parse_dates=["game_date"])
    available = [c for c in TOTALS_FEATURE_COLS if c in df.columns]
    missing   = [c for c in TOTALS_FEATURE_COLS if c not in df.columns]
    if missing:
        print(f"  Missing totals features: {missing[:5]}...")
    df = df.dropna(subset=[TOTALS_TARGET])
    df[available] = df[available].fillna(df[available].median())
    print(f"  Loaded {len(df):,} games | Avg total: {df[TOTALS_TARGET].mean():.2f}")
    return df, available

def _time_weights(dates):
    today    = pd.Timestamp.today().normalize()
    days_old = (today - pd.to_datetime(dates)).dt.days.clip(lower=0).values
    return np.exp(-np.log(2) / WEIGHT_HALF_LIFE * days_old)


def split(df):
    seasons = sorted(s for s in df["season"].dropna().astype(str).unique()
                     if s != _CURRENT_SEASON)
    train = df[df["season"].astype(str).isin(seasons)].copy()
    test  = df[df["season"].astype(str) == _CURRENT_SEASON].copy()
    return train, test

def train_model(X_train, y_train, sample_weight=None):
    print("  Training XGBoost (totals)...")
    model = XGBRegressor(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.04,
        subsample=0.8,
        colsample_bytree=0.75,
        min_child_weight=5,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
    )
    cv = cross_val_score(model, X_train, y_train, cv=5,
                         scoring="neg_mean_absolute_error", n_jobs=-1)
    print(f"  CV MAE: {-cv.mean():.3f} ± {cv.std():.3f}")
    model.fit(X_train, y_train, sample_weight=sample_weight)
    return model

def main():
    print("── NHL Totals Model Training ─────────────────────────────────────────────")
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
    y_train = train_df[TOTALS_TARGET].values

    model = train_model(X_train, y_train, sample_weight=w_train)

    if len(test_df) > 0:
        preds = model.predict(test_df[feature_cols].values)
        mae   = mean_absolute_error(test_df[TOTALS_TARGET].values, preds)
        rmse  = float(mean_squared_error(test_df[TOTALS_TARGET].values, preds) ** 0.5)
        r2    = r2_score(test_df[TOTALS_TARGET].values, preds)
        print(f"  Test MAE: {mae:.3f} goals | RMSE (sigma): {rmse:.3f} | R2: {r2:.4f}")
        print(f"  Avg pred: {preds.mean():.2f} | Avg actual: {test_df[TOTALS_TARGET].mean():.2f}")
    else:
        # Fallback: use recent training data std as sigma estimate
        rmse = float(train_df[TOTALS_TARGET].std()) if TOTALS_TARGET in train_df.columns else 1.4
        r2   = 0.0
        print(f"  No test data — using training std as sigma: {rmse:.3f}")

    # Shrinkage skill factor (see mlb_train_totals.py): R2<=0 -> shrink fully to
    # the market line, suppressing noise-manufactured edges; auto-reactivates >0.
    skill = max(0.0, float(r2))
    print(f"  Skill factor (max(0,R2)) = {skill:.3f}  "
          f"(0 => predictions collapse to market line, no bets)")

    with open("nhl_totals_model.pkl", "wb") as f:
        pickle.dump(model, f)
    meta = {"feature_cols": feature_cols, "target": TOTALS_TARGET,
            "rmse": rmse, "skill": skill,
            "trained_at": pd.Timestamp.now().isoformat()}
    with open("nhl_totals_model_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  sigma (RMSE) = {rmse:.3f} goals — used in P(over/under) Normal CDF")

    print(f"  Saving nhl_totals_model.pkl ({len(feature_cols)} features)")
    print("Done.")

if __name__ == "__main__":
    main()
