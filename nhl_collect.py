# ── nhl_collect.py ────────────────────────────────────────────────────────────
# Pulls NHL game data using the official NHL Stats API v1.
# Collects game results + boxscore stats (goals, shots, PP%, PK%, save%).
# Usage: python nhl_collect.py

import sqlite3
import requests
import pandas as pd
import numpy as np
import time
from datetime import date, datetime
from nhl_config import NHL_DB_PATH, NHL_SEASONS, NHL_TEAMS

NHL_API = "https://api-web.nhle.com/v1"

def get_conn():
    return sqlite3.connect(NHL_DB_PATH)

def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nhl_games (
            game_id        TEXT PRIMARY KEY,
            game_date      TEXT,
            season         TEXT,
            home_team      TEXT,
            away_team      TEXT,
            home_score     INTEGER,
            away_score     INTEGER,
            home_win       INTEGER,
            goal_diff      INTEGER,
            total_goals    INTEGER,
            game_type      INTEGER,
            -- Boxscore stats
            home_sog       INTEGER,
            away_sog       INTEGER,
            home_pp_goals  INTEGER,
            home_pp_opp    INTEGER,
            away_pp_goals  INTEGER,
            away_pp_opp    INTEGER,
            home_pim       INTEGER,
            away_pim       INTEGER,
            home_hits      INTEGER,
            away_hits      INTEGER,
            home_blocks    INTEGER,
            away_blocks    INTEGER,
            went_ot        INTEGER
        )
    """)
    conn.commit()

def _get(url: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return {}
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))
    return {}

def pull_team_season(team: str, season: str, conn) -> int:
    """Pull all completed games for a team+season from the NHL schedule API."""
    url  = f"{NHL_API}/club-schedule-season/{team}/{season}"
    data = _get(url)
    games = data.get("games", [])
    if not games:
        return 0

    saved = 0
    existing = set(
        row[0] for row in
        conn.execute("SELECT game_id FROM nhl_games").fetchall()
    )

    for g in games:
        gid       = str(g.get("id", ""))
        state     = g.get("gameState", "")
        game_type = g.get("gameType", 2)  # 2=regular, 3=playoffs

        # Only process completed games (OFF = final)
        if state not in ("OFF", "FINAL") or gid in existing:
            continue

        home = g.get("homeTeam", {})
        away = g.get("awayTeam", {})
        h_score = home.get("score")
        a_score = away.get("score")

        if h_score is None or a_score is None:
            continue

        h_team = home.get("abbrev", "")
        a_team = away.get("abbrev", "")
        gdate  = g.get("gameDate", "")[:10]
        season_str = g.get("season", season)

        h_win    = 1 if h_score > a_score else 0
        gdiff    = h_score - a_score
        total    = h_score + a_score

        # Fetch boxscore for shot/PP data
        box = _get(f"{NHL_API}/gamecenter/{gid}/boxscore")
        bh  = box.get("homeTeam", {})
        ba  = box.get("awayTeam", {})

        # Detect OT/SO
        periods = box.get("periodDescriptor", {})
        went_ot = 1 if box.get("periodDescriptor", {}).get("periodType") in ("OT", "SO") else 0
        # Fallback: check if period number > 3
        linescore = box.get("linescore", {})
        if not went_ot and linescore:
            went_ot = 1 if linescore.get("currentPeriod", 3) > 3 else 0

        conn.execute("""
            INSERT OR IGNORE INTO nhl_games VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, (
            gid, gdate, str(season_str), h_team, a_team,
            h_score, a_score, h_win, gdiff, total, game_type,
            bh.get("sog"),         ba.get("sog"),
            bh.get("ppGoals"),     bh.get("ppOpportunities"),
            ba.get("ppGoals"),     ba.get("ppOpportunities"),
            bh.get("pim"),         ba.get("pim"),
            bh.get("hits"),        ba.get("hits"),
            bh.get("blocks"),      ba.get("blocks"),
            went_ot,
        ))
        existing.add(gid)
        saved += 1
        time.sleep(0.15)

    conn.commit()
    return saved

def main():
    conn = get_conn()
    init_db(conn)

    total = 0
    for season in NHL_SEASONS:
        print(f"\n── Season {season} ──────────────────────────────────────")
        season_total = 0
        seen = set()  # avoid double-counting home + away team calls

        for team in NHL_TEAMS:
            saved = pull_team_season(team, season, conn)
            season_total += saved
            time.sleep(0.3)

        print(f"  Season {season}: {season_total} new games saved")
        total += season_total

    conn.close()
    print(f"\nDone — {total} total new NHL games saved to nhl.db")

if __name__ == "__main__":
    main()
