# props_odds.py
# Fetches NBA player props (points + rebounds) from The Odds API and stores them.
#
# NOTE: Player props use the per-event endpoint (/events/{id}/odds), which costs
# roughly 1 API credit per bookmaker per event. Fetching 10 games x 2 books x 2 markets
# = ~40 credits per run. On the free tier (500/month) that allows ~12 daily runs.
# If you hit the limit, set PROPS_BOOKS to just ["draftkings"].
#
# Usage: python props_odds.py

import sqlite3
import requests
import time
import pandas as pd
from datetime import datetime, timezone, timedelta
from config import DB_PATH, ODDS_API_KEY

PROPS_SPORT   = "basketball_nba"
PROPS_MARKETS = ["player_points", "player_rebounds", "player_assists", "player_threes",
                 "player_steals", "player_blocks"]                                        # expand here for more props
PROPS_BOOKS   = ["draftkings", "fanduel"]              # Pinnacle rarely lists player props

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS props_odds (
        player_name   TEXT,
        game_id       TEXT,
        home_team     TEXT,
        away_team     TEXT,
        commence_time TEXT,
        bookmaker     TEXT,
        market        TEXT,
        line          REAL,
        over_price    REAL,
        under_price   REAL,
        pulled_at     TEXT,
        PRIMARY KEY (player_name, game_id, bookmaker, market, pulled_at)
    )
"""


def get_conn():
    return sqlite3.connect(DB_PATH)


def _maybe_migrate(conn):
    """Add market to PRIMARY KEY if the existing table uses the old PK schema."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='props_odds'"
    ).fetchone()
    if row is None:
        return  # table will be created fresh by _CREATE_SQL
    sql = row[0]
    pk_start = sql.upper().find("PRIMARY KEY")
    if pk_start == -1:
        return
    pk_clause = sql[pk_start:]
    if "market" in pk_clause.lower():
        return  # already on new schema
    print("  Migrating props_odds table to include market in PRIMARY KEY...")
    conn.execute("ALTER TABLE props_odds RENAME TO props_odds_v1")
    conn.execute(_CREATE_SQL.replace("IF NOT EXISTS ", ""))
    conn.execute("INSERT OR IGNORE INTO props_odds SELECT * FROM props_odds_v1")
    conn.execute("DROP TABLE props_odds_v1")
    conn.commit()
    print("  Migration complete.")


def _american_to_implied(odds):
    if odds is None:
        return 0.5
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def fetch_todays_event_ids(conn) -> list:
    """Return (game_id, home_team, away_team, commence_time) for today's games from the odds table."""
    now     = datetime.now(timezone.utc)
    cutoff  = now + timedelta(hours=24)
    try:
        df = pd.read_sql("""
            SELECT DISTINCT game_id, home_team, away_team, commence_time
            FROM odds
            WHERE pulled_at >= ?
        """, conn, params=((now - timedelta(hours=12)).isoformat(),))
        if df.empty:
            return []
        df["dt"] = pd.to_datetime(df["commence_time"], utc=True)
        df = df[(df["dt"] >= now) & (df["dt"] <= cutoff)]
        return df[["game_id","home_team","away_team","commence_time"]].drop_duplicates().to_dict("records")
    except Exception:
        return []


def fetch_props_for_event(event_id: str, market: str) -> list:
    """Call the Odds API per-event endpoint for a single market and return raw bookmaker data."""
    url = (f"https://api.the-odds-api.com/v4/sports/{PROPS_SPORT}"
           f"/events/{event_id}/odds")
    params = {
        "apiKey":      ODDS_API_KEY,
        "regions":     "us",
        "markets":     market,
        "oddsFormat":  "american",
        "bookmakers":  ",".join(PROPS_BOOKS),
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 422:
            return []   # event not found / no props market
        if resp.status_code != 200:
            print(f"    API error {resp.status_code} for {event_id} ({market})")
            return []
        return resp.json().get("bookmakers", [])
    except Exception as e:
        print(f"    Request failed: {e}")
        return []


def parse_and_store(bookmakers: list, event: dict, market: str,
                    conn: sqlite3.Connection) -> int:
    pulled_at = datetime.now(timezone.utc).isoformat()
    rows = []

    for book in bookmakers:
        bk = book["key"]
        for mkt in book.get("markets", []):
            if mkt["key"] != market:
                continue

            # Group Over/Under by player (keyed by description = player name)
            players = {}
            for o in mkt.get("outcomes", []):
                name  = o.get("description", "")   # player name
                side  = o.get("name", "")           # "Over" or "Under"
                price = o.get("price")
                line  = o.get("point")
                if not name or side not in ("Over", "Under"):
                    continue
                if name not in players:
                    players[name] = {"line": line}
                players[name][side.lower() + "_price"] = price

            for player_name, data in players.items():
                if "over_price" not in data or "under_price" not in data:
                    continue
                rows.append((
                    player_name,
                    event["game_id"],
                    event["home_team"],
                    event["away_team"],
                    event["commence_time"],
                    bk,
                    market,
                    data["line"],
                    data["over_price"],
                    data["under_price"],
                    pulled_at,
                ))

    if rows:
        conn.executemany("""
            INSERT OR REPLACE INTO props_odds
            (player_name, game_id, home_team, away_team, commence_time,
             bookmaker, market, line, over_price, under_price, pulled_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        conn.commit()
    return len(rows)


if __name__ == "__main__":
    print("\n-- Props Odds Fetch (Points + Rebounds + Assists + 3PM + Stl + Blk) -")

    conn = get_conn()
    _maybe_migrate(conn)
    conn.execute(_CREATE_SQL)
    conn.commit()

    events = fetch_todays_event_ids(conn)
    if not events:
        print("  No events found in odds table — run python odds.py first.")
        conn.close()
        exit()

    print(f"  {len(events)} game(s) to fetch props for.")
    total_rows = 0

    for market in PROPS_MARKETS:
        market_label = market.replace("player_", "").replace("_", " ").title()
        print(f"\n  Market: {market_label}")
        market_rows = 0
        for i, event in enumerate(events):
            time.sleep(0.4)
            bookmakers = fetch_props_for_event(event["game_id"], market)
            n = parse_and_store(bookmakers, event, market, conn)
            home = event["home_team"].split()[-1]
            away = event["away_team"].split()[-1]
            print(f"    [{i+1}/{len(events)}] {away} @ {home} — {n} lines")
            market_rows += n
        print(f"  {market_label} total: {market_rows} lines")
        total_rows += market_rows

    unique_players = conn.execute("""
        SELECT COUNT(DISTINCT player_name) FROM props_odds
        WHERE pulled_at >= datetime('now', '-1 hour')
    """).fetchone()[0]

    print(f"\n  Done. {total_rows} lines for {unique_players} player(s) across {len(events)} game(s).")
    conn.close()
