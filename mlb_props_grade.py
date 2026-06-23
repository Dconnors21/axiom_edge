# ── mlb_props_grade.py ────────────────────────────────────────────────────────
# Backfills actual_val on the MLB props prediction tables from the local game
# logs (mlb_pitcher_game_logs / mlb_batter_game_logs), matched by player + date.
#
# The API-based results fetcher wasn't populating actual_val, leaving the props
# models unvalidated. The game logs are pulled daily by mlb_props_collect, so
# this local join is reliable and network-free. Idempotent: only fills nulls.
#
# Usage: python mlb_props_grade.py

import sqlite3
from mlb_config import MLB_DB_PATH

# props table -> (game-log table, actual stat column)
_GRADE = [
    ("mlb_props_predictions_k",    "mlb_pitcher_game_logs", "strikeouts"),
    ("mlb_props_predictions_hits", "mlb_batter_game_logs",  "hits"),
    ("mlb_props_predictions_tb",   "mlb_batter_game_logs",  "total_bases"),
]


def grade(conn, ptable: str, ltable: str, stat: str) -> int:
    cur = conn.execute(f"""
        UPDATE {ptable}
        SET actual_val = (
            SELECT l.{stat} FROM {ltable} l
            WHERE l.player_name = {ptable}.player_name
              AND l.game_date  = {ptable}.predict_date
            LIMIT 1
        )
        WHERE actual_val IS NULL
          AND EXISTS (
            SELECT 1 FROM {ltable} l
            WHERE l.player_name = {ptable}.player_name
              AND l.game_date  = {ptable}.predict_date
          )
    """)
    return cur.rowcount


def main():
    conn = sqlite3.connect(MLB_DB_PATH)
    print("── Grading MLB props from game logs ──")
    for ptable, ltable, stat in _GRADE:
        try:
            filled = grade(conn, ptable, ltable, stat)
            conn.commit()
            total = conn.execute(f"SELECT COUNT(*) FROM {ptable}").fetchone()[0]
            graded = conn.execute(
                f"SELECT COUNT(*) FROM {ptable} WHERE actual_val IS NOT NULL"
            ).fetchone()[0]
            print(f"  {ptable}: filled {filled} this run · {graded}/{total} graded")
        except sqlite3.OperationalError as e:
            print(f"  {ptable}: skipped ({e})")
    conn.close()
    print("  Done.")


if __name__ == "__main__":
    main()
