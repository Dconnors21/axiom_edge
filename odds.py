# ── odds.py ───────────────────────────────────────────────────────────────────
# Fetches today's NBA game lines from The Odds API and stores them in nba.db.
# Free tier: 500 requests/month — this script uses 1 request per run.
#
# Usage: python odds.py

import sqlite3
import requests
import pandas as pd
from datetime import datetime
from config import DB_PATH, ODDS_API_KEY, ODDS_SPORT, ODDS_REGIONS, ODDS_MARKETS, ODDS_FORMAT, SHARP_BOOKS

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_odds_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS odds (
            game_id         TEXT,
            commence_time   TEXT,
            home_team       TEXT,
            away_team       TEXT,
            bookmaker       TEXT,
            market          TEXT,   -- h2h, spreads, totals
            home_price      REAL,   -- american odds for home
            away_price      REAL,   -- american odds for away
            home_point      REAL,   -- spread/total point
            away_point      REAL,
            pulled_at       TEXT,
            PRIMARY KEY (game_id, bookmaker, market, pulled_at)
        )
    """)
    conn.commit()

def american_to_implied_prob(odds: float) -> float:
    """Convert American odds to implied probability."""
    if odds is None:
        return None
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)

def fetch_odds() -> list:
    """Hit The Odds API and return raw JSON."""
    url = f"https://api.the-odds-api.com/v4/sports/{ODDS_SPORT}/odds"
    params = {
        "apiKey":  ODDS_API_KEY,
        "regions": ODDS_REGIONS,
        "markets": ODDS_MARKETS,
        "oddsFormat": ODDS_FORMAT,
        "dateFormat": "iso",
    }

    print(f"  Fetching odds from The Odds API...", end=" ", flush=True)
    resp = requests.get(url, params=params, timeout=10)

    if resp.status_code != 200:
        print(f"FAILED — HTTP {resp.status_code}: {resp.text}")
        return []

    data = resp.json()
    remaining = resp.headers.get("x-requests-remaining", "?")
    used       = resp.headers.get("x-requests-used", "?")
    print(f"{len(data)} games found. (Requests used: {used}, remaining: {remaining})")
    return data

def parse_and_store(data: list, conn: sqlite3.Connection):
    """Parse the odds JSON and write to nba.db."""
    rows = []
    pulled_at = datetime.utcnow().isoformat()

    for game in data:
        game_id       = game["id"]
        commence_time = game["commence_time"]
        home_team     = game["home_team"]
        away_team     = game["away_team"]

        for bookmaker in game.get("bookmakers", []):
            bk_key = bookmaker["key"]

            for market in bookmaker.get("markets", []):
                mkt_key = market["key"]
                outcomes = {o["name"]: o for o in market.get("outcomes", [])}

                home_out = outcomes.get(home_team, {})
                away_out = outcomes.get(away_team, {})

                # For totals, outcomes are "Over"/"Under"
                if mkt_key == "totals":
                    over_out  = outcomes.get("Over",  {})
                    under_out = outcomes.get("Under", {})
                    home_price = over_out.get("price")
                    away_price = under_out.get("price")
                    home_point = over_out.get("point")
                    away_point = under_out.get("point")
                else:
                    home_price = home_out.get("price")
                    away_price = away_out.get("price")
                    home_point = home_out.get("point")
                    away_point = away_out.get("point")

                rows.append({
                    "game_id":       game_id,
                    "commence_time": commence_time,
                    "home_team":     home_team,
                    "away_team":     away_team,
                    "bookmaker":     bk_key,
                    "market":        mkt_key,
                    "home_price":    home_price,
                    "away_price":    away_price,
                    "home_point":    home_point,
                    "away_point":    away_point,
                    "pulled_at":     pulled_at,
                })

    if not rows:
        print("  No odds rows to store.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df.to_sql("odds", conn, if_exists="append", index=False, method="multi")

    # Deduplicate
    conn.execute("""
        DELETE FROM odds WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM odds
            GROUP BY game_id, bookmaker, market, pulled_at
        )
    """)
    conn.commit()
    print(f"  Stored {len(df)} odds rows for {df['game_id'].nunique()} games.")
    return df

def show_todays_lines(conn: sqlite3.Connection):
    """Print a clean summary of today's lines from sharp books."""
    df = pd.read_sql("""
        SELECT game_id, home_team, away_team, commence_time,
               bookmaker, market, home_price, away_price, home_point
        FROM odds
        WHERE bookmaker IN ({})
          AND market = 'h2h'
          AND DATE(pulled_at) = DATE('now')
        ORDER BY commence_time, bookmaker
    """.format(",".join(f"'{b}'" for b in SHARP_BOOKS)), conn)

    if df.empty:
        print("  No lines found for today.")
        return

    # Add implied probabilities
    df["home_implied"] = df["home_price"].apply(american_to_implied_prob)
    df["away_implied"] = df["away_price"].apply(american_to_implied_prob)
    df["vig"]          = (df["home_implied"] + df["away_implied"] - 1).round(4)

    print(f"\n── Today's NBA Lines ({'h2h moneyline'}) ──────────────────")
    for _, row in df.iterrows():
        print(f"  {row['away_team']:25s} @ {row['home_team']:25s}")
        print(f"    [{row['bookmaker']:12s}]  Away: {int(row['away_price']):+d} "
              f"({row['away_implied']:.1%})  "
              f"Home: {int(row['home_price']):+d} "
              f"({row['home_implied']:.1%})  "
              f"Vig: {row['vig']:.1%}")
        print()

if __name__ == "__main__":
    print("\n── NBA Odds ─────────────────────────────────────────────")

    if ODDS_API_KEY == "YOUR_ODDS_API_KEY_HERE":
        print("  ERROR: Set your ODDS_API_KEY in config.py first!")
        exit()

    conn = get_conn()
    init_odds_table(conn)

    data = fetch_odds()
    if data:
        df = parse_and_store(data, conn)
        show_todays_lines(conn)

    print("Next step: python features.py\n")
    conn.close()
