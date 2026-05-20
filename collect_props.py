# collect_props.py
# Pulls NBA player game logs from the NBA API and stores them in player_game_logs.
# Used as the training data source for props models and as the result resolver
# after games finish (collect_props --date yesterday resolves last night's props).
#
# Usage:
#   python collect_props.py                    (current + prior season)
#   python collect_props.py --season 2024-25   (specific season only)
#   python collect_props.py --date 2026-05-18  (re-pull logs for a date, for resolution)

import sqlite3
import time
import argparse
import pandas as pd
from nba_api.stats.endpoints import leaguegamelog
from config import DB_PATH, SEASONS

API_DELAY = 0.8

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS player_game_logs (
        player_id        INTEGER,
        player_name      TEXT,
        team_id          INTEGER,
        team_abbreviation TEXT,
        game_id          TEXT,
        game_date        TEXT,
        season           TEXT,
        matchup          TEXT,
        is_home          INTEGER,
        wl               TEXT,
        min_played       REAL,
        pts              REAL,
        reb              REAL,
        ast              REAL,
        stl              REAL,
        blk              REAL,
        tov              REAL,
        fg3m             REAL,
        PRIMARY KEY (player_id, game_id)
    )
"""


def get_conn():
    return sqlite3.connect(DB_PATH)


def pull_season(season: str, conn: sqlite3.Connection) -> int:
    print(f"  Pulling player logs: {season}...", end=" ", flush=True)
    time.sleep(API_DELAY)
    try:
        gl = leaguegamelog.LeagueGameLog(
            season=season,
            league_id="00",
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="P",
        )
        df = gl.get_data_frames()[0]
    except Exception as e:
        print(f"FAILED — {e}")
        return 0

    if df.empty:
        print("no data.")
        return 0

    df.columns = [c.lower() for c in df.columns]
    df["season"]   = season
    df["is_home"]  = df["matchup"].apply(lambda x: 1 if "vs." in str(x) else 0)
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.strftime("%Y-%m-%d")

    keep = [
        "player_id", "player_name", "team_id", "team_abbreviation",
        "game_id", "game_date", "season", "matchup", "is_home", "wl",
        "min", "pts", "reb", "ast", "stl", "blk", "tov", "fg3m",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    df = df.rename(columns={"min": "min_played"})
    df["min_played"] = pd.to_numeric(df["min_played"], errors="coerce").fillna(0)

    cols = ["player_id","player_name","team_id","team_abbreviation","game_id","game_date",
            "season","matchup","is_home","wl","min_played","pts","reb","ast","stl","blk","tov","fg3m"]
    df = df[[c for c in cols if c in df.columns]]
    conn.executemany("""
        INSERT OR IGNORE INTO player_game_logs
        (player_id, player_name, team_id, team_abbreviation, game_id, game_date,
         season, matchup, is_home, wl, min_played, pts, reb, ast, stl, blk, tov, fg3m)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, df.values.tolist())
    conn.commit()
    print(f"{len(df):,} rows.")
    return len(df)


def pull_date(game_date: str, conn: sqlite3.Connection) -> int:
    """Re-pull all player logs for a specific date (for result resolution)."""
    print(f"  Pulling player logs for {game_date}...", end=" ", flush=True)
    time.sleep(API_DELAY)
    try:
        gl = leaguegamelog.LeagueGameLog(
            season="2025-26",
            league_id="00",
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="P",
            date_from_nullable=game_date,
            date_to_nullable=game_date,
        )
        df = gl.get_data_frames()[0]
    except Exception as e:
        print(f"FAILED — {e}")
        return 0

    if df.empty:
        print("no data.")
        return 0

    df.columns  = [c.lower() for c in df.columns]
    df["season"] = "2025-26"
    df["is_home"] = df["matchup"].apply(lambda x: 1 if "vs." in str(x) else 0)
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.strftime("%Y-%m-%d")

    keep = [
        "player_id", "player_name", "team_id", "team_abbreviation",
        "game_id", "game_date", "season", "matchup", "is_home", "wl",
        "min", "pts", "reb", "ast", "stl", "blk", "tov", "fg3m",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    df = df.rename(columns={"min": "min_played"})
    df["min_played"] = pd.to_numeric(df["min_played"], errors="coerce").fillna(0)

    # Upsert — replace any existing rows for this date
    conn.executemany("""
        INSERT OR REPLACE INTO player_game_logs
        (player_id, player_name, team_id, team_abbreviation, game_id, game_date,
         season, matchup, is_home, wl, min_played, pts, reb, ast, stl, blk, tov, fg3m)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, df[[
        "player_id","player_name","team_id","team_abbreviation","game_id","game_date",
        "season","matchup","is_home","wl","min_played","pts","reb","ast","stl","blk","tov","fg3m"
    ]].values.tolist())
    conn.commit()
    print(f"{len(df)} rows upserted.")
    return len(df)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default=None, help="Single season e.g. 2024-25")
    parser.add_argument("--date",   default=None, help="Pull logs for one date (YYYY-MM-DD)")
    args = parser.parse_args()

    print("\n-- Collect Player Game Logs ----------------------------------------")
    conn = get_conn()
    conn.execute(_CREATE_SQL)
    conn.commit()

    if args.date:
        n = pull_date(args.date, conn)
        print(f"  Done. {n} rows for {args.date}.")
    else:
        seasons = [args.season] if args.season else SEASONS
        total = 0
        for s in seasons:
            existing = conn.execute(
                "SELECT COUNT(*) FROM player_game_logs WHERE season=?", (s,)
            ).fetchone()[0]
            if existing > 5000 and s != seasons[-1]:
                print(f"  Skipping {s} — {existing:,} rows already in DB")
                continue
            total += pull_season(s, conn)
        total_all = conn.execute(
            "SELECT COUNT(*) FROM player_game_logs"
        ).fetchone()[0]
        print(f"\n  Done. {total_all:,} total player-game rows in DB.")

    conn.close()
