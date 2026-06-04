# ── mlb_totals_predict.py ─────────────────────────────────────────────────────
# Generates MLB over/under predictions for today's games.
# Predicts total runs via regression, then computes P(over) via Normal CDF.
#
# Usage: python mlb_totals_predict.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from scipy.stats import norm
from mlb_config import MLB_DB_PATH, MIN_EDGE, KELLY_FRACTION, SHARP_BOOKS

MLB_NAME_TO_ABBREV = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",         "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN",      "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",     "Detroit Tigers": "DET",
    "Houston Astros": "HOU",       "Kansas City Royals": "KCR",
    "Los Angeles Angels": "LAA",   "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",        "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",      "New York Mets": "NYM",
    "New York Yankees": "NYY",     "Athletics": "OAK",
    "Oakland Athletics": "OAK",    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",   "San Diego Padres": "SDP",
    "Seattle Mariners": "SEA",     "San Francisco Giants": "SFG",
    "St. Louis Cardinals": "STL",  "Tampa Bay Rays": "TBR",
    "Texas Rangers": "TEX",        "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSN",
}

PARK_FACTORS = {
    "COL":1.18,"BOS":1.08,"CIN":1.07,"TEX":1.06,"PHI":1.05,
    "NYY":1.04,"BAL":1.03,"ATL":1.02,"CHC":1.01,"LAD":0.99,
    "HOU":0.98,"TBR":0.98,"NYM":0.97,"SFG":0.97,"SEA":0.96,
    "MIA":0.96,"SDP":0.96,"PIT":0.96,"DET":0.96,"CHW":0.95,
    "LAA":0.95,"CLE":0.95,"KCR":0.94,"TOR":0.94,"WSN":0.94,"ARI":0.97,
}

def _abbrev(full_name: str) -> str:
    return MLB_NAME_TO_ABBREV.get(full_name, full_name)

def get_conn():
    return sqlite3.connect(MLB_DB_PATH)

def american_to_implied(odds):
    if odds is None or (isinstance(odds, float) and np.isnan(odds)):
        return 0.5
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def kelly(edge, prob, odds, fraction=KELLY_FRACTION):
    if odds > 0: decimal = odds / 100 + 1
    else:        decimal = 100 / abs(odds) + 1
    b = decimal - 1; q = 1 - prob
    k = (b * prob - q) / b
    return max(0, k * fraction)


def load_todays_totals(conn) -> pd.DataFrame:
    try:
        df = pd.read_sql("SELECT * FROM mlb_totals_odds ORDER BY pulled_at DESC", conn)
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)
    df["commence_dt"] = pd.to_datetime(df["commence_time"], utc=True)
    df = df[(df["commence_dt"] >= now) & (df["commence_dt"] <= cutoff)]
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values("pulled_at", ascending=False)
    df = df.drop_duplicates(subset=["game_id", "bookmaker"])

    best_lines = []
    for game_id, group in df.groupby("game_id"):
        for book in SHARP_BOOKS:
            row = group[group["bookmaker"] == book]
            if not row.empty:
                best_lines.append(row.iloc[0])
                break

    if not best_lines:
        return pd.DataFrame()

    best_df = pd.DataFrame(best_lines)

    best_df["over_implied"]  = best_df["over_price"].apply(american_to_implied)
    best_df["under_implied"] = best_df["under_price"].apply(american_to_implied)
    total                    = best_df["over_implied"] + best_df["under_implied"]
    best_df["over_fair"]     = best_df["over_implied"] / total
    best_df["under_fair"]    = best_df["under_implied"] / total

    return best_df


