# ── mlb_props_train.py ────────────────────────────────────────────────────────
# Trains XGBoost regression models for MLB player props:
#   - Pitcher strikeouts
#   - Batter hits
#   - Batter total bases
# Usage: python mlb_props_train.py

import sqlite3
import pickle
import json
import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_absolute_error
from mlb_config import MLB_DB_PATH, WEIGHT_HALF_LIFE
from datetime import date as _date

_CURRENT_SEASON = str(_date.today().year)

PITCHER_FEATURE_COLS = [
    "k_last3", "k_last5", "k_last10",
    "ip_last3", "ip_last5",
    "k_per9_last5",
    "walks_last5",
    "era_last5",
    "is_home",
    "days_rest",
    "opp_k_pct_last10",      # how often opponent team strikes out
    "season_k_avg",
]

BATTER_HIT_FEATURE_COLS = [
    "hits_last5", "hits_last10", "hits_last15",
    "ba_last10", "ba_last15",
    "ab_last5",
    "is_home",
    "days_rest",
    "season_hit_avg",
    "opp_era_last5",          # opposing pitcher quality proxy
]

BATTER_TB_FEATURE_COLS = [
    "tb_last5", "tb_last10", "tb_last15",
    "hr_last10",
    "xbh_rate_last10",        # extra base hit rate
    "ab_last5",
    "is_home",
    "days_rest",
    "season_tb_avg",
    "opp_era_last5",
]


def get_conn():
    return sqlite3.connect(MLB_DB_PATH)


# ── Opponent quality lookups (no-lookahead rolling aggregates) ────────────────

def _opp_k_rate_lookup(conn) -> dict:
    """
    Returns {(team_upper, date_iso): rolling_10game_K_rate} computed with a
    one-game shift so the feature is always out-of-sample at train time.
    Uses batter game logs: aggregate strikeouts & at_bats per (team, game_date).
    """
    try:
        df = pd.read_sql(
            "SELECT team, game_date, strikeouts, at_bats FROM mlb_batter_game_logs",
            conn, parse_dates=["game_date"]
        )
    except Exception:
        return {}
    if df.empty:
        return {}

    tg = df.groupby(["team", "game_date"]).agg(
        k=("strikeouts", "sum"),
        ab=("at_bats", "sum")
    ).reset_index()

    lookup = {}
    for team, grp in tg.groupby("team"):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        roll_k  = grp["k"].rolling(10, min_periods=3).sum().shift(1)
        roll_ab = grp["ab"].rolling(10, min_periods=3).sum().shift(1)
        rate = (roll_k / roll_ab.replace(0, np.nan)).fillna(0.22)
        for idx, row in grp.iterrows():
            key = (str(team).upper(), row["game_date"].date().isoformat())
            lookup[key] = float(rate.iloc[idx]) if pd.notna(rate.iloc[idx]) else 0.22
    return lookup


def _opp_era_lookup(conn) -> dict:
    """
    Returns {(team_upper, date_iso): rolling_5start_ERA} computed with a
    one-start shift so the feature is always out-of-sample at train time.
    Filters pitcher logs to starters (IP >= 4) only.
    """
    try:
        df = pd.read_sql(
            "SELECT team, game_date, earned_runs, innings_pitched "
            "FROM mlb_pitcher_game_logs",
            conn, parse_dates=["game_date"]
        )
    except Exception:
        return {}
    if df.empty:
        return {}

    starters = df[df["innings_pitched"] >= 4].copy()
    # One starter per team per game — take the highest-IP row
    tg = (starters
          .sort_values("innings_pitched", ascending=False)
          .groupby(["team", "game_date"])[["earned_runs", "innings_pitched"]]
          .first()
          .reset_index())

    lookup = {}
    for team, grp in tg.groupby("team"):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        roll_er = grp["earned_runs"].rolling(5, min_periods=2).sum().shift(1)
        roll_ip = grp["innings_pitched"].rolling(5, min_periods=2).sum().shift(1)
        era = (roll_er / roll_ip.replace(0, np.nan) * 9).fillna(4.0)
        for idx, row in grp.iterrows():
            key = (str(team).upper(), row["game_date"].date().isoformat())
            lookup[key] = float(era.iloc[idx]) if pd.notna(era.iloc[idx]) else 4.0
    return lookup


