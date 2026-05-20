# ── mlb_collect.py ────────────────────────────────────────────────────────────
# Pulls MLB game data using pybaseball with proper date parsing.
# Usage: python mlb_collect.py

import sqlite3
import pandas as pd
import numpy as np
import time
from datetime import date, datetime
from mlb_config import MLB_DB_PATH, MLB_SEASONS

def get_conn():
    return sqlite3.connect(MLB_DB_PATH)

def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_games (
            game_id     TEXT PRIMARY KEY,
            game_date   TEXT,
            season      TEXT,
            home_team   TEXT,
            away_team   TEXT,
            home_score  INTEGER,
            away_score  INTEGER,
            home_win    INTEGER,
            run_diff    INTEGER,
            game_type   TEXT,
            venue       TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_pitcher_logs (
            game_id      TEXT,
            game_date    TEXT,
            season       TEXT,
            team         TEXT,
            pitcher_name TEXT,
            is_starter   INTEGER,
            ip           REAL,
            er           INTEGER,
            era          REAL,
            whip         REAL,
            PRIMARY KEY (game_id, pitcher_name)
        )
    """)
    conn.commit()

def pull_schedule(season: str, conn):
    from pybaseball import schedule_and_record

    print(f"  Pulling {season} schedule...")

    teams = [
        "ARI","ATL","BAL","BOS","CHC","CHW","CIN","CLE","COL","DET",
        "HOU","KCR","LAA","LAD","MIA","MIL","MIN","NYM","NYY","OAK",
        "PHI","PIT","SDP","SFG","SEA","STL","TBR","TEX","TOR","WSN"
    ]

    all_games = []
    for team in teams:
        try:
            time.sleep(0.3)
            df = schedule_and_record(int(season), team)
            if df is None or df.empty:
                continue
            df["team"]   = team
            df["season"] = season
            all_games.append(df)
        except Exception:
            continue

    if not all_games:
        print(f"  No data for {season}")
        return 0

    raw = pd.concat(all_games, ignore_index=True)
    raw.columns = [c.lower().replace(" ","_") for c in raw.columns]

    # pybaseball returns dates like "Thursday, Apr 6" with no year
    # We need to parse these and add the season year
    def parse_date(date_str, season_year):
        if pd.isna(date_str):
            return None
        date_str = str(date_str).strip()
        # Remove day of week prefix: "Thursday, Apr 6" -> "Apr 6"
        if "," in date_str:
            date_str = date_str.split(",", 1)[1].strip()
        # Handle doubleheader suffix: "Apr 6 (1)" -> "Apr 6"
        if "(" in date_str:
            date_str = date_str.split("(")[0].strip()
        # Parse "Apr 6" with year
        try:
            dt = datetime.strptime(f"{date_str} {season_year}", "%b %d %Y")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            try:
                dt = datetime.strptime(f"{date_str} {season_year}", "%B %d %Y")
                return dt.strftime("%Y-%m-%d")
            except Exception:
                return None

    # Find the date column
    date_col = next((c for c in ["date","game_date","date_game"] if c in raw.columns), None)
    if date_col is None:
        print(f"  Could not find date column. Columns: {raw.columns.tolist()[:10]}")
        return 0

    raw["parsed_date"] = raw[date_col].apply(
        lambda x: parse_date(x, season))

    # Find score columns
    # pybaseball uses 'r' for runs scored, 'ra' for runs allowed
    runs_col    = next((c for c in ["r","runs","runs_scored"] if c in raw.columns), None)
    allowed_col = next((c for c in ["ra","runs_against","runs_allowed"] if c in raw.columns), None)
    result_col  = next((c for c in ["w/l","result","w_l"] if c in raw.columns), None)
    opp_col     = next((c for c in ["opp","opponent","tm"] if c in raw.columns), None)
    venue_col   = next((c for c in ["home_away","unnamed:_4","field"] if c in raw.columns), None)

    games_built = []
    processed   = set()

    for _, row in raw.iterrows():
        try:
            parsed_date = row.get("parsed_date")
            if not parsed_date:
                continue

            # Determine if home game
            # pybaseball marks away games with '@' in home_away column
            is_away = False
            if venue_col and venue_col in row:
                is_away = str(row[venue_col]).strip() == "@"

            if is_away:
                continue  # only process home games to avoid duplicates

            home_team  = row["team"]
            away_team  = str(row.get(opp_col,"UNK")).strip() if opp_col else "UNK"
            home_score = float(row.get(runs_col, 0) or 0) if runs_col else 0
            away_score = float(row.get(allowed_col, 0) or 0) if allowed_col else 0
            result_str = str(row.get(result_col,"")) if result_col else ""

            if "W" in result_str.upper():
                home_win = 1
            elif "L" in result_str.upper():
                home_win = 0
            else:
                continue  # skip postponed/no result

            game_id = f"{season}_{parsed_date}_{home_team}_{away_team}"
            if game_id in processed:
                continue
            processed.add(game_id)

            games_built.append({
                "game_id":   game_id,
                "game_date": parsed_date,
                "season":    season,
                "home_team": home_team,
                "away_team": away_team,
                "home_score": int(home_score),
                "away_score": int(away_score),
                "home_win":   home_win,
                "run_diff":   int(home_score - away_score),
                "game_type":  "R",
                "venue":      home_team,
            })
        except Exception:
            continue

    if not games_built:
        print(f"  Could not parse games for {season}")
        return 0

    df_out = pd.DataFrame(games_built)

    # Remove dupes in DB
    conn.execute("DELETE FROM mlb_games WHERE season = ?", (season,))
    df_out.to_sql("mlb_games", conn, if_exists="append",
                  index=False, chunksize=100)
    conn.commit()
    print(f"  Saved {len(df_out)} games for {season} "
          f"({df_out['game_date'].min()} to {df_out['game_date'].max()})")
    return len(df_out)

def pull_pitcher_stats(season: str, conn):
    """Pull pitcher stats - try multiple sources."""
    print(f"  Pulling {season} pitcher stats...")
    time.sleep(0.5)

    # Try pybaseball pitching_stats
    try:
        from pybaseball import pitching_stats
        df = pitching_stats(int(season), int(season), qual=20)
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            out = pd.DataFrame({
                "pitcher_name": df.get("name", df.get("player_name","")),
                "season":       season,
                "team":         df.get("team", df.get("tm","")),
                "era":          pd.to_numeric(df.get("era",4.2), errors="coerce").fillna(4.2),
                "whip":         pd.to_numeric(df.get("whip",1.3), errors="coerce").fillna(1.3),
                "ip":           pd.to_numeric(df.get("ip",0), errors="coerce").fillna(0),
                "game_id":      f"season_{season}",
                "game_date":    f"{season}-01-01",
                "is_starter":   1,
                "er": 0, "h": 0, "bb": 0, "k": 0,
            })
            conn.execute("DELETE FROM mlb_pitcher_logs WHERE season = ?", (season,))
            out.to_sql("mlb_pitcher_logs", conn, if_exists="append",
                       index=False, chunksize=100)
            conn.commit()
            print(f"  Saved {len(out)} pitchers for {season}")
            return
    except Exception as e:
        print(f"  FanGraphs blocked ({e}) — using league average ERA defaults")

    # Fallback: insert league average by team from games data
    games = pd.read_sql(
        "SELECT home_team as team, AVG(away_score) as era_proxy FROM mlb_games "
        "WHERE season=? GROUP BY home_team", conn, params=(season,))
    if not games.empty:
        games["season"]      = season
        games["pitcher_name"]= games["team"] + "_avg"
        games["era"]         = games["era_proxy"].clip(3.0, 6.0)
        games["whip"]        = 1.30
        games["ip"]          = 180.0
        games["game_id"]     = f"season_{season}"
        games["game_date"]   = f"{season}-01-01"
        games["is_starter"]  = 1
        games["er"]          = 0
        conn.execute("DELETE FROM mlb_pitcher_logs WHERE season = ?", (season,))
        games[["game_id","game_date","season","team","pitcher_name",
                "is_starter","ip","er","era","whip"]]\
            .to_sql("mlb_pitcher_logs", conn, if_exists="append", index=False)
        conn.commit()
        print(f"  Saved team ERA proxies for {season} (FanGraphs unavailable)")

if __name__ == "__main__":
    print("\n── MLB Collect ──────────────────────────────────────────")
    conn = get_conn()
    init_db(conn)

    total = 0
    for season in MLB_SEASONS:
        n = pull_schedule(season, conn)
        total += n
        pull_pitcher_stats(season, conn)
        time.sleep(0.5)

    total_in_db = conn.execute(
        "SELECT COUNT(*) FROM mlb_games").fetchone()[0]

    print(f"\n── Verify ───────────────────────────────────────────────")
    seasons = pd.read_sql(
        "SELECT season, COUNT(*) as n, MIN(game_date) as earliest, "
        "MAX(game_date) as latest FROM mlb_games GROUP BY season", conn)
    print(seasons.to_string())

    print(f"\n── Done ─────────────────────────────────────────────────")
    print(f"  Total MLB games in DB : {total_in_db:,}")
    print(f"  Next step: python mlb_features.py")
    conn.close()