# ── predict.py ────────────────────────────────────────────────────────────────
# Generates predictions for tonight's NBA games using the trained model
# and compares them against current sportsbook lines to find value bets.
#
# Usage: python predict.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from datetime import datetime, date, timezone, timedelta
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

def implied_prob_to_american(prob: float) -> str:
    if prob >= 0.5:
        return f"-{round(prob / (1 - prob) * 100)}"
    else:
        return f"+{round((1 - prob) / prob * 100)}"

def kelly_stake(edge: float, prob: float, odds: float) -> float:
    if odds > 0:
        decimal_odds = (odds / 100) + 1
    else:
        decimal_odds = (100 / abs(odds)) + 1
    b = decimal_odds - 1
    q = 1 - prob
    kelly = (b * prob - q) / b
    return max(0, kelly * KELLY_FRACTION)

# ── Load today's odds ─────────────────────────────────────────────────────────

def load_todays_odds(conn) -> pd.DataFrame:
    query = """
        SELECT game_id, home_team, away_team, commence_time,
               bookmaker, market, home_price, away_price, pulled_at
        FROM odds
        WHERE market = 'h2h'
          AND bookmaker IN ({books})
        ORDER BY pulled_at DESC
    """.format(books=",".join(f"'{b}'" for b in SHARP_BOOKS))

    df = pd.read_sql(query, conn)
    if df.empty:
        return pd.DataFrame()

    # Filter to only games starting within the next 24 hours
    now     = datetime.now(timezone.utc)
    cutoff  = now + timedelta(hours=24)
    df["commence_dt"] = pd.to_datetime(df["commence_time"], utc=True)
    df = df[df["commence_dt"] >= now]          # not already started
    df = df[df["commence_dt"] <= cutoff]       # within next 24 hours

    if df.empty:
        return pd.DataFrame()

    # Keep most recent pull per game+bookmaker
    df = df.sort_values("pulled_at", ascending=False)
    df = df.drop_duplicates(subset=["game_id", "bookmaker"])

    # Best line per game — prefer sharpest book
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
    best_df["home_implied"] = best_df["home_price"].apply(american_to_implied_prob)
    best_df["away_implied"] = best_df["away_price"].apply(american_to_implied_prob)
    best_df["vig"]          = best_df["home_implied"] + best_df["away_implied"] - 1
    best_df["home_fair_prob"] = best_df["home_implied"] / (best_df["home_implied"] + best_df["away_implied"])
    best_df["away_fair_prob"] = best_df["away_implied"] / (best_df["home_implied"] + best_df["away_implied"])

    return best_df

# ── Build features for today's games ─────────────────────────────────────────

def build_today_features(odds_df: pd.DataFrame, conn, feature_cols: list) -> pd.DataFrame:
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
    for _, game in odds_df.iterrows():
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

# ── Generate predictions ──────────────────────────────────────────────────────

def generate_predictions(today_features, model, feature_cols, odds_df):
    meta_cols = ["game_id", "home_team", "away_team", "commence_time"]
    X = today_features[feature_cols].fillna(0)

    probs = model.predict_proba(X)
    today_features = today_features.copy()
    today_features["model_home_prob"] = probs[:, 1]
    today_features["model_away_prob"] = probs[:, 0]

    results = today_features[meta_cols + ["model_home_prob", "model_away_prob"]].merge(
        odds_df[["game_id", "home_price", "away_price",
                 "home_fair_prob", "away_fair_prob", "vig", "bookmaker"]],
        on="game_id", how="left"
    )

    results["home_edge"] = results["model_home_prob"] - results["home_fair_prob"]
    results["away_edge"] = results["model_away_prob"] - results["away_fair_prob"]

    results["home_kelly"] = results.apply(
        lambda r: kelly_stake(r["home_edge"], r["model_home_prob"], r["home_price"])
        if pd.notna(r["home_price"]) else 0, axis=1)
    results["away_kelly"] = results.apply(
        lambda r: kelly_stake(r["away_edge"], r["model_away_prob"], r["away_price"])
        if pd.notna(r["away_price"]) else 0, axis=1)

    results["home_value"] = results["home_edge"] > MIN_EDGE
    results["away_value"] = results["away_edge"] > MIN_EDGE

    return results

# ── Pretty print report ───────────────────────────────────────────────────────