def build_features(totals_df, conn, feature_cols):
    home_stats = pd.read_sql("""
        SELECT * FROM mlb_games_featured g
        WHERE game_date = (
            SELECT MAX(game_date) FROM mlb_games_featured g2
            WHERE g2.home_team = g.home_team
        )
    """, conn).drop_duplicates(subset=["home_team"])
    home_lookup = home_stats.set_index("home_team").to_dict("index")

    away_stats = pd.read_sql("""
        SELECT * FROM mlb_games_featured g
        WHERE game_date = (
            SELECT MAX(game_date) FROM mlb_games_featured g2
            WHERE g2.away_team = g.away_team
        )
    """, conn).drop_duplicates(subset=["away_team"])
    away_lookup = away_stats.set_index("away_team").to_dict("index")

    # Merge today's probable starters for ERA/WHIP
    try:
        starters = pd.read_sql("""
            SELECT * FROM probable_starters WHERE game_date=?
        """, conn, params=(date.today().isoformat(),))
        if not starters.empty:
            totals_df = totals_df.merge(
                starters[["home_team","away_team","home_pitcher","away_pitcher",
                           "home_era","away_era","home_whip","away_whip"]],
                on=["home_team","away_team"], how="left"
            )
    except Exception:
        pass

    for col, default in [("home_era",4.20),("away_era",4.20),
                         ("home_whip",1.30),("away_whip",1.30)]:
        if col not in totals_df.columns:
            totals_df[col] = default
        else:
            totals_df[col] = totals_df[col].fillna(default)

    rows = []
    for _, game in totals_df.iterrows():
        home = game["home_team"]; away = game["away_team"]
        hs   = home_lookup.get(_abbrev(home), {})
        as_  = away_lookup.get(_abbrev(away), {})
        home_era  = float(game.get("home_era") or 4.20)
        away_era  = float(game.get("away_era") or 4.20)
        home_abbr = _abbrev(home) if _abbrev(home) != home else home.split()[-1][:3].upper()

        row = {
            "game_id":       game["game_id"],
            "home_team":     home,
            "away_team":     away,
            "commence_time": game["commence_time"],
        }

        for col in feature_cols:
            if col == "home_advantage":
                row[col] = 1.0
            elif col == "park_factor":
                row[col] = PARK_FACTORS.get(home_abbr, 1.0)
            elif col == "home_sp_era_season":
                row[col] = home_era
            elif col == "away_sp_era_season":
                row[col] = away_era
            elif col == "home_sp_whip_season":
                row[col] = float(game.get("home_whip") or 1.30)
            elif col == "away_sp_whip_season":
                row[col] = float(game.get("away_whip") or 1.30)
            elif col.startswith("home_"):
                row[col] = hs.get(col, np.nan)
            elif col.startswith("away_"):
                row[col] = as_.get(col, np.nan)
            else:
                row[col] = np.nan

        rows.append(row)

    return pd.DataFrame(rows)


def generate_predictions(features_df, model, feature_cols, totals_df, sigma, skill=1.0):
    # Fill missing features with the training median, not 0 — a 0 for a ~4.5-run
    # rolling feature is wildly out-of-distribution and produces garbage totals.
    X = features_df[feature_cols].copy()
    X = X.fillna(X.median(numeric_only=True)).fillna(0)
    pred_totals = model.predict(X)

    features_df = features_df.copy()
    features_df["pred_total"] = pred_totals

    meta = ["game_id","home_team","away_team","commence_time","pred_total"]
    results = features_df[meta].merge(
        totals_df[[
            "game_id","over_price","under_price",
            "total_line","over_fair","under_fair","bookmaker",
        ]],
        on="game_id", how="left"
    )

    # Shrink the raw prediction toward the market line by the model's skill factor.
    # skill=0 (R2<=0, no out-of-sample edge) => pred collapses to the line => ~0 edge.
    def _shrink(r):
        if pd.isna(r["total_line"]):
            return r["pred_total"]
        return r["total_line"] + skill * (r["pred_total"] - r["total_line"])
    results["pred_total"] = results.apply(_shrink, axis=1)

    results["over_prob"]  = results.apply(
        lambda r: norm.cdf((r["pred_total"] - r["total_line"]) / sigma)
        if pd.notna(r["total_line"]) else 0.5, axis=1
    )
    results["under_prob"] = 1.0 - results["over_prob"]

    results["over_edge"]  = results["over_prob"]  - results["over_fair"]
    results["under_edge"] = results["under_prob"] - results["under_fair"]

    results["over_kelly"]  = results.apply(
        lambda r: kelly(r["over_edge"], r["over_prob"], r["over_price"])
        if pd.notna(r.get("over_price")) else 0, axis=1
    )
    results["under_kelly"] = results.apply(
        lambda r: kelly(r["under_edge"], r["under_prob"], r["under_price"])
        if pd.notna(r.get("under_price")) else 0, axis=1
    )

    # Baseball totals have high variance (sigma ~4.7r) relative to typical lines (8-10r),
    # so small pred/line gaps manufacture edges easily. Require meaningful conviction.
    TL_MIN_EDGE = max(MIN_EDGE, 0.10)
    results["over_value"]   = (results["over_edge"]  > TL_MIN_EDGE).astype(int)
    results["under_value"]  = (results["under_edge"] > TL_MIN_EDGE).astype(int)
    results["totals_sigma"] = sigma

    return results


