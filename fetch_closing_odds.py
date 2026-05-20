# ── fetch_closing_odds.py ─────────────────────────────────────────────────────
# Fetches current odds close to game time (~4 PM daily) and stores vig-free
# closing probabilities for CLV (closing line value) tracking.
#
# CLV = close_fair_prob - open_fair_prob
# Positive CLV means the bet was placed at better odds than the market closed at,
# which is the strongest indicator that a model is finding genuine edge.
#
# Usage: python fetch_closing_odds.py
# Scheduled: run_daily.py --afternoon  (4:00 PM daily via Task Scheduler)

import sqlite3
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from config import DB_PATH, ODDS_API_KEY, SHARP_BOOKS
from mlb_config import MLB_DB_PATH, ODDS_API_KEY as MLB_ODDS_KEY, SHARP_BOOKS as MLB_SHARP_BOOKS

NBA_SPORT = "basketball_nba"
MLB_SPORT = "baseball_mlb"

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS {table} (
        game_id         TEXT,
        market          TEXT,
        side            TEXT,
        close_price     REAL,
        close_fair_prob REAL,
        fetched_at      TEXT,
        PRIMARY KEY (game_id, market, side)
    )
"""


def american_to_implied(odds):
    if odds is None or (isinstance(odds, float) and np.isnan(float(odds))):
        return None
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def vig_free(p1, p2):
    """Return vig-removed (p1_fair, p2_fair) from raw implied probs."""
    if p1 is None or p2 is None:
        return None, None
    total = p1 + p2
    if total <= 0:
        return None, None
    return p1 / total, p2 / total


def fetch_and_store(sport: str, db_path: str, table: str,
                    api_key: str, sharp_books: list):
    """Fetch current odds from The Odds API and write closing_odds rows."""
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey":     api_key,
        "regions":    "us",
        "markets":    "h2h,spreads,totals",
        "oddsFormat": "american",
        "dateFormat": "iso",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"  [{sport}] API error {resp.status_code}")
            return 0
        data = resp.json()
        remaining = resp.headers.get("x-requests-remaining", "?")
        print(f"  [{sport}] {len(data)} games — requests remaining: {remaining}")
    except Exception as e:
        print(f"  [{sport}] Request failed: {e}")
        return 0

    now       = datetime.now(timezone.utc)
    horizon   = now + timedelta(hours=16)   # capture all games today
    fetched_at = now.isoformat()

    rows = []
    for game in data:
        commence = pd.to_datetime(game["commence_time"], utc=True)
        if commence < now or commence > horizon:
            continue

        game_id    = game["id"]
        home_team  = game["home_team"]
        away_team  = game["away_team"]

        # Pick sharpest available book
        book_data = {}
        for book in game.get("bookmakers", []):
            if book["key"] in sharp_books:
                book_data[book["key"]] = book

        chosen_book = None
        for b in sharp_books:
            if b in book_data:
                chosen_book = book_data[b]
                break
        if not chosen_book:
            continue

        for mkt in chosen_book.get("markets", []):
            mkt_key  = mkt["key"]
            outcomes = {o["name"]: o for o in mkt.get("outcomes", [])}

            if mkt_key == "h2h":
                home_price = outcomes.get(home_team, {}).get("price")
                away_price = outcomes.get(away_team, {}).get("price")
                hi = american_to_implied(home_price)
                ai = american_to_implied(away_price)
                hf, af = vig_free(hi, ai)
                if hf is not None:
                    rows += [
                        (game_id, "h2h", "home", home_price, hf, fetched_at),
                        (game_id, "h2h", "away", away_price, af, fetched_at),
                    ]

            elif mkt_key == "spreads":
                home_out = outcomes.get(home_team, {})
                away_out = outcomes.get(away_team, {})
                hp = home_out.get("price"); ap = away_out.get("price")
                hi = american_to_implied(hp); ai = american_to_implied(ap)
                hf, af = vig_free(hi, ai)
                if hf is not None:
                    rows += [
                        (game_id, "spreads", "home", hp, hf, fetched_at),
                        (game_id, "spreads", "away", ap, af, fetched_at),
                    ]

            elif mkt_key == "totals":
                over_out  = outcomes.get("Over",  {})
                under_out = outcomes.get("Under", {})
                op = over_out.get("price"); up = under_out.get("price")
                oi = american_to_implied(op); ui = american_to_implied(up)
                of_, uf = vig_free(oi, ui)
                if of_ is not None:
                    rows += [
                        (game_id, "totals", "over",  op, of_, fetched_at),
                        (game_id, "totals", "under", up, uf,  fetched_at),
                    ]

    if not rows:
        print(f"  [{sport}] No qualifying games in closing window.")
        return 0

    conn = sqlite3.connect(db_path)
    conn.execute(_CREATE_SQL.format(table=table))

    # Upsert — replace existing closing rows for today's games
    conn.executemany(f"""
        INSERT OR REPLACE INTO {table}
        (game_id, market, side, close_price, close_fair_prob, fetched_at)
        VALUES (?,?,?,?,?,?)
    """, rows)
    conn.commit()
    conn.close()

    game_ids = len(set(r[0] for r in rows))
    print(f"  [{sport}] Stored closing odds for {game_ids} game(s) ({len(rows)} rows).")
    return game_ids


if __name__ == "__main__":
    print("\n-- Closing Odds Fetch -------------------------------------------")
    print(f"  Fetching at {datetime.now().strftime('%H:%M')} — captures vig-free close for CLV tracking")

    nba_games = fetch_and_store(NBA_SPORT, DB_PATH, "closing_odds",
                                ODDS_API_KEY, SHARP_BOOKS)
    mlb_games = fetch_and_store(MLB_SPORT, MLB_DB_PATH, "mlb_closing_odds",
                                MLB_ODDS_KEY, MLB_SHARP_BOOKS)

    print(f"\n  Done. NBA: {nba_games} game(s) | MLB: {mlb_games} game(s)")
    print(f"  CLV will be computed automatically when results are resolved tonight.")
