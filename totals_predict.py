# ── totals_predict.py ──────────────────────────────────────────────────────────
# Generates NBA over/under predictions for tonight's games.
# Predicts total score via regression, then computes P(over) via Normal CDF.
#
# Usage: python totals_predict.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from scipy.stats import norm
from config import DB_PATH, MIN_EDGE, KELLY_FRACTION, SHARP_BOOKS

def get_conn():
    return sqlite3.connect(DB_PATH)

def american_to_implied_prob(odds: float) -> float:
    if odds is None or np.isnan(float(odds)):
        return None
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def kelly_stake(edge: float, prob: float, odds: float) -> float:
    if odds > 0:
        decimal_odds = (odds / 100) + 1
    else:
        decimal_odds = (100 / abs(odds)) + 1
    b = decimal_odds - 1
    q = 1 - prob
    k = (b * prob - q) / b
    return max(0, k * KELLY_FRACTION)


def load_todays_totals(conn) -> pd.DataFrame:
    query = """
        SELECT game_id, home_team, away_team, commence_time,
               bookmaker, market, home_price, away_price,
               home_point, away_point, pulled_at
        FROM odds
        WHERE market = 'totals'
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

    # Pick sharpest book per game
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

    # home_price = over odds, away_price = under odds (how odds.py stores them)
    best_df["over_implied"]  = best_df["home_price"].apply(american_to_implied_prob)
    best_df["under_implied"] = best_df["away_price"].apply(american_to_implied_prob)
    total                    = best_df["over_implied"] + best_df["under_implied"]
    best_df["over_fair"]     = best_df["over_implied"] / total
    best_df["under_fair"]    = best_df["under_implied"] / total

    return best_df


def build_today_features(totals_df: pd.DataFrame, conn, feature_cols: list) -> pd.DataFrame:
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
    for _, game in totals_df.iterrows():
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
            for _, ts in team_stats.iterrows():
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
            else:
                feature_row[col] = np.nan

        rows.append(feature_row)

    return pd.DataFrame(rows)


def generate_totals_predictions(today_features, model, feature_cols, totals_df, sigma):
    meta_cols = ["game_id", "home_team", "away_team", "commence_time"]
    X = today_features[feature_cols].fillna(0)

    pred_totals = model.predict(X)
    today_features = today_features.copy()
    today_features["pred_total"] = pred_totals

    results = today_features[meta_cols + ["pred_total"]].merge(
        totals_df[[
            "game_id", "home_price", "away_price",
            "home_point", "over_fair", "under_fair", "bookmaker",
        ]],
        on="game_id", how="left"
    )

    # P(over) = Φ((pred_total - line) / σ)
    results["over_prob"]  = results.apply(
        lambda r: norm.cdf((r["pred_total"] - r["home_point"]) / sigma)
        if pd.notna(r["home_point"]) else 0.5, axis=1
    )
    results["under_prob"] = 1.0 - results["over_prob"]

    results["over_edge"]  = results["over_prob"]  - results["over_fair"]
    results["under_edge"] = results["under_prob"] - results["under_fair"]

    results["over_kelly"] = results.apply(
        lambda r: kelly_stake(r["over_edge"], r["over_prob"], r["home_price"])
        if pd.notna(r.get("home_price")) else 0, axis=1
    )
    results["under_kelly"] = results.apply(
        lambda r: kelly_stake(r["under_edge"], r["under_prob"], r["away_price"])
        if pd.notna(r.get("away_price")) else 0, axis=1
    )

    results["over_value"]  = results["over_edge"]  > MIN_EDGE
    results["under_value"] = results["under_edge"] > MIN_EDGE
    results["totals_sigma"] = sigma

    return results


def save_totals_predictions(results, conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS totals_predictions (
            game_id         TEXT,
            predict_date    TEXT,
            home_team       TEXT,
            away_team       TEXT,
            commence_time   TEXT,
            total_line      REAL,
            pred_total      REAL,
            over_prob       REAL,
            under_prob      REAL,
            over_fair       REAL,
            under_fair      REAL,
            over_edge       REAL,
            under_edge      REAL,
            over_value      INTEGER,
            under_value     INTEGER,
            over_kelly      REAL,
            under_kelly     REAL,
            over_price      REAL,
            under_price     REAL,
            totals_sigma    REAL,
            bookmaker       TEXT,
            actual_total    REAL,
            PRIMARY KEY (game_id, predict_date)
        )
    """)
    today = date.today().isoformat()
    conn.execute("DELETE FROM totals_predictions WHERE predict_date = ?", (today,))

    results["predict_date"] = today
    results["actual_total"] = None
    results["total_line"]   = results["home_point"]
    results["over_price"]   = results["home_price"]
    results["under_price"]  = results["away_price"]

    save_cols = [c for c in results.columns if c in [
        "game_id","predict_date","home_team","away_team","commence_time",
        "total_line","pred_total","over_prob","under_prob",
        "over_fair","under_fair","over_edge","under_edge",
        "over_value","under_value","over_kelly","under_kelly",
        "over_price","under_price","totals_sigma","bookmaker","actual_total",
    ]]
    results[save_cols].to_sql("totals_predictions", conn, if_exists="append",
                              index=False, chunksize=50)
    conn.commit()
    print(f"  Totals predictions saved → nba.db: totals_predictions")


