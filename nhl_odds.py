# ── nhl_odds.py ───────────────────────────────────────────────────────────────
# Fetches today's NHL odds (moneyline, puck line, totals) from The Odds API.
# Usage: python nhl_odds.py

import sqlite3
import requests
import pandas as pd
from datetime import datetime, date
from nhl_config import NHL_DB_PATH, ODDS_API_KEY, NHL_SPORT, SHARP_BOOKS

def get_conn():
    return sqlite3.connect(NHL_DB_PATH)

def init_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nhl_odds (
            game_id        TEXT,
            home_team      TEXT,
            away_team      TEXT,
            commence_time  TEXT,
            bookmaker      TEXT,
            market         TEXT,
            home_price     REAL,
            away_price     REAL,
            pulled_at      TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nhl_spread_odds (
            game_id        TEXT,
            home_team      TEXT,
            away_team      TEXT,
            commence_time  TEXT,
            bookmaker      TEXT,
            home_price     REAL,
            away_price     REAL,
            home_point     REAL,
            away_point     REAL,
            pulled_at      TEXT,
            PRIMARY KEY (game_id, bookmaker, pulled_at)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nhl_totals_odds (
            game_id        TEXT,
            home_team      TEXT,
            away_team      TEXT,
            commence_time  TEXT,
            bookmaker      TEXT,
            total_line     REAL,
            over_price     REAL,
            under_price    REAL,
            pulled_at      TEXT,
            PRIMARY KEY (game_id, bookmaker, pulled_at)
        )
    """)
    conn.commit()

def fetch_odds(conn) -> list:
    url = f"https://api.the-odds-api.com/v4/sports/{NHL_SPORT}/odds"
    params = {
        "apiKey":     ODDS_API_KEY,
        "regions":    "us",
        "markets":    "h2h,spreads,totals",
        "oddsFormat": "american",
        "dateFormat": "iso",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"  Odds API returned {resp.status_code}: {resp.text[:200]}")
            return []
        data = resp.json()
        print(f"  Fetched {len(data)} NHL games from Odds API")
        return data
    except Exception as e:
        print(f"  Error fetching odds: {e}")
        return []

def save_odds(data: list, conn):
    pulled = datetime.utcnow().isoformat()
    ml_rows = []
    spread_rows = []
    totals_rows = []

    for game in data:
        gid  = game.get("id", "")
        home = game.get("home_team", "")
        away = game.get("away_team", "")
        ct   = game.get("commence_time", "")

        for bm in game.get("bookmakers", []):
            book = bm.get("key", "")
            if book not in SHARP_BOOKS:
                continue

            for market in bm.get("markets", []):
                mkey = market.get("key", "")
                outs = {o["name"]: o["price"] for o in market.get("outcomes", [])}

                if mkey == "h2h":
                    ml_rows.append((gid, home, away, ct, book, "h2h",
                                    outs.get(home), outs.get(away), pulled))

                elif mkey == "spreads":
                    home_out = next((o for o in market.get("outcomes", []) if o["name"] == home), {})
                    away_out = next((o for o in market.get("outcomes", []) if o["name"] == away), {})
                    spread_rows.append((
                        gid, home, away, ct, book,
                        home_out.get("price"), away_out.get("price"),
                        home_out.get("point"), away_out.get("point"),
                        pulled,
                    ))

                elif mkey == "totals":
                    over_out  = next((o for o in market.get("outcomes", []) if o["name"] == "Over"),  {})
                    under_out = next((o for o in market.get("outcomes", []) if o["name"] == "Under"), {})
                    totals_rows.append((
                        gid, home, away, ct, book,
                        over_out.get("point"),
                        over_out.get("price"), under_out.get("price"),
                        pulled,
                    ))

    if ml_rows:
        conn.executemany(
            "INSERT INTO nhl_odds VALUES (?,?,?,?,?,?,?,?,?)", ml_rows
        )
    if spread_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO nhl_spread_odds VALUES (?,?,?,?,?,?,?,?,?,?)", spread_rows
        )
    if totals_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO nhl_totals_odds VALUES (?,?,?,?,?,?,?,?,?)", totals_rows
        )
    conn.commit()
    print(f"  Saved: {len(ml_rows)} ML rows | {len(spread_rows)} spread rows | {len(totals_rows)} totals rows")

def main():
    print("── NHL Odds Fetch ─────────────────────────────────────────────────────────")
    conn = get_conn()
    init_tables(conn)
    data = fetch_odds(conn)
    if data:
        save_odds(data, conn)
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
