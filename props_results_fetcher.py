# props_results_fetcher.py
# Resolves player props predictions (points + rebounds) against actual box scores.
# Relies on collect_props.py having already pulled the day's player game logs.
#
# Usage:
#   python props_results_fetcher.py                    (all stats, yesterday + today)
#   python props_results_fetcher.py --date 2026-05-18  (specific date, all stats)
#   python props_results_fetcher.py --stat pts         (points only)
#   python props_results_fetcher.py --stat reb         (rebounds only)

import sqlite3
import argparse
import pandas as pd
from datetime import date, timedelta
from config import DB_PATH

# ── Stat configuration ─────────────────────────────────────────────────────────
STAT_CONFIGS = {
    "pts": {
        "pred_table":    "props_predictions",
        "bet_log_table": "props_bet_log",
        "actual_col":    "pts",
        "pred_col":      "pred_pts",
        "result_col":    "actual_pts",
        "label":         "Points",
    },
    "reb": {
        "pred_table":    "props_reb_predictions",
        "bet_log_table": "props_reb_bet_log",
        "actual_col":    "reb",
        "pred_col":      "pred_reb",
        "result_col":    "actual_reb",
        "label":         "Rebounds",
    },
    "ast": {
        "pred_table":    "props_ast_predictions",
        "bet_log_table": "props_ast_bet_log",
        "actual_col":    "ast",
        "pred_col":      "pred_ast",
        "result_col":    "actual_ast",
        "label":         "Assists",
    },
    "threes": {
        "pred_table":    "props_threes_predictions",
        "bet_log_table": "props_threes_bet_log",
        "actual_col":    "fg3m",
        "pred_col":      "pred_threes",
        "result_col":    "actual_threes",
        "label":         "3-Pointers",
    },
    "stl": {
        "pred_table":    "props_stl_predictions",
        "bet_log_table": "props_stl_bet_log",
        "actual_col":    "stl",
        "pred_col":      "pred_stl",
        "result_col":    "actual_stl",
        "label":         "Steals",
    },
    "blk": {
        "pred_table":    "props_blk_predictions",
        "bet_log_table": "props_blk_bet_log",
        "actual_col":    "blk",
        "pred_col":      "pred_blk",
        "result_col":    "actual_blk",
        "label":         "Blocks",
    },
}


def _bet_log_sql(cfg: dict) -> str:
    pred_col   = cfg["pred_col"]
    result_col = cfg["result_col"]
    label      = cfg["label"].lower()
    return f"""
        CREATE TABLE IF NOT EXISTS {cfg['bet_log_table']} (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date  TEXT,
            game_id       TEXT,
            player_name   TEXT,
            home_team     TEXT,
            away_team     TEXT,
            bet_side      TEXT,
            line          REAL,
            {pred_col}    REAL,
            ou_prob       REAL,
            edge          REAL,
            price         REAL,
            kelly_stake   REAL,
            result        TEXT,
            profit_units  REAL,
            {result_col}  REAL,
            recorded_at   TEXT
        )
    """


def get_conn():
    return sqlite3.connect(DB_PATH)


def norm_name(n: str) -> str:
    return str(n).lower().strip()


