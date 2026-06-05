# ── mlb_spread_predict.py ────────────────────────────────────────────────────
# Generates MLB run line (ATS) predictions using the spread regression model.
# Run line in MLB is almost always +/-1.5 — model predicts run margin,
# then converts to P(cover) via Normal CDF.
#
# Usage: python mlb_spread_predict.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from scipy.stats import norm
from mlb_config import MLB_DB_PATH, MIN_EDGE, KELLY_FRACTION, SHARP_BOOKS, FEATURE_COLS
import market_signal as ms

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


def load_todays_run_lines(conn) -> pd.DataFrame:
    try:
        df = pd.read_sql("SELECT * FROM mlb_spread_odds ORDER BY pulled_at DESC", conn)
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

    # Best line per game — prefer sharpest book
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

    # Vig-free implied probabilities from run line odds
    best_df["home_rl_implied"] = best_df["home_price"].apply(american_to_implied)
    best_df["away_rl_implied"] = best_df["away_price"].apply(american_to_implied)
    total = best_df["home_rl_implied"] + best_df["away_rl_implied"]
    best_df["home_cover_fair"] = best_df["home_rl_implied"] / total
    best_df["away_cover_fair"] = best_df["away_rl_implied"] / total

    return best_df


def build_features(run_lines_df, conn, feature_cols):
    park_factors = {
        "COL":1.18,"BOS":1.08,"CIN":1.07,"TEX":1.06,"PHI":1.05,
        "NYY":1.04,"BAL":1.03,"ATL":1.02,"CHC":1.01,"LAD":0.99,
        "HOU":0.98,"TBR":0.98,"NYM":0.97,"SFG":0.97,"SEA":0.96,
        "MIA":0.96,"SDP":0.96,"PIT":0.96,"DET":0.96,"CHW":0.95,
        "LAA":0.95,"CLE":0.95,"KCR":0.94,"TOR":0.94,"WSN":0.94,"ARI":0.97,
    }

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

    # Merge today's probable starters
    try:
        starters = pd.read_sql("""
            SELECT * FROM probable_starters WHERE game_date=?
        """, conn, params=(date.today().isoformat(),))
        if not starters.empty:
            run_lines_df = run_lines_df.merge(
                starters[["home_team","away_team","home_pitcher","away_pitcher",
                           "home_era","away_era","home_whip","away_whip"]],
                on=["home_team","away_team"], how="left"
            )
    except Exception:
        pass

    for col, default in [("home_era",4.20),("away_era",4.20),
                         ("home_whip",1.30),("away_whip",1.30)]:
        if col not in run_lines_df.columns:
            run_lines_df[col] = default
        else:
            run_lines_df[col] = run_lines_df[col].fillna(default)

    rows = []
    for _, game in run_lines_df.iterrows():
        home = game["home_team"]; away = game["away_team"]
        hs   = home_lookup.get(_abbrev(home), {})
        as_  = away_lookup.get(_abbrev(away), {})
        home_era = float(game.get("home_era") or 4.20)
        away_era = float(game.get("away_era") or 4.20)
        home_abbr = home.split()[-1][:3].upper()

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
                row[col] = park_factors.get(home_abbr, 1.0)
            elif col == "home_sp_era_season":
                row[col] = home_era
            elif col == "away_sp_era_season":
                row[col] = away_era
            elif col == "home_sp_whip_season":
                row[col] = float(game.get("home_whip") or 1.30)
            elif col == "away_sp_whip_season":
                row[col] = float(game.get("away_whip") or 1.30)
            elif col == "sp_era_diff":
                row[col] = away_era - home_era
            elif col.startswith("home_"):
                row[col] = hs.get(col, np.nan)
            elif col.startswith("away_"):
                row[col] = as_.get(col, np.nan)
            elif "diff" in col:
                h_col = f"home_{col.replace('_diff','')}"
                a_col = f"away_{col.replace('_diff','')}"
                hv = hs.get(h_col, np.nan); av = as_.get(a_col, np.nan)
                row[col] = (hv - av) if not (
                    np.isnan(float(hv if hv is not None else np.nan)) or
                    np.isnan(float(av if av is not None else np.nan))
                ) else 0.0
            else:
                row[col] = np.nan

        rows.append(row)

    return pd.DataFrame(rows)


