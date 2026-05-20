# props_results_fetcher.py
# Resolves player points props predictions against actual box score results.
# Relies on collect_props.py having already pulled the day's player game logs.
#
# Usage:
#   python props_results_fetcher.py                    (yesterday + today)
#   python props_results_fetcher.py --date 2026-05-18  (specific date)

import sqlite3
import argparse
import pandas as pd
from datetime import date, timedelta
from config import DB_PATH

_BET_LOG_SQL = """
    CREATE TABLE IF NOT EXISTS props_bet_log (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        predict_date  TEXT,
        game_id       TEXT,
        player_name   TEXT,
        home_team     TEXT,
        away_team     TEXT,
        bet_side      TEXT,
        line          REAL,
        pred_pts      REAL,
        ou_prob       REAL,
        edge          REAL,
        price         REAL,
        kelly_stake   REAL,
        result        TEXT,
        profit_units  REAL,
        actual_pts    REAL,
        recorded_at   TEXT
    )
"""


def get_conn():
    return sqlite3.connect(DB_PATH)


def norm_name(n: str) -> str:
    return str(n).lower().strip()


def resolve_date(game_date: str, conn) -> int:
    """Look up actual player pts from player_game_logs and resolve props_predictions."""
    actuals = pd.read_sql("""
        SELECT player_name, game_id, pts, min_played
        FROM player_game_logs
        WHERE game_date = ?
    """, conn, params=(game_date,))

    if actuals.empty:
        print(f"  No player logs for {game_date} — run collect_props.py --date {game_date} first.")
        return 0

    # Build lookup: (norm_name, game_id) -> pts
    actuals["key"] = actuals["player_name"].map(norm_name) + "|" + actuals["game_id"].astype(str)
    actual_lookup  = actuals.set_index("key")["pts"].to_dict()
    mins_lookup    = actuals.set_index("key")["min_played"].to_dict()

    preds = pd.read_sql("""
        SELECT * FROM props_predictions
        WHERE predict_date = ? AND actual_pts IS NULL
          AND (over_value = 1 OR under_value = 1)
    """, conn, params=(game_date,))

    if preds.empty:
        print(f"  No unresolved props predictions for {game_date}.")
        return 0

    conn.execute(_BET_LOG_SQL)

    resolved = 0
    for _, pred in preds.iterrows():
        key = norm_name(pred["player_name"]) + "|" + str(pred["game_id"])
        if key not in actual_lookup:
            continue

        actual_pts = actual_lookup[key]
        min_played = mins_lookup.get(key, 0)

        # Update actual_pts in predictions table
        conn.execute("""
            UPDATE props_predictions SET actual_pts = ?
            WHERE player_name = ? AND game_id = ? AND predict_date = ?
        """, (actual_pts, pred["player_name"], pred["game_id"], pred["predict_date"]))

        total_line  = pred["line"]
        actual_over = 1 if actual_pts > total_line else 0

        for side in ["over", "under"]:
            if not pred.get(f"{side}_value"):
                continue

            # Skip if player barely played (DNP / injury)
            if min_played < 5:
                print(f"  Skipping {pred['player_name']} — only {min_played:.0f} min played")
                continue

            won    = (side == "over" and actual_over == 1) or \
                     (side == "under" and actual_over == 0)
            result = "WIN" if won else "LOSS"
            price  = pred[f"{side}_price"]
            kelly  = pred[f"{side}_kelly"]
            profit = kelly * ((price/100) if price > 0 else (100/abs(price))) if won else -kelly
            prob   = pred[f"{side}_prob"]
            edge   = pred[f"{side}_edge"]
            label  = f"O{total_line}" if side == "over" else f"U{total_line}"

            icon = "✅" if won else "❌"
            print(f"  {icon} {result}: {pred['player_name']} {label} "
                  f"(actual: {actual_pts:.0f}) | Edge: {edge:+.1%} | P&L: {profit:+.4f}u")

            existing = conn.execute("""
                SELECT id FROM props_bet_log
                WHERE game_id=? AND predict_date=? AND player_name=? AND bet_side=?
            """, (pred["game_id"], pred["predict_date"],
                  pred["player_name"], side)).fetchone()

            if existing:
                conn.execute("""
                    UPDATE props_bet_log SET result=?, profit_units=?, actual_pts=?
                    WHERE game_id=? AND predict_date=? AND player_name=? AND bet_side=?
                """, (result, profit, actual_pts,
                      pred["game_id"], pred["predict_date"],
                      pred["player_name"], side))
            else:
                conn.execute("""
                    INSERT INTO props_bet_log
                    (predict_date, game_id, player_name, home_team, away_team,
                     bet_side, line, pred_pts, ou_prob, edge, price, kelly_stake,
                     result, profit_units, actual_pts, recorded_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
                """, (pred["predict_date"], pred["game_id"], pred["player_name"],
                      pred["home_team"], pred["away_team"],
                      side, total_line, pred["pred_pts"], prob, edge, price,
                      kelly, result, profit, actual_pts))

        resolved += 1

    conn.commit()
    return resolved


def print_summary(conn):
    try:
        df = pd.read_sql("""
            SELECT result, profit_units FROM props_bet_log
            WHERE result IN ('WIN','LOSS')
        """, conn)
        if df.empty:
            print("  No completed props bets yet.")
            return
        tb = len(df)
        tw = (df["result"] == "WIN").sum()
        tu = df["profit_units"].sum()
        print(f"\n-- Props Running Record -----------------------------------------")
        print(f"  All time : {tw}W - {tb-tw}L ({tw/tb:.1%})")
        print(f"  Units P&L: {tu:+.4f}")
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None,
                        help="Date to resolve (YYYY-MM-DD). Default: yesterday + today.")
    args = parser.parse_args()

    if args.date:
        dates_to_try = [args.date]
    else:
        today     = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        dates_to_try = [yesterday, today]

    print(f"\n-- Props Results Fetcher -------------------------------------------")

    conn = get_conn()
    total = 0
    for d in dates_to_try:
        print(f"\n  Checking {d}...")
        n = resolve_date(d, conn)
        total += n
        if n:
            print(f"  Resolved {n} player(s) for {d}.")

    print(f"\n  Total resolved: {total} player-game(s).")
    print_summary(conn)
    conn.close()