def save_predictions(results, conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_totals_predictions (
            game_id        TEXT,
            predict_date   TEXT,
            home_team      TEXT,
            away_team      TEXT,
            commence_time  TEXT,
            total_line     REAL,
            pred_total     REAL,
            over_prob      REAL,
            under_prob     REAL,
            over_fair      REAL,
            under_fair     REAL,
            over_edge      REAL,
            under_edge     REAL,
            over_value     INTEGER,
            under_value    INTEGER,
            over_kelly     REAL,
            under_kelly    REAL,
            over_price     REAL,
            under_price    REAL,
            totals_sigma   REAL,
            bookmaker      TEXT,
            actual_total   REAL,
            PRIMARY KEY (game_id, predict_date)
        )
    """)
    today = date.today().isoformat()
    conn.execute("DELETE FROM mlb_totals_predictions WHERE predict_date=?", (today,))

    results["predict_date"] = today
    results["actual_total"] = None

    save_cols = [c for c in results.columns if c in [
        "game_id","predict_date","home_team","away_team","commence_time",
        "total_line","pred_total","over_prob","under_prob",
        "over_fair","under_fair","over_edge","under_edge",
        "over_value","under_value","over_kelly","under_kelly",
        "over_price","under_price","totals_sigma","bookmaker","actual_total",
    ]]
    results[save_cols].to_sql("mlb_totals_predictions", conn,
                              if_exists="append", index=False, chunksize=50)
    conn.commit()
    print(f"  MLB totals predictions saved -> mlb.db: mlb_totals_predictions")


if __name__ == "__main__":
    print("\n-- MLB Totals Predict -------------------------------------------")

    for fname in ["mlb_totals_model.pkl", "mlb_totals_features.json", "mlb_totals_model_std.json"]:
        if not Path(fname).exists():
            print(f"  ERROR: {fname} not found. Run python mlb_train_totals.py first.")
            exit(1)

    with open("mlb_totals_model.pkl", "rb") as f:
        model = pickle.load(f)
    with open("mlb_totals_features.json") as f:
        feature_cols = json.load(f)
    with open("mlb_totals_model_std.json") as f:
        _std  = json.load(f)
        sigma = _std["rmse"]
        skill = float(_std.get("skill", 1.0))

    print(f"  Model loaded. sigma={sigma:.2f} runs. skill={skill:.3f}. Features: {len(feature_cols)}")
    if skill <= 0.0:
        print(f"  NOTE: skill=0 (model has no out-of-sample edge) -> predictions "
              f"shrink to the market line, no value bets will be flagged.")

    conn = get_conn()

    totals_df = load_todays_totals(conn)
    if totals_df.empty:
        print("  No MLB totals odds found. Run python mlb_odds.py first.")
        conn.close()
        exit()
    print(f"  Found {len(totals_df)} game(s) with totals lines.")

    features_df = build_features(totals_df, conn, feature_cols)
    if features_df.empty:
        print("  Could not build features.")
        conn.close()
        exit()

    results = generate_predictions(features_df, model, feature_cols, totals_df, sigma, skill)

    print(f"\n{'='*60}")
    print(f"  MLB TOTALS PICKS")
    print(f"{'='*60}")
    for _, g in results.iterrows():
        line = g.get("total_line")
        line_str = f"{line:.1f}" if pd.notna(line) else "N/A"
        print(f"  {g['away_team']} @ {g['home_team']}")
        print(f"  Pred total: {g['pred_total']:.1f}r  Line: {line_str}")
        print(f"  P(over): {g['over_prob']:.1%}  Over edge: {g['over_edge']:+.1%}")
        if g["over_value"]:
            print(f"  >> VALUE: OVER {line_str}")
        elif g["under_value"]:
            print(f"  >> VALUE: UNDER {line_str}")
        print()

    value_count = int(results["over_value"].sum() + results["under_value"].sum())
    print(f"  Totals value picks: {value_count}")

    save_predictions(results, conn)
    conn.close()
