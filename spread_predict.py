# ── spread_predict.py ─────────────────────────────────────────────────────────
# Generates ATS (against-the-spread) predictions for tonight's NBA games.
# Uses the spread regression model to predict home margin, then computes
# P(cover) via Normal CDF and compares to book's implied probability.
#
# Usage: python spread_predict.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from datetime import datetime, date, timezone, timedelta
from scipy.stats import norm
from config import DB_PATH, MIN_EDGE, KELLY_FRACTION, SHARP_BOOKS

def get_conn():
    return sqlite3.connect(DB_PATH)

def american_to_implied_prob(odds: float) -> float:
    if odds is None or np.isnan(float(odds)):
        return None
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)

def kelly_stake(edge: float, prob: float, odds: float) -> float:
    if odds > 0:
        decimal_odds = (odds / 100) + 1
    else:
        decimal_odds = (100 / abs(odds)) + 1
    b = decimal_odds - 1
    q = 1 - prob
    kelly = (b * prob - q) / b
    return max(0, kelly * KELLY_FRACTION)


# ── Load today's spread lines ─────────────────────────────────────────────────

def load_todays_spreads(conn) -> pd.DataFrame:
    query = """
        SELECT game_id, home_team, away_team, commence_time,
               bookmaker, market, home_price, away_price,
               home_point, away_point, pulled_at
        FROM odds
        WHERE market = 'spreads'
          AND bookmaker IN ({books})
        ORDER BY pulled_at DESC
    """.format(books=",".join(f"'{b}'" for b in SHARP_BOOKS))

    df = pd.read_sql(query, conn)
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

    # Compute vig-free implied probs from spread odds
    best_df["home_spread_implied"] = best_df["home_price"].apply(american_to_implied_prob)
    best_df["away_spread_implied"] = best_df["away_price"].apply(american_to_implied_prob)
    best_df["spread_vig"]          = best_df["home_spread_implied"] + best_df["away_spread_implied"] - 1
    total                          = best_df["home_spread_implied"] + best_df["away_spread_implied"]
    best_df["home_cover_fair"]     = best_df["home_spread_implied"] / total
    best_df["away_cover_fair"]     = best_df["away_spread_implied"] / total

    return best_df


# ── Build features (same as predict.py) ──────────────────────────────────────

def build_today_features(spreads_df: pd.DataFrame, conn, feature_cols: list) -> pd.DataFrame:
    team_stats = pd.read_sql("""
        SELECT * FROM games_featured
        WHERE game_date = (
            SELECT MAX(game_date) FROM games_featured gf2
            WHERE gf2.team_id = games_featured.team_id
        )
    """, conn, parse_dates=["game_date"])

    team_lookup = {}
    for _, row in team_stats.iterrows():
        name = str(row.get("team_name", "")).strip()
        abbr = str(row.get("team_abbreviation", "")).strip()
        team_lookup[name] = row
        team_lookup[abbr] = row

    rows = []
    for _, game in spreads_df.iterrows():
        home_team = game["home_team"]
        away_team = game["away_team"]

        home_stats = None
        away_stats = None

        for key, stats in team_lookup.items():
            if any(part in home_team for part in key.split() if len(part) > 3):
                home_stats = stats
            if any(part in away_team for part in key.split() if len(part) > 3):
                away_stats = stats

        if home_stats is None or away_stats is None:
            all_teams = team_stats.copy()
            for _, ts in all_teams.iterrows():
                tname = str(ts.get("team_name", ""))
                if home_stats is None and any(w in home_team for w in tname.split() if len(w) > 4):
                    home_stats = ts
                if away_stats is None and any(w in away_team for w in tname.split() if len(w) > 4):
                    away_stats = ts

        if home_stats is None or away_stats is None:
            print(f"  Warning: Could not find stats for {home_team} vs {away_team}")
            continue

        feature_row = {
            "game_id":       game["game_id"],
            "home_team":     home_team,
            "away_team":     away_team,
            "commence_time": game["commence_time"],
        }

        for col in feature_cols:
            if col.startswith("home_"):
                base = col[5:]
                feature_row[col] = home_stats.get(base, np.nan)
            elif col.startswith("away_"):
                base = col[5:]
                feature_row[col] = away_stats.get(base, np.nan)
            elif col == "home_advantage":
                feature_row[col] = 1
            elif "diff" in col:
                base = col.replace("_diff", "").replace("pdiff", "point_diff").replace("win_rate", "win")
                h_val = home_stats.get(f"{base}_last10", np.nan)
                a_val = away_stats.get(f"{base}_last10", np.nan)
                feature_row[col] = h_val - a_val if not (np.isnan(h_val) or np.isnan(a_val)) else 0
            else:
                feature_row[col] = np.nan

        rows.append(feature_row)

    return pd.DataFrame(rows)


# ── Generate ATS predictions ──────────────────────────────────────────────────

