import sqlite3
import time
import pandas as pd
from nba_api.stats.endpoints import leaguegamefinder, leaguedashteamstats
from config import DB_PATH, SEASONS

API_DELAY = 0.6

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # Let pandas create the games table dynamically from real data
    # Only create the tables we define manually
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_season_stats (
            season      TEXT,
            team_id     INTEGER,
            team_name   TEXT,
            gp          REAL, w REAL, l REAL, w_pct REAL,
            pts         REAL, opp_pts REAL,
            off_rtg     REAL, def_rtg REAL, net_rtg REAL,
            pace        REAL, ts_pct REAL,
            PRIMARY KEY (season, team_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS pull_log (
            season    TEXT PRIMARY KEY,
            pulled_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("  Database initialized.")

def pull_games_for_season(season: str, conn: sqlite3.Connection):
    print(f"  Pulling games: {season}...", end=" ", flush=True)
    time.sleep(API_DELAY)
    try:
        finder = leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            league_id_nullable="00",
            season_type_nullable="Regular Season",
        )
        df = finder.get_data_frames()[0]
    except Exception as e:
        print(f"FAILED — {e}")
        return 0

    if df.empty:
        print("no data returned.")
        return 0

    # Lowercase all columns so we have a consistent naming convention
    df.columns = [c.lower() for c in df.columns]
    df["season"]  = season
    df["is_home"] = df["matchup"].apply(lambda x: 1 if "vs." in str(x) else 0)

    # Calculate opponent points
    game_pts = df.groupby("game_id")["pts"].apply(list).to_dict()
    def get_opp_pts(row):
        pair = game_pts.get(row["game_id"], [])
        if len(pair) == 2:
            return pair[1] if row["pts"] == pair[0] else pair[0]
        return None
    df["opp_pts"] = df.apply(get_opp_pts, axis=1)

    # Write directly — let pandas infer schema from the actual data
    # This avoids any column name mismatch with the API
    df.to_sql("games", conn, if_exists="append", index=False, chunksize=100)

    # Deduplicate on game_id + team_id
    conn.execute("""
        DELETE FROM games WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM games GROUP BY game_id, team_id
        )
    """)
    conn.commit()
    print(f"{len(df)} rows.")
    return len(df)

def pull_team_season_stats(season: str, conn: sqlite3.Connection):
    print(f"  Pulling team stats: {season}...", end=" ", flush=True)
    time.sleep(API_DELAY)
    try:
        stats = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            measure_type_nullable="Advanced",
            per_mode_simple="PerGame",
        )
        df = stats.get_data_frames()[0]
    except Exception as e:
        print(f"FAILED — {e}")
        return
    if df.empty:
        print("no data.")
        return
    df.columns = [c.lower() for c in df.columns]
    df["season"] = season
    df.to_sql("team_season_stats", conn, if_exists="replace", index=False)
    conn.commit()
    print(f"{len(df)} teams.")

if __name__ == "__main__":
    print("\n── NBA Collect ──────────────────────────────────────────")
    print(f"Database: {DB_PATH}\n")
    init_db()
    conn = get_conn()

    pulled = pd.read_sql("SELECT season FROM pull_log", conn)["season"].tolist()

    total = 0
    for season in SEASONS:
        if season in pulled:
            print(f"  [skip] {season} — already in database")
            continue
        print(f"\n── Season: {season} ─────────────────────────────────────")
        n = pull_games_for_season(season, conn)
        pull_team_season_stats(season, conn)
        total += n
        conn.execute("INSERT OR REPLACE INTO pull_log VALUES (?, datetime('now'))", (season,))
        conn.commit()

    print(f"\n── Current season (2025-26) — refreshing ────────────────")
    pull_games_for_season("2025-26", conn)
    pull_team_season_stats("2025-26", conn)

    count = pd.read_sql("SELECT COUNT(*) as n FROM games", conn).iloc[0]["n"]
    print(f"\n── Done ─────────────────────────────────────────────────")
    print(f"  Total game rows in DB : {count:,}")
    print(f"\nNext step: python odds.py\n")
    conn.close()

