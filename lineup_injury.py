# ── lineup_injury.py ──────────────────────────────────────────────────────────
# Pulls player availability and injury data from multiple free sources.
# Priority order:
#   1. nba_api LeagueInjuries (official, sometimes blocked)
#   2. ESPN hidden API (free, usually works)  
#   3. Manual entry fallback (always works)
#
# Usage: python lineup_injury.py
#        python lineup_injury.py --manual   (force manual entry)

import sqlite3
import requests
import argparse
import time
import json
import pandas as pd
from datetime import date, datetime
from pathlib import Path
from config import DB_PATH

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS injury_report (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date     TEXT,
            player_name     TEXT,
            team_abbrev     TEXT,
            team_name       TEXT,
            status          TEXT,   -- 'Out', 'Doubtful', 'Questionable', 'Available'
            reason          TEXT,
            source          TEXT,
            pulled_at       TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lineup_impact (
            report_date     TEXT,
            team_abbrev     TEXT,
            out_count       INTEGER,
            doubtful_count  INTEGER,
            questionable_count INTEGER,
            impact_score    REAL,   -- 0-1, higher = more impacted
            star_out        INTEGER, -- 1 if a top-15 min player is out
            PRIMARY KEY (report_date, team_abbrev)
        )
    """)
    conn.commit()

# ── Source 1: nba_api ─────────────────────────────────────────────────────────

def fetch_via_nba_api():
    """Try the official nba_api LeagueInjuries endpoint."""
    try:
        from nba_api.stats.endpoints import leagueinjuries
        time.sleep(0.6)
        inj = leagueinjuries.LeagueInjuries()
        df  = inj.get_data_frames()[0]
        if df.empty:
            return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        print(f"  nba_api: {len(df)} injured players found")
        return df
    except Exception as e:
        print(f"  nba_api failed: {e}")
        return pd.DataFrame()

# ── Source 2: ESPN API ────────────────────────────────────────────────────────

def fetch_via_espn():
    """Try the ESPN hidden API — works with proper headers."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.espn.com/nba/injuries",
        }
        url  = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
        resp = requests.get(url, headers=headers, timeout=10)

        if resp.status_code != 200:
            print(f"  ESPN API returned {resp.status_code}")
            return pd.DataFrame()

        data = resp.json()
        rows = []

        for team in data.get("injuries", []):
            team_abbrev = team.get("team", {}).get("abbreviation", "")
            team_name   = team.get("team", {}).get("displayName", "")

            for injury in team.get("injuries", []):
                athlete = injury.get("athlete", {})
                rows.append({
                    "player_name": athlete.get("displayName",""),
                    "team_abbrev": team_abbrev,
                    "team_name":   team_name,
                    "status":      injury.get("status",""),
                    "reason":      injury.get("longComment",
                                   injury.get("shortComment","")),
                    "source":      "ESPN",
                })

        df = pd.DataFrame(rows)
        print(f"  ESPN API: {len(df)} injured players found")
        return df

    except Exception as e:
        print(f"  ESPN API failed: {e}")
        return pd.DataFrame()

# ── Source 3: Manual entry ────────────────────────────────────────────────────

def fetch_manual(today_games: list = None):
    """
    Manual injury entry — user types in injuries for today's games.
    today_games: list of (home_team, away_team) tuples
    """
    print("\n── Manual Injury Entry ──────────────────────────────────")
    print("Enter injuries for today's games.")
    print("Format: PlayerName,TeamAbbrev,Status (Out/Doubtful/Questionable)")
    print("Example: Anthony Edwards,MIN,Questionable")
    print("Press Enter with no input when done.\n")

    if today_games:
        print("Today's games:")
        for home, away in today_games:
            print(f"  {away} @ {home}")
        print()

    rows = []
    while True:
        entry = input("  Injury (or Enter to finish): ").strip()
        if not entry:
            break
        parts = entry.split(",")
        if len(parts) < 3:
            print("  Format: PlayerName,TeamAbbrev,Status")
            continue
        rows.append({
            "player_name": parts[0].strip(),
            "team_abbrev": parts[1].strip().upper(),
            "team_name":   "",
            "status":      parts[2].strip(),
            "reason":      parts[3].strip() if len(parts) > 3 else "",
            "source":      "manual",
        })
        print(f"  Added: {rows[-1]['player_name']} ({rows[-1]['team_abbrev']}) - {rows[-1]['status']}")

    return pd.DataFrame(rows)