def generate_spread_predictions(today_features, model, feature_cols, spreads_df, sigma):
    meta_cols = ["game_id", "home_team", "away_team", "commence_time"]
    X = today_features[feature_cols].fillna(0)

    pred_margins = model.predict(X)
    today_features = today_features.copy()
    today_features["pred_home_margin"] = pred_margins

    results = today_features[meta_cols + ["pred_home_margin"]].merge(
        spreads_df[[
            "game_id", "home_price", "away_price",
            "home_point", "away_point",
            "home_cover_fair", "away_cover_fair",
            "spread_vig", "bookmaker",
        ]],
        on="game_id", how="left"
    )

    # P(home covers) = P(actual_margin > -home_point) = Φ((pred - (-home_point)) / σ)
    # home_point is negative for favorites (e.g., -5.5)
    results["home_cover_prob"] = results.apply(
        lambda r: norm.cdf((r["pred_home_margin"] - (-r["home_point"])) / sigma)
        if pd.notna(r["home_point"]) else 0.5, axis=1
    )
    results["away_cover_prob"] = 1.0 - results["home_cover_prob"]

    results["home_ats_edge"] = results["home_cover_prob"] - results["home_cover_fair"]
    results["away_ats_edge"] = results["away_cover_prob"] - results["away_cover_fair"]

    results["home_ats_kelly"] = results.apply(
        lambda r: kelly_stake(r["home_ats_edge"], r["home_cover_prob"], r["home_price"])
        if pd.notna(r["home_price"]) else 0, axis=1
    )
    results["away_ats_kelly"] = results.apply(
        lambda r: kelly_stake(r["away_ats_edge"], r["away_cover_prob"], r["away_price"])
        if pd.notna(r["away_price"]) else 0, axis=1
    )

    results["home_ats_value"] = results["home_ats_edge"] > MIN_EDGE
    results["away_ats_value"] = results["away_ats_edge"] > MIN_EDGE
    results["spread_sigma"]   = sigma

    return results


# ── Save predictions ──────────────────────────────────────────────────────────

def save_spread_predictions(results, conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spread_predictions (
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
            PRIMARY KEY (game_id, predict_date)
        )
    """)
    today = date.today().isoformat()
    conn.execute("DELETE FROM spread_predictions WHERE predict_date = ?", (today,))

    results["predict_date"]       = today
    results["actual_home_cover"]  = None

    save_cols = [c for c in results.columns if c in [
        "game_id","predict_date","home_team","away_team","commence_time",
        "home_point","away_point","pred_home_margin",
        "home_cover_prob","away_cover_prob","home_cover_fair","away_cover_fair",
        "home_ats_edge","away_ats_edge","home_ats_value","away_ats_value",
        "home_ats_kelly","away_ats_kelly","home_price","away_price",
        "spread_sigma","bookmaker","actual_home_cover",
    ]]
    results[save_cols].to_sql("spread_predictions", conn, if_exists="append",
                              index=False, chunksize=50)
    conn.commit()
    print(f"  Spread predictions saved → nba.db: spread_predictions")


# ── Print report ──────────────────────────────────────────────────────────────

def print_report(results):
    today = date.today().strftime("%A, %B %d %Y")
    print(f"\n{'='*60}")
    print(f"  NBA ATS PICKS REPORT — {today}")
    print(f"{'='*60}\n")

    value_count = 0
    for _, g in results.iterrows():
        home = g["home_team"];  away = g["away_team"]
        spread_str = f"{g['home_point']:+.1f}" if pd.notna(g["home_point"]) else "N/A"
        margin_str = f"{g['pred_home_margin']:+.1f}"

        print(f"  {away} @ {home}  |  Spread: {home} {spread_str}  |  Pred margin: {margin_str}")
        print(f"  P(home cover): {g['home_cover_prob']:.1%}  "
              f"Fair: {g['home_cover_fair']:.1%}  "
              f"Edge: {g['home_ats_edge']:+.1%}")

        if g["home_ats_value"]:
            print(f"  🔥 ATS VALUE: {home} {spread_str} — edge {g['home_ats_edge']:+.1%}")
            value_count += 1
        elif g["away_ats_value"]:
            away_spread = f"{g['away_point']:+.1f}" if pd.notna(g["away_point"]) else "N/A"
            print(f"  🔥 ATS VALUE: {away} {away_spread} — edge {g['away_ats_edge']:+.1%}")
            value_count += 1
        else:
            print(f"  ⚪ No ATS value")
        print()

    print(f"{'='*60}")
    print(f"  ATS value picks: {value_count}")
    print(f"{'='*60}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n── NBA Spread Predict ───────────────────────────────────")

    for fname in ["spread_model.pkl", "spread_features.json", "spread_model_std.json"]:
        if not __import__("pathlib").Path(fname).exists():
            print(f"  ERROR: {fname} not found. Run python train_spread.py first.")
            exit(1)

    with open("spread_model.pkl", "rb") as f:
        model = pickle.load(f)
    with open("spread_features.json") as f:
        feature_cols = json.load(f)
    with open("spread_model_std.json") as f:
        sigma = json.load(f)["rmse"]

    print(f"  Model loaded. σ = {sigma:.2f} pts. Features: {len(feature_cols)}")

    conn = get_conn()

    spreads_df = load_todays_spreads(conn)
    if spreads_df.empty:
        print("  No spread lines found for next 24 hours. Run python odds.py first.")
        conn.close()
        exit()
    print(f"  Found {len(spreads_df)} game(s) with spread lines.")

    today_features = build_today_features(spreads_df, conn, feature_cols)
    if today_features.empty:
        print("  Could not build features for tonight's games.")
        conn.close()
        exit()

    results = generate_spread_predictions(today_features, model, feature_cols, spreads_df, sigma)
    print_report(results)
    save_spread_predictions(results, conn)

    value_bets = int(results["home_ats_value"].sum() + results["away_ats_value"].sum())
    print(f"  ATS value picks found: {value_bets}")

    conn.close()
