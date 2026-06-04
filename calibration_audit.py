# ── calibration_audit.py ──────────────────────────────────────────────────────
# Per-market probability-calibration validation on each model's test split.
#
# For CLASSIFIERS (moneyline, NHL puck line): reports Brier, log-loss, ECE and a
#   reliability table (predicted prob vs actual win rate).
# For REGRESSORS (spreads, totals): validates the Normal-CDF mapping that the
#   predict scripts use — residual bias, ±1σ/±2σ coverage vs normal targets, PIT
#   uniformity, and the coverage-calibrated sigma. Flags when the saved sigma is
#   materially off so it can be re-tuned.
#
# This is the institutional "is our P(...) trustworthy?" check. Run it after any
# retrain.  Usage: python calibration_audit.py
#
# Note: totals models currently shrink predictions to the market line (skill=0),
# so their over/under probability is ~0.5 by design until features improve R2.
# This audit still reports the underlying residual calibration of the raw model.

import json
import pickle
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from datetime import date as _date

_NBA_SEASON = "2025-26"
_NHL_SEASON = "20252026"
_MLB_SEASON = str(_date.today().year)


# ── Market registry ───────────────────────────────────────────────────────────
# kind: "clf" (binary classifier) or "reg" (regressor -> Normal CDF).
# target: callable(df) -> Series, derived exactly as the trainer does.
MARKETS = [
    # NBA — db nba.db, table matchups, season 2025-26
    {"name": "NBA Moneyline",  "kind": "clf", "db": "nba.db", "table": "matchups",
     "season": _NBA_SEASON, "model": "model.pkl",        "feats": "features.json",
     "target": lambda d: d["home_win"]},
    {"name": "NBA Spread",     "kind": "reg", "db": "nba.db", "table": "matchups",
     "season": _NBA_SEASON, "model": "spread_model.pkl", "feats": "spread_features.json",
     "sigma": "spread_model_std.json", "target": lambda d: d["home_pts"] - d["away_pts"]},
    {"name": "NBA Totals",     "kind": "reg", "db": "nba.db", "table": "matchups",
     "season": _NBA_SEASON, "model": "totals_model.pkl", "feats": "totals_features.json",
     "sigma": "totals_model_std.json", "target": lambda d: d["home_pts"] + d["away_pts"]},

    # MLB — db mlb.db, table mlb_games_featured, season = current year
    {"name": "MLB Moneyline",  "kind": "clf", "db": "mlb.db", "table": "mlb_games_featured",
     "season": _MLB_SEASON, "model": "mlb_model.pkl",        "feats": "mlb_features.json",
     "target": lambda d: (d["home_score"] > d["away_score"]).astype(int)},
    {"name": "MLB Run Line",   "kind": "reg", "db": "mlb.db", "table": "mlb_games_featured",
     "season": _MLB_SEASON, "model": "mlb_spread_model.pkl", "feats": "mlb_spread_features.json",
     "sigma": "mlb_spread_model_std.json", "target": lambda d: d["home_score"] - d["away_score"]},
    {"name": "MLB Totals",     "kind": "reg", "db": "mlb.db", "table": "mlb_games_featured",
     "season": _MLB_SEASON, "model": "mlb_totals_model.pkl", "feats": "mlb_totals_features.json",
     "sigma": "mlb_totals_model_std.json", "target": lambda d: d["home_score"] + d["away_score"]},

    # NHL — db nhl.db, table nhl_games_featured, season 20252026
    {"name": "NHL Moneyline",  "kind": "clf", "db": "nhl.db", "table": "nhl_games_featured",
     "season": _NHL_SEASON, "model": "nhl_model.pkl",        "feats": "nhl_model_meta.json",
     "target": lambda d: d["home_win"]},
    {"name": "NHL Puck Line",  "kind": "clf", "db": "nhl.db", "table": "nhl_games_featured",
     "season": _NHL_SEASON, "model": "nhl_spread_model.pkl", "feats": "nhl_spread_model_meta.json",
     "target": lambda d: ((d["home_score"] - d["away_score"]) >= 2).astype(int)},
    {"name": "NHL Totals",     "kind": "reg", "db": "nhl.db", "table": "nhl_games_featured",
     "season": _NHL_SEASON, "model": "nhl_totals_model.pkl", "feats": "nhl_totals_model_meta.json",
     "sigma": "nhl_totals_model_meta.json", "target": lambda d: d["home_score"] + d["away_score"]},
]