# ── Get today's games ─────────────────────────────────────────────────────────

def get_todays_games(conn) -> list:
    today = date.today().isoformat()
    df = pd.read_sql("""
        SELECT home_team, away_team FROM predictions
        WHERE predict_date = ?
    """, conn, params=(today,))
    if df.empty:
        return []
    return list(zip(df["home_team"], df["away_team"]))

# ── Calculate impact score ────────────────────────────────────────────────────

def calculate_impact(injuries_df: pd.DataFrame, conn) -> pd.DataFrame:
    """
    For each team, calculate an injury impact score based on:
    - Number of players out/doubtful/questionable
    - Whether a key player (high minutes) is affected
    """
    if injuries_df.empty:
        return pd.DataFrame()

    # Get average minutes per player this season to identify key players
    player_mins = pd.read_sql("""
        SELECT player_name, AVG(min) as avg_min
        FROM player_stats
        WHERE season = '2025-26'
        GROUP BY player_name
        HAVING avg_min > 0
    """, conn)
    key_threshold = 28.0  # avg minutes threshold for "key player"

    impact_rows = []
    status_weights = {
        "out":           1.0,
        "doubtful":      0.75,
        "questionable":  0.4,
        "game time":     0.3,
        "available":     0.0,
        "probable":      0.1,
    }

    for team, group in injuries_df.groupby("team_abbrev"):
        out_count          = (group["status"].str.lower() == "out").sum()
        doubtful_count     = (group["status"].str.lower() == "doubtful").sum()
        questionable_count = (group["status"].str.lower().isin(
            ["questionable","game time"])).sum()

        # Calculate weighted impact
        total_impact = 0
        star_out     = 0
        for _, row in group.iterrows():
            weight  = status_weights.get(row["status"].lower(), 0.3)
            # Check if this is a key player
            player_row = player_mins[
                player_mins["player_name"].str.lower() == row["player_name"].lower()
            ]
            if not player_row.empty:
                avg_min = float(player_row["avg_min"].iloc[0])
                if avg_min >= key_threshold:
                    weight *= 2.0  # double weight for key players
                    if row["status"].lower() in ["out","doubtful"]:
                        star_out = 1
            total_impact += weight

        # Normalize to 0-1 (3+ key injuries = max impact)
        impact_score = min(total_impact / 6.0, 1.0)

        impact_rows.append({
            "report_date":         date.today().isoformat(),
            "team_abbrev":         team,
            "out_count":           int(out_count),
            "doubtful_count":      int(doubtful_count),
            "questionable_count":  int(questionable_count),
            "impact_score":        round(impact_score, 4),
            "star_out":            star_out,
        })

    return pd.DataFrame(impact_rows)

# ── Save to DB ────────────────────────────────────────────────────────────────

def save_injuries(injuries_df: pd.DataFrame, impact_df: pd.DataFrame,
                  conn: sqlite3.Connection, source: str):
    today = date.today().isoformat()

    # Clear today's data first
    conn.execute("DELETE FROM injury_report WHERE report_date = ?", (today,))

    if not injuries_df.empty:
        injuries_df["report_date"] = today
        injuries_df["pulled_at"]   = datetime.utcnow().isoformat()
        injuries_df["source"]      = source
        cols = ["report_date","player_name","team_abbrev","team_name",
                "status","reason","source","pulled_at"]
        avail = [c for c in cols if c in injuries_df.columns]
        injuries_df[avail].to_sql("injury_report", conn,
                                   if_exists="append", index=False)

    if not impact_df.empty:
        conn.execute("DELETE FROM lineup_impact WHERE report_date = ?", (today,))
        impact_df.to_sql("lineup_impact", conn, if_exists="append", index=False)

    conn.commit()
    print(f"  Saved {len(injuries_df)} injury records and "
          f"{len(impact_df)} team impact scores.")

# ── Update features with injury context ───────────────────────────────────────

def get_injury_features_for_prediction(conn) -> dict:
    """
    Returns injury impact scores for today's games.
    Used by predict.py to adjust probabilities.
    Returns: {team_abbrev: {'impact_score': float, 'star_out': int}}
    """
    today = date.today().isoformat()
    df = pd.read_sql("""
        SELECT team_abbrev, impact_score, star_out
        FROM lineup_impact
        WHERE report_date = ?
    """, conn, params=(today,))

    if df.empty:
        return {}

    result = {}
    for _, row in df.iterrows():
        result[row["team_abbrev"]] = {
            "impact_score": float(row["impact_score"]),
            "star_out":     int(row["star_out"]),
        }
    return result

