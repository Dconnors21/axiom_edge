# ── mlb_pitchers.py ───────────────────────────────────────────────────────────
# Fetches tonight's probable starters from the free MLB Stats API
# and looks up their season ERA/WHIP from the MLB Stats API.
#
# Usage: python mlb_pitchers.py

import sqlite3
import requests
import pandas as pd
import numpy as np
import time
from datetime import date
from mlb_config import MLB_DB_PATH

def get_conn():
    return sqlite3.connect(MLB_DB_PATH)

def init_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS probable_starters (
            game_date    TEXT,
            game_pk      INTEGER,
            home_team    TEXT,
            away_team    TEXT,
            home_pitcher TEXT,
            away_pitcher TEXT,
            home_era     REAL,
            away_era     REAL,
            home_whip    REAL,
            away_whip    REAL,
            home_fip     REAL,
            away_fip     REAL,
            pulled_at    TEXT,
            PRIMARY KEY (game_date, game_pk)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pitcher_season_stats (
            season          TEXT,
            pitcher_name    TEXT,
            team            TEXT,
            era             REAL,
            whip            REAL,
            fip             REAL,
            ip              REAL,
            k_per_9         REAL,
            bb_per_9        REAL,
            PRIMARY KEY (season, pitcher_name)
        )
    """)
    conn.commit()

def fetch_probable_starters(game_date: str = None) -> pd.DataFrame:
    if game_date is None:
        game_date = date.today().isoformat()

    url = (f"https://statsapi.mlb.com/api/v1/schedule"
           f"?sportId=1&date={game_date}&hydrate=probablePitcher,team")
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            print(f"  MLB API returned {resp.status_code}")
            return pd.DataFrame()

        data = resp.json()
        rows = []
        for d in data.get("dates", []):
            for game in d.get("games", []):
                game_pk   = game.get("gamePk")
                home      = game["teams"]["home"]
                away      = game["teams"]["away"]
                home_team = home["team"]["name"]
                away_team = away["team"]["name"]

                home_pitcher = home.get("probablePitcher",{}).get("fullName","TBD")
                away_pitcher = away.get("probablePitcher",{}).get("fullName","TBD")
                home_pid     = home.get("probablePitcher",{}).get("id")
                away_pid     = away.get("probablePitcher",{}).get("id")

                rows.append({
                    "game_date":    game_date,
                    "game_pk":      game_pk,
                    "home_team":    home_team,
                    "away_team":    away_team,
                    "home_abbrev":  home["team"].get("abbreviation",""),
                    "away_abbrev":  away["team"].get("abbreviation",""),
                    "home_pitcher": home_pitcher,
                    "away_pitcher": away_pitcher,
                    "home_pid":     home_pid,
                    "away_pid":     away_pid,
                })

        df = pd.DataFrame(rows)
        print(f"  Found {len(df)} games for {game_date}")
        return df

    except Exception as e:
        print(f"  Failed to fetch starters: {e}")
        return pd.DataFrame()

def fetch_pitcher_stats_from_api(pitcher_id: int, season: str) -> dict:
    if not pitcher_id:
        return {}
    time.sleep(0.15)
    url = (f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}"
           f"/stats?stats=season&season={season}&group=pitching")
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return {}
        data   = resp.json()
        splits = data.get("stats",[{}])[0].get("splits",[])
        if not splits:
            return {}
        s = splits[0].get("stat",{})
        return {
            "era":  float(s.get("era",  4.20) or 4.20),
            "whip": float(s.get("whip", 1.30) or 1.30),
            "ip":   float(s.get("inningsPitched", 0) or 0),
            "k9":   float(s.get("strikeoutsPer9Inn", 8.0) or 8.0),
            "bb9":  float(s.get("walksPer9Inn",      3.0) or 3.0),
        }
    except Exception:
        return {}

def pull_pitcher_season_stats(season: str, conn):
    """Pull full pitcher season stats from MLB Stats API with team abbreviation."""
    print(f"  Pulling pitcher season stats for {season} from MLB API...")

    url = (f"https://statsapi.mlb.com/api/v1/stats"
           f"?stats=season&season={season}&group=pitching"
           f"&sportId=1&limit=500"
           f"&hydrate=team")
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"  MLB API returned {resp.status_code}")
            return

        data  = resp.json()
        stats = data.get("stats",[{}])[0].get("splits",[])

        rows = []
        for split in stats:
            player = split.get("player",{})
            team   = split.get("team",{})
            s      = split.get("stat",{})
            ip     = float(s.get("inningsPitched",0) or 0)
            if ip < 10:
                continue

            # Try multiple fields for team abbreviation
            team_abbr = (team.get("abbreviation") or
                         team.get("teamCode") or
                         team.get("fileCode") or
                         team.get("name",""))

            rows.append({
                "season":       season,
                "pitcher_name": player.get("fullName",""),
                "team":         team_abbr,
                "era":          float(s.get("era",  4.20) or 4.20),
                "whip":         float(s.get("whip", 1.30) or 1.30),
                "fip":          float(s.get("era",  4.20) or 4.20),
                "ip":           ip,
                "k_per_9":      float(s.get("strikeoutsPer9Inn", 8.0) or 8.0),
                "bb_per_9":     float(s.get("walksPer9Inn",      3.0) or 3.0),
            })

        if rows:
            df = pd.DataFrame(rows)
            conn.execute("DELETE FROM pitcher_season_stats WHERE season = ?", (season,))
            df.to_sql("pitcher_season_stats", conn, if_exists="append",
                      index=False, chunksize=100)
            conn.commit()
            # Show sample to verify team field
            sample = df[df["team"] != ""].head(3)
            print(f"  Saved {len(df)} pitcher records for {season}")
            if not sample.empty:
                print(f"  Sample: {sample[['pitcher_name','team','era']].to_string(index=False)}")
            else:
                print(f"  Warning: team field still empty — will use player-level API fallback")
        else:
            print(f"  No pitcher data returned for {season}")

    except Exception as e:
        print(f"  Failed: {e}")

def enrich_starters(starters_df: pd.DataFrame, conn, season: str = None) -> pd.DataFrame:
    if season is None:
        season = str(date.today().year)

    rows = []
    for _, row in starters_df.iterrows():
        # Always use per-player API for accurate ERA (most reliable source)
        home_stats = {}
        away_stats = {}

        if row.get("home_pid"):
            home_stats = fetch_pitcher_stats_from_api(row["home_pid"], season)
        if row.get("away_pid"):
            away_stats = fetch_pitcher_stats_from_api(row["away_pid"], season)

        rows.append({
            **row.to_dict(),
            "home_era":  home_stats.get("era",  4.20),
            "away_era":  away_stats.get("era",  4.20),
            "home_whip": home_stats.get("whip", 1.30),
            "away_whip": away_stats.get("whip", 1.30),
            "home_fip":  home_stats.get("era",  4.20),
            "away_fip":  away_stats.get("era",  4.20),
            "home_ip":   home_stats.get("ip",   0),
            "away_ip":   away_stats.get("ip",   0),
        })

    return pd.DataFrame(rows)

def print_starters_report(starters_df: pd.DataFrame):
    today = date.today().strftime("%B %d, %Y")
    print(f"\n── Probable Starters — {today} ─────────────────────────")
    print(f"  {'Matchup':<45} {'Away SP':<22} {'ERA':>5} {'Home SP':<22} {'ERA':>5}")
    print(f"  {'─'*105}")
    for _, row in starters_df.iterrows():
        matchup = f"{row['away_team']} @ {row['home_team']}"
        print(f"  {matchup:<45} "
              f"{row['away_pitcher']:<22} {row.get('away_era',0):>5.2f} "
              f"{row['home_pitcher']:<22} {row.get('home_era',0):>5.2f}")

def save_starters(starters_df: pd.DataFrame, conn):
    today = date.today().isoformat()
    conn.execute("DELETE FROM probable_starters WHERE game_date = ?", (today,))
    cols  = ["game_date","game_pk","home_team","away_team",
             "home_pitcher","away_pitcher",
             "home_era","away_era","home_whip","away_whip",
             "home_fip","away_fip"]
    avail = [c for c in cols if c in starters_df.columns]
    starters_df["pulled_at"] = pd.Timestamp.now("UTC").isoformat()
    starters_df[avail + ["pulled_at"]].to_sql(
        "probable_starters", conn, if_exists="append", index=False)
    conn.commit()
    print(f"  Saved {len(starters_df)} games to probable_starters table.")

if __name__ == "__main__":
    print("\n── MLB Pitcher Lookup ───────────────────────────────────")
    conn   = get_conn()
    init_tables(conn)
    season = str(date.today().year)

    # Pull season-level stats (for feature engineering)
    pull_pitcher_season_stats(season, conn)

    # Fetch tonight's starters with individual ERA from player API
    print(f"\n  Fetching tonight's probable starters...")
    starters = fetch_probable_starters()

    if starters.empty:
        print("  No games found.")
    else:
        starters = enrich_starters(starters, conn, season)
        print_starters_report(starters)
        save_starters(starters, conn)

    conn.close()