def print_report(results):
    today = date.today().strftime("%A, %B %d %Y")
    print(f"\n{'='*60}")
    print(f"  NBA VALUE BETS REPORT — {today}")
    print(f"  Model: XGBoost | Min edge: {MIN_EDGE:.0%} | Kelly: {KELLY_FRACTION:.0%}")
    print(f"{'='*60}\n")

    value_bets_found = 0

    for _, game in results.iterrows():
        home = game["home_team"]
        away = game["away_team"]
        try:
            tip = pd.to_datetime([game["commence_time"]], utc=True).tz_convert("America/New_York").strftime("%I:%M %p ET").lstrip("0")
        except Exception:
            tip_time = str(game["commence_time"])

        print(f"  {away} @ {home}")
        print(f"  Tip: {tip_time}  |  Book: {game.get('bookmaker','N/A')}")
        print(f"  {'─'*52}")

        h_prob = game["model_home_prob"]
        a_prob = game["model_away_prob"]
        h_fair = game.get("home_fair_prob", 0.5)
        a_fair = game.get("away_fair_prob", 0.5)
        h_edge = game["home_edge"]
        a_edge = game["away_edge"]
        h_price = game.get("home_price")
        a_price = game.get("away_price")

        print(f"  {'Team':<26} {'Model%':>8} {'Book%':>8} {'Edge':>8} {'Line':>8}")
        print(f"  {'─'*60}")
        print(f"  {home:<26} {h_prob:>7.1%} {h_fair:>7.1%} {h_edge:>+7.1%} "
              f"{implied_prob_to_american(h_fair) if h_fair else 'N/A':>8}")
        print(f"  {away:<26} {a_prob:>7.1%} {a_fair:>7.1%} {a_edge:>+7.1%} "
              f"{implied_prob_to_american(a_fair) if a_fair else 'N/A':>8}")

        if game["home_value"]:
            kelly_pct = game["home_kelly"] * 100
            print(f"\n  🔥 VALUE BET: {home}")
            print(f"     Edge: {h_edge:+.1%} | Kelly stake: {kelly_pct:.1f}% of bankroll")
            print(f"     Line: {int(h_price):+d} | Model prob: {h_prob:.1%}")
            value_bets_found += 1

        if game["away_value"]:
            kelly_pct = game["away_kelly"] * 100
            print(f"\n  🔥 VALUE BET: {away}")
            print(f"     Edge: {a_edge:+.1%} | Kelly stake: {kelly_pct:.1f}% of bankroll")
            print(f"     Line: {int(a_price):+d} | Model prob: {a_prob:.1%}")
            value_bets_found += 1

        if not game["home_value"] and not game["away_value"]:
            print(f"\n  ⚪ No value found — skip this game")

        print()

    print(f"{'='*60}")
    print(f"  Value bets today: {value_bets_found}")
    print(f"  Remember: Kelly sizing assumes a fixed bankroll.")
    print(f"{'='*60}\n")

    return value_bets_found

# ── Save predictions to DB ────────────────────────────────────────────────────

def save_predictions(results, conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            game_id          TEXT,
            predict_date     TEXT,
            home_team        TEXT,
            away_team        TEXT,
            commence_time    TEXT,
            model_home_prob  REAL,
            model_away_prob  REAL,
            home_fair_prob   REAL,
            away_fair_prob   REAL,
            home_edge        REAL,
            away_edge        REAL,
            home_value       INTEGER,
            away_value       INTEGER,
            home_kelly       REAL,
            away_kelly       REAL,
            bookmaker        TEXT,
            home_price       REAL,
            away_price       REAL,
            actual_home_win  INTEGER,
            PRIMARY KEY (game_id, predict_date)
        )
    """)
    today = date.today().isoformat()

    # Clear today's predictions first to avoid duplicates
    conn.execute("DELETE FROM predictions WHERE predict_date = ?", (today,))

    results["predict_date"]    = today
    results["actual_home_win"] = None

    cols = [c for c in results.columns if c in [
        "game_id","predict_date","home_team","away_team","commence_time",
        "model_home_prob","model_away_prob","home_fair_prob","away_fair_prob",
        "home_edge","away_edge","home_value","away_value","home_kelly","away_kelly",
        "bookmaker","home_price","away_price","actual_home_win"
    ]]
    results[cols].to_sql("predictions", conn, if_exists="append",
                         index=False, chunksize=50)
    conn.commit()
    print(f"  Predictions saved to nba.db → predictions table")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n── NBA Predict ──────────────────────────────────────────")

    with open("model.pkl", "rb") as f:
        model = pickle.load(f)
    with open("features.json") as f:
        feature_cols = json.load(f)

    print(f"  Model loaded. Features: {len(feature_cols)}")

    conn = get_conn()

    odds_df = load_todays_odds(conn)
    if odds_df.empty:
        print("  No games found in next 24 hours. Run python odds.py first.")
        exit()
    print(f"  Found {len(odds_df)} game(s) tonight.")

    today_features = build_today_features(odds_df, conn, feature_cols)
    if today_features.empty:
        print("  Could not build features for tonight's games.")
        exit()

    results = generate_predictions(today_features, model, feature_cols, odds_df)
    value_count = print_report(results)
    save_predictions(results, conn)

    conn.close()