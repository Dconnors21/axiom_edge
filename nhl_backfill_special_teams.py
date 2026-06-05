# ── nhl_backfill_special_teams.py ─────────────────────────────────────────────
# One-time (resumable) backfill of PP / PIM / hits / blocks for NHL games whose
# special-teams columns are NULL. These were never populated because the old
# collector read them from the boxscore `homeTeam` object, where the NHL API
# does not expose them — they live in gamecenter/{id}/right-rail teamGameStats.
#
# Safe to re-run: only touches rows still missing power-play data, and commits
# in batches so an interrupted run keeps its progress.
#
# Usage:
#   python nhl_backfill_special_teams.py            # backfill all NULL rows
#   python nhl_backfill_special_teams.py --limit 50 # smoke-test on 50 games

import time
import argparse
import sqlite3
from nhl_config import NHL_DB_PATH
from nhl_collect import NHL_API, _get, parse_team_stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process the first N missing games (smoke test).")
    parser.add_argument("--sleep", type=float, default=0.15,
                        help="Delay between API calls (seconds).")
    args = parser.parse_args()

    conn = sqlite3.connect(NHL_DB_PATH)
    rows = conn.execute(
        "SELECT game_id FROM nhl_games "
        "WHERE home_pp_opp IS NULL ORDER BY game_date DESC"
    ).fetchall()
    game_ids = [r[0] for r in rows]
    if args.limit:
        game_ids = game_ids[:args.limit]

    total = len(game_ids)
    print(f"── NHL special-teams backfill — {total} game(s) missing PP data ──")
    if not total:
        conn.close()
        return

    updated = skipped = 0
    for i, gid in enumerate(game_ids, 1):
        ts = parse_team_stats(_get(f"{NHL_API}/gamecenter/{gid}/right-rail"))
        if ts["home_pp_opp"] is None and ts["away_pp_opp"] is None:
            skipped += 1  # no stats available (very old game / API gap)
        else:
            conn.execute("""
                UPDATE nhl_games SET
                    home_pp_goals=?, home_pp_opp=?, away_pp_goals=?, away_pp_opp=?,
                    home_pim=?, away_pim=?, home_hits=?, away_hits=?,
                    home_blocks=?, away_blocks=?
                WHERE game_id=?
            """, (
                ts["home_pp_goals"], ts["home_pp_opp"],
                ts["away_pp_goals"], ts["away_pp_opp"],
                ts["home_pim"], ts["away_pim"],
                ts["home_hits"], ts["away_hits"],
                ts["home_blocks"], ts["away_blocks"],
                gid,
            ))
            updated += 1

        if i % 100 == 0:
            conn.commit()
            print(f"  {i}/{total} processed — {updated} updated, {skipped} no-data")
        time.sleep(args.sleep)

    conn.commit()
    conn.close()
    print(f"Done — {updated} updated, {skipped} had no stats, of {total} processed.")


if __name__ == "__main__":
    main()