def resolve_date(game_date: str, conn, cfg: dict) -> int:
    """Look up actual stat from player_game_logs and resolve the predictions table."""
    actual_col = cfg["actual_col"]
    pred_col   = cfg["pred_col"]
    result_col = cfg["result_col"]
    pred_table = cfg["pred_table"]
    log_table  = cfg["bet_log_table"]
    label      = cfg["label"]

    try:
        actuals = pd.read_sql(f"""
            SELECT player_name, game_id, {actual_col}, min_played
            FROM player_game_logs
            WHERE game_date = ?
        """, conn, params=(game_date,))
    except Exception:
        print(f"  No player logs for {game_date}.")
        return 0

    if actuals.empty:
        print(f"  No player logs for {game_date} — run collect_props.py --date {game_date} first.")
        return 0

    actuals["key"] = actuals["player_name"].map(norm_name) + "|" + actuals["game_id"].astype(str)
    actual_lookup  = actuals.set_index("key")[actual_col].to_dict()
    mins_lookup    = actuals.set_index("key")["min_played"].to_dict()

    try:
        preds = pd.read_sql(f"""
            SELECT * FROM {pred_table}
            WHERE predict_date = ? AND {result_col} IS NULL
              AND (over_value = 1 OR under_value = 1)
        """, conn, params=(game_date,))
    except Exception:
        print(f"  {label}: no predictions table for {game_date}.")
        return 0

    if preds.empty:
        print(f"  {label}: no unresolved predictions for {game_date}.")
        return 0

    conn.execute(_bet_log_sql(cfg))

    resolved = 0
    for _, pred in preds.iterrows():
        key = norm_name(pred["player_name"]) + "|" + str(pred["game_id"])
        if key not in actual_lookup:
            continue

        actual_val = actual_lookup[key]
        min_played = mins_lookup.get(key, 0)

        conn.execute(f"""
            UPDATE {pred_table} SET {result_col} = ?
            WHERE player_name = ? AND game_id = ? AND predict_date = ?
        """, (actual_val, pred["player_name"], pred["game_id"], pred["predict_date"]))

        total_line  = pred["line"]
        actual_over = 1 if actual_val > total_line else 0

        for side in ["over", "under"]:
            if not pred.get(f"{side}_value"):
                continue

            if min_played < 5:
                print(f"  Skipping {pred['player_name']} — only {min_played:.0f} min played")
                continue

            won    = (side == "over" and actual_over == 1) or \
                     (side == "under" and actual_over == 0)
            result = "WIN" if won else "LOSS"
            price  = pred[f"{side}_price"]
            k      = pred[f"{side}_kelly"]
            profit = k * ((price/100) if price > 0 else (100/abs(price))) if won else -k
            prob   = pred[f"{side}_prob"]
            edge   = pred[f"{side}_edge"]
            label_str = f"O{total_line}" if side == "over" else f"U{total_line}"

            icon = "✅" if won else "❌"
            print(f"  {icon} {result} [{label}]: {pred['player_name']} {label_str} "
                  f"(actual: {actual_val:.0f}) | Edge: {edge:+.1%} | P&L: {profit:+.4f}u")

            existing = conn.execute(f"""
                SELECT id FROM {log_table}
                WHERE game_id=? AND predict_date=? AND player_name=? AND bet_side=?
            """, (pred["game_id"], pred["predict_date"],
                  pred["player_name"], side)).fetchone()

            if existing:
                conn.execute(f"""
                    UPDATE {log_table} SET result=?, profit_units=?, {result_col}=?
                    WHERE game_id=? AND predict_date=? AND player_name=? AND bet_side=?
                """, (result, profit, actual_val,
                      pred["game_id"], pred["predict_date"],
                      pred["player_name"], side))
            else:
                conn.execute(f"""
                    INSERT INTO {log_table}
                    (predict_date, game_id, player_name, home_team, away_team,
                     bet_side, line, {pred_col}, ou_prob, edge, price, kelly_stake,
                     result, profit_units, {result_col}, recorded_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
                """, (pred["predict_date"], pred["game_id"], pred["player_name"],
                      pred["home_team"], pred["away_team"],
                      side, total_line, pred[pred_col], prob, edge, price,
                      k, result, profit, actual_val))

        resolved += 1

    conn.commit()
    return resolved


def print_summary(conn, cfg: dict):
    try:
        df = pd.read_sql(f"""
            SELECT result, profit_units FROM {cfg['bet_log_table']}
            WHERE result IN ('WIN','LOSS')
        """, conn)
        if df.empty:
            print(f"  No completed {cfg['label'].lower()} bets yet.")
            return
        tb = len(df)
        tw = (df["result"] == "WIN").sum()
        tu = df["profit_units"].sum()
        print(f"\n-- {cfg['label']} Props Record ---")
        print(f"  All time : {tw}W - {tb-tw}L ({tw/tb:.1%})")
        print(f"  Units P&L: {tu:+.4f}")
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None,
                        help="Date to resolve (YYYY-MM-DD). Default: yesterday + today.")
    parser.add_argument("--stat", default="all",
                        choices=["all", "pts", "reb", "ast", "threes", "stl", "blk"],
                        help="Which stat to resolve (default: all).")
    args = parser.parse_args()

    if args.date:
        dates_to_try = [args.date]
    else:
        today     = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        dates_to_try = [yesterday, today]

    stats_to_run = list(STAT_CONFIGS.keys()) if args.stat == "all" else [args.stat]

    print(f"\n-- Props Results Fetcher ({', '.join(s.upper() for s in stats_to_run)}) ----")

    conn = get_conn()
    for stat in stats_to_run:
        cfg   = STAT_CONFIGS[stat]
        total = 0
        for d in dates_to_try:
            print(f"\n  [{cfg['label']}] Checking {d}...")
            n = resolve_date(d, conn, cfg)
            total += n
            if n:
                print(f"  Resolved {n} player(s) for {d}.")
        print(f"\n  [{cfg['label']}] Total resolved: {total} player-game(s).")
        print_summary(conn, cfg)

    conn.close()