def generate_predictions(features_df, model, feature_cols, run_lines_df, sigma):
    X = features_df[feature_cols].fillna(0)
    pred_margins = model.predict(X)

    features_df = features_df.copy()
    features_df["pred_home_margin"] = pred_margins

    meta = ["game_id","home_team","away_team","commence_time","pred_home_margin"]
    results = features_df[meta].merge(
        run_lines_df[[
            "game_id","home_price","away_price",
            "home_point","away_point",
            "home_cover_fair","away_cover_fair","bookmaker",
        ]],
        on="game_id", how="left"
    )

    # P(home covers) using Normal CDF — same logic as NBA spread model
    results["home_cover_prob"] = results.apply(
        lambda r: norm.cdf((r["pred_home_margin"] - (-r["home_point"])) / sigma)
        if pd.notna(r["home_point"]) else 0.5, axis=1
    )
    results["away_cover_prob"] = 1.0 - results["home_cover_prob"]

    results["home_ats_edge"] = results["home_cover_prob"] - results["home_cover_fair"]
    results["away_ats_edge"] = results["away_cover_prob"] - results["away_cover_fair"]

    results["home_ats_kelly"] = results.apply(
        lambda r: kelly(r["home_ats_edge"], r["home_cover_prob"], r["home_price"])
        if pd.notna(r.get("home_price")) else 0, axis=1
    )
    results["away_ats_kelly"] = results.apply(
        lambda r: kelly(r["away_ats_edge"], r["away_cover_prob"], r["away_price"])
        if pd.notna(r.get("away_price")) else 0, axis=1
    )

    # Run line needs a higher threshold than moneyline — the fixed ±1.5 line
    # combined with baseball's high variance (σ≈4.5r) makes edges easy to manufacture.
    # Only flag picks where the model has meaningful conviction.
    RL_MIN_EDGE = max(MIN_EDGE, 0.10)
    results["home_ats_value"] = (results["home_ats_edge"] > RL_MIN_EDGE).astype(int)
    results["away_ats_value"] = (results["away_ats_edge"] > RL_MIN_EDGE).astype(int)
    results["spread_sigma"]   = sigma

    return results


def add_market_signals(results, conn):
    """Annotate run line picks with line movement + soft gate (Kelly haircut
    when the spread moves against our side). Adds market_flag / market_move."""
    try:
        sigs = ms.compute_signals(
            conn, "mlb_spread_odds", "spread",
            point_col="home_point", market_filter=None,
            sharp_books=SHARP_BOOKS)
    except Exception as e:
        print(f"  Market signals skipped: {e}")
        results["market_flag"] = ""
        results["market_move"] = 0.0
        return results
    return ms.annotate_results(
        results, sigs,
        value_a="home_ats_value", value_b="away_ats_value",
        kelly_a="home_ats_kelly", kelly_b="away_ats_kelly",
        edge_a="home_ats_edge",  edge_b="away_ats_edge")