# ── Feature builders ──────────────────────────────────────────────────────────

def _build_pitcher_features(conn, opp_k_lookup: dict = None) -> pd.DataFrame:
    df = pd.read_sql("""
        SELECT * FROM mlb_pitcher_game_logs
        ORDER BY player_id, game_date ASC
    """, conn, parse_dates=["game_date"])

    if df.empty:
        return df

    rows = []
    for pid, grp in df.groupby("player_id"):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        for i in range(3, len(grp)):
            hist = grp.iloc[:i]
            cur  = grp.iloc[i]

            # Rolling K averages
            k3  = hist["strikeouts"].tail(3).mean()
            k5  = hist["strikeouts"].tail(5).mean()
            k10 = hist["strikeouts"].tail(10).mean()
            ip3 = hist["innings_pitched"].tail(3).mean()
            ip5 = hist["innings_pitched"].tail(5).mean()
            k9  = (k5 / ip5 * 9) if ip5 > 0 else 0
            w5  = hist["walks"].tail(5).mean()
            er5 = hist["earned_runs"].tail(5).mean()
            ip5_ = hist["innings_pitched"].tail(5).mean()
            era5 = (er5 / ip5_ * 9) if ip5_ > 0 else 0

            season_k = grp[grp["season"] == cur["season"]].iloc[:i]["strikeouts"].mean()

            # Days rest
            prev_date  = hist["game_date"].iloc[-1]
            days_rest  = min((cur["game_date"] - prev_date).days, 10)

            rows.append({
                "player_id":     pid,
                "player_name":   cur["player_name"],
                "game_id":       cur["game_id"],
                "game_date":     cur["game_date"],
                "season":        cur["season"],
                "strikeouts":    cur["strikeouts"],    # target
                "k_last3":       k3,
                "k_last5":       k5,
                "k_last10":      k10,
                "ip_last3":      ip3,
                "ip_last5":      ip5,
                "k_per9_last5":  k9,
                "walks_last5":   w5,
                "era_last5":     era5,
                "is_home":       int(cur["is_home"]),
                "days_rest":     days_rest,
                "opp_k_pct_last10": (opp_k_lookup or {}).get(
                    (str(cur.get("opponent", "")).upper(),
                     cur["game_date"].date().isoformat()), 0.22),
                "season_k_avg":  float(season_k) if pd.notna(season_k) else k5,
            })

    return pd.DataFrame(rows)