# ── Calibration metrics ───────────────────────────────────────────────────────
def expected_calibration_error(probs, y, bins=10):
    probs = np.asarray(probs, float)
    y     = np.asarray(y, float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for i in range(bins):
        hi = edges[i + 1]
        m  = (probs >= edges[i]) & ((probs < hi) if i < bins - 1 else (probs <= hi))
        if m.sum():
            ece += m.mean() * abs(y[m].mean() - probs[m].mean())
    return float(ece)


def _load_feature_list(path):
    obj = json.load(open(path))
    if isinstance(obj, dict):
        return obj.get("feature_cols") or obj.get("features") or []
    return obj


def _load_sigma(path):
    obj = json.load(open(path))
    return float(obj.get("rmse", obj.get("sigma", 1.0)))


def _load_test(mkt):
    if not Path(mkt["db"]).exists():
        return None
    conn = sqlite3.connect(mkt["db"])
    try:
        df = pd.read_sql(f"SELECT * FROM {mkt['table']}", conn)
    except Exception:
        return None
    finally:
        conn.close()
    if df.empty or "season" not in df.columns:
        return None
    df["season"] = df["season"].astype(str)
    return df[df["season"] == mkt["season"]].copy()


def _report_classifier(name, probs, y):
    from sklearn.metrics import brier_score_loss, log_loss
    y = np.asarray(y, float)
    print(f"  base rate (actual)   : {y.mean():.3f}")
    print(f"  mean predicted prob  : {probs.mean():.3f}  (bias {probs.mean()-y.mean():+.3f})")
    print(f"  Brier score          : {brier_score_loss(y, probs):.4f}  (lower better)")
    try:
        print(f"  Log loss             : {log_loss(y, np.clip(probs,1e-6,1-1e-6)):.4f}")
    except Exception:
        pass
    ece = expected_calibration_error(probs, y)
    flag = "OK" if ece <= 0.05 else ("WATCH" if ece <= 0.10 else "MISCALIBRATED")
    print(f"  ECE (10-bin)         : {ece:.4f}  [{flag}]")
    print(f"  Reliability (pred -> actual):")
    edges = np.arange(0.30, 0.75, 0.05)
    for lo in edges:
        m = (probs >= lo) & (probs < lo + 0.05)
        if m.sum():
            print(f"    [{lo:.2f}-{lo+0.05:.2f})  n={int(m.sum()):4d}  "
                  f"pred={probs[m].mean():.3f}  actual={y[m].mean():.3f}")


def _report_regressor(name, resid, saved_sigma):
    n = len(resid)
    rstd = float(resid.std())
    bias = float(resid.mean())
    print(f"  saved sigma (RMSE)   : {saved_sigma:.3f}")
    print(f"  residual std         : {rstd:.3f}")
    print(f"  residual mean (bias) : {bias:+.3f}")
    for k, tgt in [(1, 0.6827), (2, 0.9545)]:
        cov = float((np.abs(resid) <= k * saved_sigma).mean())
        print(f"  +/-{k}sigma coverage    : {cov:.3f}  (normal target {tgt:.3f})")
    u = norm.cdf(resid / saved_sigma)
    print(f"  PIT mean / std       : {u.mean():.3f} / {u.std():.3f}  (target 0.500 / 0.289)")
    # Coverage-calibrated sigma: value s.t. P(|resid| <= s) = 0.6827.
    sigma_cov = float(np.quantile(np.abs(resid), 0.6827))
    drift = abs(sigma_cov - saved_sigma) / saved_sigma if saved_sigma else 0.0
    flag = "OK" if drift <= 0.10 else "RETUNE"
    print(f"  coverage-cal sigma   : {sigma_cov:.3f}  (saved off by {drift:.1%})  [{flag}]")
    if flag == "RETUNE":
        print(f"    -> consider setting sigma={sigma_cov:.3f} for calibrated P(over/cover)")


def audit_market(mkt):
    print(f"\n── {mkt['name']} ─────────────────────────────────────────")
    for f in (mkt["model"], mkt["feats"]):
        if not Path(f).exists():
            print(f"  SKIP: missing {f}")
            return
    test = _load_test(mkt)
    if test is None or test.empty:
        print(f"  SKIP: no test rows for season {mkt['season']} in {mkt['db']}:{mkt['table']}")
        return
    try:
        y = mkt["target"](test)
    except Exception as e:
        print(f"  SKIP: cannot derive target ({e})")
        return
    test = test.assign(_y=y).dropna(subset=["_y"])
    if test.empty:
        print("  SKIP: no resolved outcomes")
        return

    feats = _load_feature_list(mkt["feats"])
    avail = [c for c in feats if c in test.columns]
    if not avail:
        print("  SKIP: no model features present in table")
        return
    # Some featured tables store rolling-rate columns as object/str with NULLs;
    # coerce to numeric exactly as the trainer's fillna(median) path effectively does.
    X = test[avail].apply(pd.to_numeric, errors="coerce")
    X = X.fillna(X.median(numeric_only=True)).fillna(0.0)
    model = pickle.load(open(mkt["model"], "rb"))
    print(f"  test games           : {len(test)}  ({mkt['season']})")

    if mkt["kind"] == "clf":
        try:
            probs = model.predict_proba(X)[:, 1]
        except Exception as e:
            print(f"  SKIP: predict_proba failed ({e})")
            return
        _report_classifier(mkt["name"], probs, test["_y"].values)
    else:
        try:
            preds = model.predict(X)
        except Exception as e:
            print(f"  SKIP: predict failed ({e})")
            return
        resid = test["_y"].values - preds
        saved_sigma = _load_sigma(mkt["sigma"]) if Path(mkt["sigma"]).exists() else float(resid.std())
        _report_regressor(mkt["name"], resid, saved_sigma)


def main():
    print("══ Probability Calibration Audit ════════════════════════════")
    print("  Validates each market's predicted probability against actual")
    print("  outcomes on the held-out current-season test split.")
    for mkt in MARKETS:
        try:
            audit_market(mkt)
        except Exception as e:
            print(f"\n── {mkt['name']} ──\n  ERROR: {e}")
    print("\n  Legend: clf ECE<=0.05 OK / <=0.10 WATCH / else MISCALIBRATED;")
    print("          reg sigma RETUNE if coverage-cal sigma differs >10% from saved.")
    print("Done.")


if __name__ == "__main__":
    main()