def save_predictions(results, conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_spread_predictions (
            game_id           TEXT,
            predict_date      TEXT,
            home_team         TEXT,
            away_team         TEXT,
            commence_time     TEXT,
            home_point        REAL,
            away_point        REAL,
            pred_home_margin  REAL,
            home_cover_prob   REAL,
            away_cover_prob   REAL,
            home_cover_fair   REAL,
            away_cover_fair   REAL,
            home_ats_edge     REAL,
            away_ats_edge     REAL,
            home_ats_value    INTEGER,
            away_ats_value    INTEGER,
            home_ats_kelly    REAL,
            away_ats_kelly    REAL,
            home_price        REAL,
            away_price        REAL,
            spread_sigma      REAL,
            bookmaker         TEXT,
            actual_home_cover INTEGER,
            market_flag       TEXT,
            market_move       REAL,
            PRIMARY KEY (game_id, predict_date)
        )
    """)
    for col, decl in [("market_flag", "TEXT"), ("market_move", "REAL")]:
        try:
            conn.execute(f"ALTER TABLE mlb_spread_predictions ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass
    today = date.today().isoformat()
    conn.execute("DELETE FROM mlb_spread_predictions WHERE predict_date=?", (today,))

    results["predict_date"]      = today
    results["actual_home_cover"] = None

    save_cols = [c for c in results.columns if c in [
        "game_id","predict_date","home_team","away_team","commence_time",
        "home_point","away_point","pred_home_margin",
        "home_cover_prob","away_cover_prob","home_cover_fair","away_cover_fair",
        "home_ats_edge","away_ats_edge","home_ats_value","away_ats_value",
        "home_ats_kelly","away_ats_kelly","home_price","away_price",
        "spread_sigma","bookmaker","actual_home_cover",
        "market_flag","market_move",
    ]]
    results[save_cols].to_sql("mlb_spread_predictions", conn,
                              if_exists="append", index=False, chunksize=50)
    conn.commit()
    print(f"  MLB run line predictions saved -> mlb.db: mlb_spread_predictions")


if __name__ == "__main__":
    print("\n-- MLB Run Line Predict -----------------------------------------")

    for fname in ["mlb_spread_model.pkl", "mlb_spread_features.json", "mlb_spread_model_std.json"]:
        if not Path(fname).exists():
            print(f"  ERROR: {fname} not found. Run python mlb_train_spread.py first.")
            exit(1)

    with open("mlb_spread_model.pkl", "rb") as f:
        model = pickle.load(f)
    with open("mlb_spread_features.json") as f:
        feature_cols = json.load(f)
    with open("mlb_spread_model_std.json") as f:
        sigma = json.load(f)["rmse"]

    print(f"  Model loaded. sigma={sigma:.2f} runs. Features: {len(feature_cols)}")

    conn = get_conn()

    run_lines = load_todays_run_lines(conn)
    if run_lines.empty:
        print("  No MLB run line odds found. Run python mlb_odds.py first.")
        conn.close()
        exit()
    print(f"  Found {len(run_lines)} game(s) with run line odds.")

    features_df = build_features(run_lines, conn, feature_cols)
    if features_df.empty:
        print("  Could not build features.")
        conn.close()
        exit()

    results = generate_predictions(features_df, model, feature_cols, run_lines, sigma)
    results = add_market_signals(results, conn)

    value_count = int(results["home_ats_value"].sum() + results["away_ats_value"].sum())
    print(f"\n{'='*60}")
    print(f"  MLB RUN LINE PICKS")
    print(f"{'='*60}")
    for _, g in results.iterrows():
        home_pt = g.get("home_point"); away_pt = g.get("away_point")
        hv = int(g.get("home_ats_value", 0)); av = int(g.get("away_ats_value", 0))
        print(f"  {g['away_team']} @ {g['home_team']}")
        print(f"  Pred margin: {g['pred_home_margin']:+.1f}r  "
              f"Run line: {g['home_team']} {f'{home_pt:+.1f}' if home_pt else 'N/A'}")
        print(f"  P(home cover): {g['home_cover_prob']:.1%}  "
              f"Edge: {g['home_ats_edge']:+.1%}")
        if hv:
            print(f"  >> VALUE: {g['home_team']} {f'{home_pt:+.1f}' if home_pt else ''}")
        elif av:
            print(f"  >> VALUE: {g['away_team']} {f'{away_pt:+.1f}' if away_pt else ''}")
        print()

    print(f"  Run line value picks: {value_count}")

    save_predictions(results, conn)
    conn.close()