def _build_batter_features(conn, opp_era_lookup: dict = None) -> pd.DataFrame:
    df = pd.read_sql("""
        SELECT * FROM mlb_batter_game_logs
        ORDER BY player_id, game_date ASC
    """, conn, parse_dates=["game_date"])

    if df.empty:
        return df

    rows = []
    for pid, grp in df.groupby("player_id"):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        for i in range(5, len(grp)):
            hist = grp.iloc[:i]
            cur  = grp.iloc[i]

            ab5  = hist["at_bats"].tail(5).replace(0, 1).mean()
            h5   = hist["hits"].tail(5).mean()
            h10  = hist["hits"].tail(10).mean()
            h15  = hist["hits"].tail(15).mean()
            ba10 = hist["hits"].tail(10).sum() / max(hist["at_bats"].tail(10).sum(), 1)
            ba15 = hist["hits"].tail(15).sum() / max(hist["at_bats"].tail(15).sum(), 1)
            tb5  = hist["total_bases"].tail(5).mean()
            tb10 = hist["total_bases"].tail(10).mean()
            tb15 = hist["total_bases"].tail(15).mean()
            hr10 = hist["home_runs"].tail(10).mean()
            xbh10_count = (hist["doubles"].tail(10) + hist["triples"].tail(10) + hist["home_runs"].tail(10)).sum()
            xbh_rate10  = xbh10_count / max(hist["at_bats"].tail(10).sum(), 1)

            season_h  = grp[grp["season"] == cur["season"]].iloc[:i]["hits"].mean()
            season_tb = grp[grp["season"] == cur["season"]].iloc[:i]["total_bases"].mean()

            prev_date = hist["game_date"].iloc[-1]
            days_rest = min((cur["game_date"] - prev_date).days, 7)

            base = {
                "player_id":   pid,
                "player_name": cur["player_name"],
                "game_id":     cur["game_id"],
                "game_date":   cur["game_date"],
                "season":      cur["season"],
                "hits":        cur["hits"],
                "total_bases": cur["total_bases"],
                "hits_last5":  h5, "hits_last10": h10, "hits_last15": h15,
                "ba_last10":   ba10, "ba_last15": ba15,
                "ab_last5":    ab5,
                "tb_last5":    tb5, "tb_last10": tb10, "tb_last15": tb15,
                "hr_last10":   hr10,
                "xbh_rate_last10": xbh_rate10,
                "is_home":     int(cur["is_home"]),
                "days_rest":   days_rest,
                "season_hit_avg": float(season_h)  if pd.notna(season_h)  else h10,
                "season_tb_avg":  float(season_tb) if pd.notna(season_tb) else tb10,
                "opp_era_last5": (opp_era_lookup or {}).get(
                    (str(cur.get("opponent", "")).upper(),
                     cur["game_date"].date().isoformat()), 4.0),
            }
            rows.append(base)

    return pd.DataFrame(rows)


# ── Training ──────────────────────────────────────────────────────────────────

def _time_weights(dates):
    """Exponential decay: games WEIGHT_HALF_LIFE days old get 0.5x weight."""
    today    = pd.Timestamp.today().normalize()
    days_old = (today - pd.to_datetime(dates)).dt.days.clip(lower=0).values
    return np.exp(-np.log(2) / WEIGHT_HALF_LIFE * days_old)


def _train_model(X, y, label, sample_weight=None):
    model = XGBRegressor(
        n_estimators=400, max_depth=4, learning_rate=0.04,
        subsample=0.8, colsample_bytree=0.75, min_child_weight=5,
        reg_alpha=0.1, reg_lambda=1.0, random_state=42, n_jobs=-1,
    )
    cv = cross_val_score(model, X, y, cv=5,
                         scoring="neg_mean_absolute_error", n_jobs=-1)
    print(f"  {label} | CV MAE: {-cv.mean():.3f} ± {cv.std():.3f}")
    model.fit(X, y, sample_weight=sample_weight)
    return model


def train_pitcher_k(conn, opp_k_lookup: dict = None):
    print("\n── Pitcher Strikeouts Model ────────────────────────────────────────────")
    df = _build_pitcher_features(conn, opp_k_lookup)
    if df.empty or len(df) < 50:
        print("  Not enough pitcher data. Run mlb_props_collect.py first.")
        return None, None, 1.5

    fc = [c for c in PITCHER_FEATURE_COLS if c in df.columns]
    df = df.dropna(subset=["strikeouts"])
    df[fc] = df[fc].fillna(0)

    w     = _time_weights(df["game_date"])
    X, y  = df[fc].values, df["strikeouts"].values
    model = _train_model(X, y, "Pitcher K's", sample_weight=w)
    recent = df[df["season"] == df["season"].max()]
    sigma  = float(recent["strikeouts"].std()) if len(recent) > 20 else float(df["strikeouts"].std())
    sigma  = sigma or 1.5
    print(f"  sigma={sigma:.3f} (from {df['season'].max()} season, n={len(recent)})")

    test = df[df["season"] == _CURRENT_SEASON]
    if len(test) > 20:
        mae = mean_absolute_error(test["strikeouts"], model.predict(test[fc]))
        print(f"  Test MAE (2026): {mae:.3f} K's")

    with open("mlb_k_model.pkl", "wb") as f:
        pickle.dump(model, f)
    meta = {"feature_cols": fc, "sigma": sigma, "market": "pitcher_strikeouts",
            "trained_at": pd.Timestamp.now().isoformat()}
    with open("mlb_k_model_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Saved mlb_k_model.pkl  (sigma={sigma:.2f})")
    return model, fc, sigma