def print_report(results):
    today = date.today().strftime("%A, %B %d %Y")
    print(f"\n{'='*60}")
    print(f"  NBA TOTALS PICKS — {today}")
    print(f"{'='*60}\n")

    value_count = 0
    for _, g in results.iterrows():
        home = g["home_team"]; away = g["away_team"]
        line = g.get("home_point")
        line_str = f"{line:.1f}" if pd.notna(line) else "N/A"

        print(f"  {away} @ {home}  |  O/U: {line_str}")
        print(f"  Pred total: {g['pred_total']:.1f}  "
              f"P(over): {g['over_prob']:.1%}  "
              f"Over edge: {g['over_edge']:+.1%}")

        if g["over_value"]:
            print(f"  🔥 VALUE: OVER {line_str} — edge {g['over_edge']:+.1%}")
            value_count += 1
        elif g["under_value"]:
            print(f"  🔥 VALUE: UNDER {line_str} — edge {g['under_edge']:+.1%}")
            value_count += 1
        else:
            print(f"  ⚪ No totals value")
        print()

    print(f"{'='*60}")
    print(f"  Totals value picks: {value_count}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print("\n── NBA Totals Predict ───────────────────────────────────")

    for fname in ["totals_model.pkl", "totals_features.json", "totals_model_std.json"]:
        if not Path(fname).exists():
            print(f"  ERROR: {fname} not found. Run python train_totals.py first.")
            exit(1)

    with open("totals_model.pkl", "rb") as f:
        model = pickle.load(f)
    with open("totals_features.json") as f:
        feature_cols = json.load(f)
    with open("totals_model_std.json") as f:
        sigma = json.load(f)["rmse"]

    print(f"  Model loaded. σ = {sigma:.2f} pts. Features: {len(feature_cols)}")

    conn = get_conn()

    totals_df = load_todays_totals(conn)
    if totals_df.empty:
        print("  No totals lines found for next 24 hours. Run python odds.py first.")
        conn.close()
        exit()
    print(f"  Found {len(totals_df)} game(s) with totals lines.")

    today_features = build_today_features(totals_df, conn, feature_cols)
    if today_features.empty:
        print("  Could not build features for tonight's games.")
        conn.close()
        exit()

    results = generate_totals_predictions(today_features, model, feature_cols, totals_df, sigma)
    print_report(results)
    save_totals_predictions(results, conn)

    value_count = int(results["over_value"].sum() + results["under_value"].sum())
    print(f"  Totals value picks found: {value_count}")

    conn.close()
