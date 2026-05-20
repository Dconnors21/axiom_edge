# ── mlb_odds.py ───────────────────────────────────────────────────────────────
# Fetches today's MLB moneyline odds from The Odds API.
# Usage: python mlb_odds.py

import sqlite3
import requests
import pandas as pd
from datetime import datetime, date
from mlb_config import MLB_DB_PATH, ODDS_API_KEY, MLB_SPORT, SHARP_BOOKS

def get_conn():
    return sqlite3.connect(MLB_DB_PATH)

def init_odds_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_odds (
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
    conn.commit()

def init_spread_odds_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_spread_odds (
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
    conn.commit()

def init_totals_odds_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_totals_odds (
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

def fetch_odds(conn) -> pd.DataFrame:
    url = f"https://api.the-odds-api.com/v4/sports/{MLB_SPORT}/odds"
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
            print(f"  Odds API returned {resp.status_code}")
            return pd.DataFrame()

        data      = resp.json()
        remaining = resp.headers.get("x-requests-remaining","?")
        print(f"  Found {len(data)} MLB games "
              f"(requests remaining: {remaining})")

        h2h_rows    = []
        spread_rows = []
        totals_rows = []
        pulled_at   = datetime.utcnow().isoformat()

        for game in data:
            for bk in game.get("bookmakers", []):
                if bk["key"] not in SHARP_BOOKS:
                    continue
                for mkt in bk.get("markets", []):
                    outcomes = {o["name"]: o for o in mkt.get("outcomes", [])}
                    home_out = outcomes.get(game["home_team"], {})
                    away_out = outcomes.get(game["away_team"], {})

                    if mkt["key"] == "h2h":
                        h2h_rows.append({
                            "game_id":       game["id"],
                            "home_team":     game["home_team"],
                            "away_team":     game["away_team"],
                            "commence_time": game["commence_time"],
                            "bookmaker":     bk["key"],
                            "market":        "h2h",
                            "home_price":    home_out.get("price"),
                            "away_price":    away_out.get("price"),
                            "pulled_at":     pulled_at,
                        })
                    elif mkt["key"] == "spreads":
                        spread_rows.append({
                            "game_id":       game["id"],
                            "home_team":     game["home_team"],
                            "away_team":     game["away_team"],
                            "commence_time": game["commence_time"],
                            "bookmaker":     bk["key"],
                            "home_price":    home_out.get("price"),
                            "away_price":    away_out.get("price"),
                            "home_point":    home_out.get("point"),
                            "away_point":    away_out.get("point"),
                            "pulled_at":     pulled_at,
                        })
                    elif mkt["key"] == "totals":
                        over_out  = outcomes.get("Over",  {})
                        under_out = outcomes.get("Under", {})
                        totals_rows.append({
                            "game_id":       game["id"],
                            "home_team":     game["home_team"],
                            "away_team":     game["away_team"],
                            "commence_time": game["commence_time"],
                            "bookmaker":     bk["key"],
                            "total_line":    over_out.get("point"),
                            "over_price":    over_out.get("price"),
                            "under_price":   under_out.get("price"),
                            "pulled_at":     pulled_at,
                        })

        if not h2h_rows:
            print("  No odds found.")
            return pd.DataFrame()

        today = date.today().isoformat()

        df = pd.DataFrame(h2h_rows)
        conn.execute("DELETE FROM mlb_odds WHERE DATE(pulled_at) = ?", (today,))
        df.to_sql("mlb_odds", conn, if_exists="append", index=False, chunksize=100)

        if spread_rows:
            sdf = pd.DataFrame(spread_rows)
            conn.execute("DELETE FROM mlb_spread_odds WHERE DATE(pulled_at) = ?", (today,))
            sdf.to_sql("mlb_spread_odds", conn, if_exists="append", index=False, chunksize=100)
            print(f"  Stored {len(sdf)} run line rows for {sdf['game_id'].nunique()} games.")

        if totals_rows:
            tdf = pd.DataFrame(totals_rows)
            conn.execute("DELETE FROM mlb_totals_odds WHERE DATE(pulled_at) = ?", (today,))
            tdf.to_sql("mlb_totals_odds", conn, if_exists="append", index=False, chunksize=100)
            print(f"  Stored {len(tdf)} totals rows for {tdf['game_id'].nunique()} games.")

        conn.commit()
        print(f"  Stored {len(df)} h2h odds rows for "
              f"{df['game_id'].nunique()} games.")

        # Print today's lines
        print(f"\n── Today's MLB Lines ────────────────────────────────────")
        best = df.sort_values("pulled_at",ascending=False)\
                 .drop_duplicates(["game_id","bookmaker"])
        for gid, grp in best.groupby("game_id"):
            row = grp.iloc[0]
            h = row["home_price"]; a = row["away_price"]
            hi = abs(h)/(abs(h)+100) if h<0 else 100/(h+100)
            ai = abs(a)/(abs(a)+100) if a<0 else 100/(a+100)
            print(f"  {row['away_team']:<28} @ {row['home_team']:<28}")
            print(f"    [{row['bookmaker']:<12}] "
                  f"Away: {int(a):+d} ({ai:.1%})  "
                  f"Home: {int(h):+d} ({hi:.1%})")
        return df

    except Exception as e:
        print(f"  Failed: {e}")
        return pd.DataFrame()

if __name__ == "__main__":
    print("\n── MLB Odds ─────────────────────────────────────────────")
    if ODDS_API_KEY == "YOUR_ODDS_API_KEY_HERE":
        print("  Set ODDS_API_KEY in mlb_config.py first!")
        exit()
    conn = get_conn()
    init_odds_table(conn)
    init_spread_odds_table(conn)
    init_totals_odds_table(conn)
    fetch_odds(conn)
    print(f"\n  Next step: python mlb_predict.py")
    conn.close()
