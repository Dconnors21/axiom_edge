# ── mlb_props_collect.py ──────────────────────────────────────────────────────
# Pulls MLB player game logs from the MLB Stats API.
# Collects pitcher stats (K's, IP, etc.) and batter stats (H, TB, etc.).
# Usage: python mlb_props_collect.py

import sqlite3
import requests
import time
import pandas as pd
from datetime import date
from mlb_config import MLB_DB_PATH, MLB_SEASONS

MLB_API = "https://statsapi.mlb.com/api/v1"

# MLB team IDs (stable across seasons)
MLB_TEAM_IDS = {
    "ARI": 109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112,
    "CHW": 145, "CIN": 113, "CLE": 114, "COL": 115, "DET": 116,
    "HOU": 117, "KCR": 118, "LAA": 108, "LAD": 119, "MIA": 146,
    "MIL": 158, "MIN": 142, "NYM": 121, "NYY": 147, "OAK": 133,
    "PHI": 143, "PIT": 134, "SDP": 135, "SEA": 136, "SFG": 137,
    "STL": 138, "TBR": 139, "TEX": 140, "TOR": 141, "WSN": 120,
}


def get_conn():
    return sqlite3.connect(MLB_DB_PATH)


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_pitcher_game_logs (
            player_id    INTEGER,
            player_name  TEXT,
            game_id      TEXT,
            game_date    TEXT,
            season       TEXT,
            team         TEXT,
            opponent     TEXT,
            is_home      INTEGER,
            strikeouts   INTEGER,
            innings_pitched REAL,
            hits_allowed INTEGER,
            walks        INTEGER,
            home_runs_allowed INTEGER,
            earned_runs  INTEGER,
            PRIMARY KEY (game_id, player_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_batter_game_logs (
            player_id    INTEGER,
            player_name  TEXT,
            game_id      TEXT,
            game_date    TEXT,
            season       TEXT,
            team         TEXT,
            opponent     TEXT,
            is_home      INTEGER,
            at_bats      INTEGER,
            hits         INTEGER,
            doubles      INTEGER,
            triples      INTEGER,
            home_runs    INTEGER,
            total_bases  INTEGER,
            walks        INTEGER,
            strikeouts   INTEGER,
            rbi          INTEGER,
            PRIMARY KEY (game_id, player_id)
        )
    """)
    conn.commit()


def _get(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))
    return {}


def _ip_to_float(ip_str):
    """Convert '6.1' innings pitched to 6.333... float."""
    try:
        parts = str(ip_str).split(".")
        full  = int(parts[0])
        third = int(parts[1]) if len(parts) > 1 else 0
        return round(full + third / 3, 3)
    except Exception:
        return 0.0


def pull_pitcher_logs(player_id, player_name, season, team, conn, existing):
    url  = f"{MLB_API}/people/{player_id}/stats"
    data = _get(url, params={"stats": "gameLog", "season": season,
                              "group": "pitching", "gameType": "R"})
    stats  = (data or {}).get("stats", [])
    splits = stats[0].get("splits", []) if stats else []
    saved  = 0

    for sp in splits:
        gid  = str(sp.get("game", {}).get("gamePk", ""))
        gkey = (gid, player_id)
        if not gid or gkey in existing:
            continue

        stat     = sp.get("stat", {})
        gdate    = sp.get("date", "")[:10]
        is_home  = 1 if sp.get("isHome", False) else 0
        opp      = sp.get("opponent", {}).get("abbreviation", "")

        ip_raw   = stat.get("inningsPitched", "0.0")
        ip       = _ip_to_float(ip_raw)
        if ip < 0.3:  # skip relief appearances < 1 out
            continue

        conn.execute("""
            INSERT OR IGNORE INTO mlb_pitcher_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            player_id, player_name, gid, gdate, season, team, opp, is_home,
            stat.get("strikeOuts", 0),
            ip,
            stat.get("hits", 0),
            stat.get("baseOnBalls", 0),
            stat.get("homeRuns", 0),
            stat.get("earnedRuns", 0),
        ))
        existing.add(gkey)
        saved += 1

    conn.commit()
    return saved


def pull_batter_logs(player_id, player_name, season, team, conn, existing):
    url  = f"{MLB_API}/people/{player_id}/stats"
    data = _get(url, params={"stats": "gameLog", "season": season,
                              "group": "hitting", "gameType": "R"})
    stats  = (data or {}).get("stats", [])
    splits = stats[0].get("splits", []) if stats else []
    saved  = 0

    for sp in splits:
        gid  = str(sp.get("game", {}).get("gamePk", ""))
        gkey = (gid, player_id)
        if not gid or gkey in existing:
            continue

        stat    = sp.get("stat", {})
        ab      = stat.get("atBats", 0)
        if ab == 0 and stat.get("hits", 0) == 0:
            continue  # skip non-appearances

        gdate   = sp.get("date", "")[:10]
        is_home = 1 if sp.get("isHome", False) else 0
        opp     = sp.get("opponent", {}).get("abbreviation", "")

        h  = stat.get("hits", 0)
        d  = stat.get("doubles", 0)
        t  = stat.get("triples", 0)
        hr = stat.get("homeRuns", 0)
        tb = stat.get("totalBases", h + d + 2 * t + 3 * hr)  # fallback calc

        conn.execute("""
            INSERT OR IGNORE INTO mlb_batter_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            player_id, player_name, gid, gdate, season, team, opp, is_home,
            ab, h, d, t, hr, tb,
            stat.get("baseOnBalls", 0),
            stat.get("strikeOuts", 0),
            stat.get("rbi", 0),
        ))
        existing.add(gkey)
        saved += 1

    conn.commit()
    return saved


def get_team_roster(team_id, season):
    """Returns list of {id, fullName, position} for active roster."""
    url  = f"{MLB_API}/teams/{team_id}/roster/Active"
    data = _get(url, params={"season": season})
    return data.get("roster", [])


def main():
    print("── MLB Props Data Collection ─────────────────────────────────────────────")
    conn = get_conn()
    init_db(conn)

    # Pre-load existing keys so we skip already-saved rows
    p_existing = set(
        (str(r[0]), r[1])
        for r in conn.execute("SELECT game_id, player_id FROM mlb_pitcher_game_logs").fetchall()
    )
    b_existing = set(
        (str(r[0]), r[1])
        for r in conn.execute("SELECT game_id, player_id FROM mlb_batter_game_logs").fetchall()
    )

    total_p = total_b = 0

    for season in MLB_SEASONS:
        print(f"\n── Season {season} ──────────────────────────────────────────────────")
        for abbrev, team_id in MLB_TEAM_IDS.items():
            roster = get_team_roster(team_id, season)
            if not roster:
                continue

            for player in roster:
                pid   = player.get("person", {}).get("id")
                pname = player.get("person", {}).get("fullName", "")
                pos   = player.get("position", {}).get("abbreviation", "")

                if not pid:
                    continue

                if pos == "P":
                    saved = pull_pitcher_logs(pid, pname, season, abbrev, conn, p_existing)
                    total_p += saved
                elif pos not in ("P", "TWP"):
                    saved = pull_batter_logs(pid, pname, season, abbrev, conn, b_existing)
                    total_b += saved

                time.sleep(0.15)

    conn.close()
    print(f"\nDone — {total_p} pitcher game logs | {total_b} batter game logs saved")


if __name__ == "__main__":
    main()