# ── Print report ──────────────────────────────────────────────────────────────

def print_injury_report(injuries_df: pd.DataFrame, impact_df: pd.DataFrame):
    today = date.today().strftime("%A, %B %d %Y")
    print(f"\n── Injury Report — {today} ─────────────────────────────")

    if injuries_df.empty:
        print("  No injuries reported.")
        return

    # Group by team
    for team, group in injuries_df.groupby("team_abbrev"):
        # Get impact score
        if not impact_df.empty and team in impact_df["team_abbrev"].values:
            impact = impact_df[impact_df["team_abbrev"]==team]["impact_score"].iloc[0]
            star   = impact_df[impact_df["team_abbrev"]==team]["star_out"].iloc[0]
            impact_str = f"Impact: {impact:.0%}"
            if star:
                impact_str += " ⭐ KEY PLAYER OUT"
        else:
            impact_str = ""

        print(f"\n  {team} — {impact_str}")
        for _, row in group.iterrows():
            status = row["status"]
            color_map = {"Out":"❌","Doubtful":"🔴","Questionable":"🟡",
                         "Available":"✅","Probable":"🟢"}
            icon = color_map.get(status, "⚪")
            reason = f" ({row['reason']})" if row.get("reason") else ""
            print(f"    {icon} {row['player_name']} — {status}{reason}")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual", action="store_true",
                        help="Force manual injury entry")
    parser.add_argument("--show", action="store_true",
                        help="Show today's stored injury report")
    args = parser.parse_args()

    print("\n── NBA Lineup & Injury Report ───────────────────────────")

    conn = get_conn()
    init_tables(conn)

    if args.show:
        today = date.today().isoformat()
        inj = pd.read_sql(
            "SELECT * FROM injury_report WHERE report_date = ?",
            conn, params=(today,))
        imp = pd.read_sql(
            "SELECT * FROM lineup_impact WHERE report_date = ?",
            conn, params=(today,))
        print_injury_report(inj, imp)
        conn.close()
        exit()

    today_games = get_todays_games(conn)
    injuries_df = pd.DataFrame()
    source      = "unknown"

    if args.manual:
        injuries_df = fetch_manual(today_games)
        source      = "manual"
    else:
        # Try automated sources in order
        print("  Trying nba_api...")
        injuries_df = fetch_via_nba_api()
        if not injuries_df.empty:
            source = "nba_api"
            # Normalize columns
            col_map = {
                "player_name": "player_name",
                "team_abbreviation": "team_abbrev",
                "team_name": "team_name",
                "game_date_est": "status",
                "injdesc": "reason",
            }
            injuries_df = injuries_df.rename(columns=col_map)
        else:
            print("  Trying ESPN API...")
            injuries_df = fetch_via_espn()
            if not injuries_df.empty:
                source = "ESPN"
            else:
                print("  Automated sources unavailable.")
                print("  Falling back to manual entry.")
                injuries_df = fetch_manual(today_games)
                source      = "manual"

    # Calculate impact scores
    impact_df = pd.DataFrame()
    if not injuries_df.empty:
        impact_df = calculate_impact(injuries_df, conn)
        save_injuries(injuries_df, impact_df, conn, source)
        print_injury_report(injuries_df, impact_df)
    else:
        print("  No injury data entered.")

    # Show today's games with injury context
    if today_games and not impact_df.empty:
        print(f"\n── Today's games injury summary ─────────────────────────")
        for home, away in today_games:
            # Match team abbreviations
            home_impact = {}
            away_impact = {}
            for team_abbrev, data in get_injury_features_for_prediction(conn).items():
                if team_abbrev in home:
                    home_impact = data
                elif team_abbrev in away:
                    away_impact = data

            home_str = f"Impact {home_impact['impact_score']:.0%}" \
                       if home_impact else "No data"
            away_str = f"Impact {away_impact['impact_score']:.0%}" \
                       if away_impact else "No data"
            print(f"  {away} @ {home}")
            print(f"    Home: {home_str} | Away: {away_str}")

    conn.close()
    print(f"\n  Source: {source}")
    print("  Run python predict.py to regenerate picks with injury context.")
