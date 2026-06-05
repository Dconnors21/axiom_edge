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


def parse_team_stats(rr: dict) -> dict:
    """Extract per-team special-teams / physical stats from the gamecenter
    right-rail `teamGameStats` block. The boxscore endpoint only exposes score
    and sog; PP/PIM/hits/blocks live here, with powerPlay formatted as "G/Opp".
    Returns Nones when a category is absent so callers can write NULLs safely."""
    out = {k: None for k in (
        "home_pp_goals", "home_pp_opp", "away_pp_goals", "away_pp_opp",
        "home_pim", "away_pim", "home_hits", "away_hits",
        "home_blocks", "away_blocks",
    )}
    stats = {s.get("category"): s for s in rr.get("teamGameStats", [])}

    def _frac(val):
        try:
            g, o = str(val).split("/")
            return int(g), int(o)
        except Exception:
            return None, None

    def _int(val):
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    if "powerPlay" in stats:
        out["home_pp_goals"], out["home_pp_opp"] = _frac(stats["powerPlay"].get("homeValue"))
        out["away_pp_goals"], out["away_pp_opp"] = _frac(stats["powerPlay"].get("awayValue"))
    for cat, key in [("pim", "pim"), ("hits", "hits"), ("blockedShots", "blocks")]:
        if cat in stats:
            out[f"home_{key}"] = _int(stats[cat].get("homeValue"))
            out[f"away_{key}"] = _int(stats[cat].get("awayValue"))
    return out

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

        # Fetch boxscore for score/shot data + right-rail for special teams.
        box = _get(f"{NHL_API}/gamecenter/{gid}/boxscore")
        bh  = box.get("homeTeam", {})
        ba  = box.get("awayTeam", {})
        ts  = parse_team_stats(_get(f"{NHL_API}/gamecenter/{gid}/right-rail"))

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
            ts["home_pp_goals"],   ts["home_pp_opp"],
            ts["away_pp_goals"],   ts["away_pp_opp"],
            ts["home_pim"],        ts["away_pim"],
            ts["home_hits"],       ts["away_hits"],
            ts["home_blocks"],     ts["away_blocks"],
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
