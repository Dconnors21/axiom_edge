# ── mlb_props_odds.py ─────────────────────────────────────────────────────────
# Fetches MLB player prop odds from The Odds API.
# Markets: pitcher_strikeouts, batter_hits, batter_total_bases
#
# NOTE: Player props use the per-event endpoint (/events/{id}/odds), which costs
# ~2 API credits per event. With ~15 MLB games per day, budget ~30 credits per run.
# Free tier = 500 credits/month → ~16 daily runs. If you hit limits,
# reduce PROPS_MARKETS or comment out batter markets.
#
# Usage: python mlb_props_odds.py

import sqlite3
import requests
import time
import pandas as pd
from datetime import datetime, timezone, timedelta
from mlb_config import MLB_DB_PATH, ODDS_API_KEY, MLB_SPORT

PROPS_MARKETS = [
    "pitcher_strikeouts",
    "batter_hits",
    "batter_total_bases",
]
PROPS_BOOKS = ["draftkings", "fanduel"]

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS mlb_prop_odds (
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
    return sqlite3.connect(MLB_DB_PATH)


def _get_events() -> list:
    """Fetch today's MLB event IDs from The Odds API."""
    url = f"https://api.the-odds-api.com/v4/sports/{MLB_SPORT}/events"
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)
    try:
        resp = requests.get(url, params={"apiKey": ODDS_API_KEY, "dateFormat": "iso"},
                            timeout=10)
        if resp.status_code != 200:
            print(f"  Events API returned {resp.status_code}")
            return []
        events = resp.json()
        # Filter to games starting within 24 hours
        result = []
        for ev in events:
            ct = ev.get("commence_time", "")
            try:
                dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                if now <= dt <= cutoff:
                    result.append(ev)
            except Exception:
                pass
        print(f"  Found {len(result)} MLB games in next 24h")
        return result
    except Exception as e:
        print(f"  Error fetching events: {e}")
        return []


def _fetch_event_props(event_id, home, away, commence_time, conn, pulled) -> int:
    url     = f"https://api.the-odds-api.com/v4/sports/{MLB_SPORT}/events/{event_id}/odds"
    markets = ",".join(PROPS_MARKETS)
    try:
        resp = requests.get(url, params={
            "apiKey":     ODDS_API_KEY,
            "regions":    "us",
            "markets":    markets,
            "oddsFormat": "american",
            "bookmakers": ",".join(PROPS_BOOKS),
        }, timeout=15)
        if resp.status_code != 200:
            return 0
        data = resp.json()
    except Exception as e:
        print(f"    Error fetching props for {home} vs {away}: {e}")
        return 0

    rows = []
    for bm in data.get("bookmakers", []):
        book = bm.get("key", "")
        for mkt in bm.get("markets", []):
            mkey = mkt.get("key", "")
            if mkey not in PROPS_MARKETS:
                continue
            # Group outcomes by player (description field)
            player_map = {}
            for out in mkt.get("outcomes", []):
                player = out.get("description", "")
                side   = out.get("name", "")   # "Over" or "Under"
                if not player:
                    continue
                player_map.setdefault(player, {})[side] = {
                    "price": out.get("price"),
                    "point": out.get("point"),
                }
            for player, sides in player_map.items():
                if "Over" not in sides or "Under" not in sides:
                    continue
                line = sides["Over"].get("point")
                rows.append((
                    player, event_id, home, away, commence_time,
                    book, mkey, line,
                    sides["Over"].get("price"),
                    sides["Under"].get("price"),
                    pulled,
                ))

    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO mlb_prop_odds VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        conn.commit()
    return len(rows)


def main():
    print("── MLB Props Odds Fetch ──────────────────────────────────────────────────")
    conn = get_conn()
    conn.execute(_CREATE_SQL)
    conn.commit()

    events = _get_events()
    if not events:
        print("  No games found or API error.")
        conn.close()
        return

    pulled = datetime.utcnow().isoformat()
    total  = 0
    for ev in events:
        gid  = ev.get("id", "")
        home = ev.get("home_team", "")
        away = ev.get("away_team", "")
        ct   = ev.get("commence_time", "")
        n    = _fetch_event_props(gid, home, away, ct, conn, pulled)
        if n:
            print(f"  {away} @ {home}: {n} prop rows saved")
        time.sleep(0.5)  # respect API rate limits
        total += n

    conn.close()
    print(f"\nDone — {total} total prop odds rows saved")


if __name__ == "__main__":
    main()
