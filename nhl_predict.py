# ── nhl_predict.py ────────────────────────────────────────────────────────────
# Generates NHL moneyline value-bet predictions for today's games.
# Usage: python nhl_predict.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from datetime import date, datetime, timezone, timedelta
from nhl_config import NHL_DB_PATH, MIN_EDGE, KELLY_FRACTION, NHL_NAME_TO_ABBREV

def get_conn():
    return sqlite3.connect(NHL_DB_PATH)

def _abbrev(name: str) -> str:
    return NHL_NAME_TO_ABBREV.get(name, name[:3].upper())

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
    return max(0.0, k * fraction)

def fmt(price):
    try:
        p = int(price)
        return f"+{p}" if p > 0 else str(p)
    except Exception:
        return "N/A"

def init_predictions(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nhl_predictions (
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
            home_price       REAL,
            away_price       REAL,
            bookmaker        TEXT,
            actual_home_win  INTEGER,
            PRIMARY KEY (game_id, predict_date)
        )
    """)
    conn.commit()

def load_todays_odds(conn):
    df = pd.read_sql("SELECT * FROM nhl_odds ORDER BY pulled_at DESC", conn)
    if df.empty:
        return pd.DataFrame()
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)
    df["commence_dt"] = pd.to_datetime(df["commence_time"], utc=True, errors="coerce")
    df = df[df["commence_dt"] >= now]
    df = df[df["commence_dt"] <= cutoff]
    df = df[df["bookmaker"].isin(["pinnacle", "draftkings", "fanduel"])]
    # Best price per game per side — use sharpest available book
    pref = {"pinnacle": 0, "draftkings": 1, "fanduel": 2}
    df["pref"] = df["bookmaker"].map(pref).fillna(99)
    df = df.sort_values("pref").groupby("game_id").first().reset_index()
    return df

def build_features(home_abbrev: str, away_abbrev: str, conn, feature_cols: list) -> pd.DataFrame:
    """Pull last-N-game rolling stats for both teams from featured table."""
    query = """
        SELECT * FROM nhl_games_featured
        WHERE (home_team = ? OR away_team = ?)
        ORDER BY game_date DESC LIMIT 20
    """
    home_recent = pd.read_sql(query, conn, params=(home_abbrev, home_abbrev))
    away_recent = pd.read_sql(query, conn, params=(away_abbrev, away_abbrev))

    if home_recent.empty or away_recent.empty:
        return pd.DataFrame()

    # Use the most recent row where this team was home for home stats
    home_as_home = home_recent[home_recent["home_team"] == home_abbrev]
    away_as_away = away_recent[away_recent["away_team"] == away_abbrev]

    row = {}
    if not home_as_home.empty:
        src = home_as_home.iloc[0]
        for col in feature_cols:
            if col in src.index:
                row[col] = src[col]
    if not away_as_away.empty:
        src = away_as_away.iloc[0]
        for col in feature_cols:
            if col.startswith("away_") and col in src.index:
                row[col] = src[col]

    row["home_advantage"] = 1.0
    return pd.DataFrame([row])

def main():
    print("── NHL Moneyline Predictions ─────────────────────────────────────────────")
    conn = get_conn()
    init_predictions(conn)

    # Load model
    try:
        with open("nhl_model.pkl",       "rb") as f: model = pickle.load(f)
        with open("nhl_model_meta.json", "r") as f: meta  = json.load(f)
        feature_cols = meta["feature_cols"]
    except FileNotFoundError:
        print("  nhl_model.pkl not found. Run nhl_train.py first.")
        conn.close()
        return

    odds_df = load_todays_odds(conn)
    if odds_df.empty:
        print("  No today's NHL odds found. Run nhl_odds.py first.")
        conn.close()
        return

    today     = date.today().isoformat()
    saved     = 0
    value_ct  = 0

    for _, row in odds_df.iterrows():
        home_full = row["home_team"]
        away_full = row["away_team"]
        home      = _abbrev(home_full)
        away      = _abbrev(away_full)
        gid       = row["game_id"]
        ct        = row["commence_time"]
        h_price   = row["home_price"]
        a_price   = row["away_price"]

        if pd.isna(h_price) or pd.isna(a_price):
            continue

        # Build features for this matchup
        feat_df = build_features(home, away, conn, feature_cols)
        if feat_df.empty:
            # Use league averages when no history
            feat_row = pd.DataFrame([{c: 0.0 for c in feature_cols}])
            feat_row["home_advantage"] = 1.0
            feat_df = feat_row

        feat_df = feat_df.reindex(columns=feature_cols, fill_value=0.0)
        feat_df = feat_df.fillna(0.0)

        try:
            prob_home = float(model.predict_proba(feat_df.values)[0][1])
        except Exception as e:
            print(f"  Prediction error for {home} vs {away}: {e}")
            continue

        prob_away    = 1 - prob_home
        impl_home    = american_to_implied(h_price)
        impl_away    = american_to_implied(a_price)
        vig          = impl_home + impl_away
        fair_home    = impl_home / vig
        fair_away    = impl_away / vig
        edge_home    = prob_home - fair_home
        edge_away    = prob_away - fair_away
        kelly_home   = kelly(edge_home, prob_home, h_price)
        kelly_away   = kelly(edge_away, prob_away, a_price)
        val_home     = 1 if edge_home >= MIN_EDGE else 0
        val_away     = 1 if edge_away >= MIN_EDGE else 0

        if val_home or val_away:
            value_ct += 1
            side = home if val_home else away
            edge = max(edge_home, edge_away)
            print(f"  VALUE: {away} @ {home} — Bet {side} | edge={edge:.1%} | {fmt(h_price if val_home else a_price)}")

        conn.execute("""
            INSERT OR REPLACE INTO nhl_predictions VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, (
            gid, today, home, away, ct,
            round(prob_home, 4), round(prob_away, 4),
            round(fair_home, 4), round(fair_away, 4),
            round(edge_home, 4), round(edge_away, 4),
            val_home, val_away,
            round(kelly_home, 4), round(kelly_away, 4),
            h_price, a_price, row["bookmaker"],
            None,
        ))
        saved += 1

    conn.commit()
    conn.close()
    print(f"\n  {saved} predictions saved | {value_ct} value bets found")
    print("Done.")

if __name__ == "__main__":
    main()
