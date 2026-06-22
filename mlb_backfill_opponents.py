# ── mlb_backfill_opponents.py ─────────────────────────────────────────────────
# The batter/pitcher game logs store the MLB gamePk as game_id but never captured
# the opponent. mlb_games has home/away teams keyed by a composite id, so we can't
# join on game_id directly. Instead we resolve the opponent by (game_date, team):
# in the game that team played that day, the opponent is simply the other team.
#
# Idempotent: only fills rows where opponent is blank and a match exists.
# Coverage is bounded by what mlb_games contains (strong for current seasons).
#
# Usage: python mlb_backfill_opponents.py

import sqlite3
from mlb_config import MLB_DB_PATH

_TABLES = ["mlb_batter_game_logs", "mlb_pitcher_game_logs"]


def backfill(conn, table: str) -> int:
    cur = conn.execute(f"""
        UPDATE {table}
        SET opponent = (
            SELECT CASE WHEN g.home_team = {table}.team THEN g.away_team ELSE g.home_team END
            FROM mlb_games g
            WHERE g.game_date = {table}.game_date
              AND (g.home_team = {table}.team OR g.away_team = {table}.team)
            LIMIT 1
        )
        WHERE (opponent IS NULL OR opponent = '')
          AND EXISTS (
            SELECT 1 FROM mlb_games g
            WHERE g.game_date = {table}.game_date
              AND (g.home_team = {table}.team OR g.away_team = {table}.team)
          )
    """)
    return cur.rowcount


def main():
    conn = sqlite3.connect(MLB_DB_PATH)
    print("── Backfilling MLB opponents from mlb_games (date + team) ──")
    for t in _TABLES:
        total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        filled = backfill(conn, t)
        conn.commit()
        have = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE opponent != ''").fetchone()[0]
        print(f"  {t}: filled {filled} this run · {have}/{total} now have an opponent "
              f"({have / total * 100:.0f}%)")
    conn.close()
    print("  Done.")


if __name__ == "__main__":
    main()