def train_batter_hits(conn, opp_era_lookup: dict = None):
    print("\n── Batter Hits Model ───────────────────────────────────────────────────")
    df = _build_batter_features(conn, opp_era_lookup)
    if df.empty or len(df) < 50:
        print("  Not enough batter data. Run mlb_props_collect.py first.")
        return None, None, 0.5

    fc = [c for c in BATTER_HIT_FEATURE_COLS if c in df.columns]
    df = df.dropna(subset=["hits"])
    df[fc] = df[fc].fillna(0)

    w     = _time_weights(df["game_date"])
    X, y  = df[fc].values, df["hits"].values
    model = _train_model(X, y, "Batter Hits", sample_weight=w)
    recent = df[df["season"] == df["season"].max()]
    sigma  = float(recent["hits"].std()) if len(recent) > 20 else float(df["hits"].std())
    sigma  = sigma or 0.6
    print(f"  sigma={sigma:.3f} (from {df['season'].max()} season, n={len(recent)})")

    with open("mlb_hits_model.pkl", "wb") as f:
        pickle.dump(model, f)
    meta = {"feature_cols": fc, "sigma": sigma, "market": "batter_hits",
            "trained_at": pd.Timestamp.now().isoformat()}
    with open("mlb_hits_model_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Saved mlb_hits_model.pkl  (sigma={sigma:.2f})")
    return model, fc, sigma


def train_batter_tb(conn, opp_era_lookup: dict = None):
    print("\n── Batter Total Bases Model ────────────────────────────────────────────")
    df = _build_batter_features(conn, opp_era_lookup)
    if df.empty or len(df) < 50:
        print("  Not enough batter data.")
        return None, None, 1.0

    fc = [c for c in BATTER_TB_FEATURE_COLS if c in df.columns]
    df = df.dropna(subset=["total_bases"])
    df[fc] = df[fc].fillna(0)

    w     = _time_weights(df["game_date"])
    X, y  = df[fc].values, df["total_bases"].values
    model = _train_model(X, y, "Batter TB", sample_weight=w)
    recent = df[df["season"] == df["season"].max()]
    sigma  = float(recent["total_bases"].std()) if len(recent) > 20 else float(df["total_bases"].std())
    sigma  = sigma or 1.0
    print(f"  sigma={sigma:.3f} (from {df['season'].max()} season, n={len(recent)})")

    with open("mlb_tb_model.pkl", "wb") as f:
        pickle.dump(model, f)
    meta = {"feature_cols": fc, "sigma": sigma, "market": "batter_total_bases",
            "trained_at": pd.Timestamp.now().isoformat()}
    with open("mlb_tb_model_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Saved mlb_tb_model.pkl  (sigma={sigma:.2f})")
    return model, fc, sigma


def main():
    print("── MLB Props Model Training ──────────────────────────────────────────────")
    conn = get_conn()

    print("  Building opponent quality lookups...")
    opp_k_lookup  = _opp_k_rate_lookup(conn)
    opp_era_lookup = _opp_era_lookup(conn)
    print(f"  opp_k_rate lookup: {len(opp_k_lookup):,} entries")
    print(f"  opp_era   lookup: {len(opp_era_lookup):,} entries")

    train_pitcher_k(conn, opp_k_lookup)
    train_batter_hits(conn, opp_era_lookup)
    train_batter_tb(conn, opp_era_lookup)
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
