# ── tracker.py ────────────────────────────────────────────────────────────────
# Records bet outcomes and calculates running ROI, win rate, and CLV.
# Run this after games complete each night.
#
# Usage:
#   python tracker.py --results          # show today's predictions
#   python tracker.py --update           # interactive: enter actual results
#   python tracker.py --record DATE HT RESULT  # record specific game
#   python tracker.py --summary          # full ROI summary

import sqlite3
import argparse
import pandas as pd
import numpy as np
from datetime import date, datetime
from config import DB_PATH

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_tracker_tables(conn):
    """Create bet log table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bet_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date    TEXT,
            game_id         TEXT,
            home_team       TEXT,
            away_team       TEXT,
            bet_side        TEXT,    -- 'home' or 'away'
            bet_team        TEXT,    -- team name we bet on
            model_prob      REAL,
            fair_prob       REAL,
            edge            REAL,
            line            REAL,    -- american odds
            kelly_stake     REAL,    -- fraction of bankroll
            result          TEXT,    -- 'WIN', 'LOSS', 'PUSH', 'PENDING'
            profit_units    REAL,    -- profit in units (1 unit = 1% bankroll)
            clv             REAL,    -- closing line value (fill in manually)
            notes           TEXT,
            recorded_at     TEXT
        )
    """)
    conn.commit()

def load_pending_predictions(conn) -> pd.DataFrame:
    """Load predictions that haven't been resolved yet."""
    df = pd.read_sql("""
        SELECT p.*,
               bl.result as logged_result
        FROM predictions p
        LEFT JOIN bet_log bl ON p.game_id = bl.game_id
            AND p.predict_date = bl.predict_date
        WHERE (p.home_value = 1 OR p.away_value = 1)
        ORDER BY p.predict_date DESC, p.commence_time
    """, conn)
    return df

def record_result(conn, game_id: str, predict_date: str,
                  home_team: str, away_team: str,
                  actual_home_win: int):
    """Record actual game result and calculate P&L for any value bets."""

    # Get the prediction
    pred = pd.read_sql("""
        SELECT * FROM predictions
        WHERE game_id = ? AND predict_date = ?
    """, conn, params=(game_id, predict_date))

    if pred.empty:
        print(f"  No prediction found for game {game_id} on {predict_date}")
        return

    row = pred.iloc[0]

    # Update actual result in predictions table
    conn.execute("""
        UPDATE predictions SET actual_home_win = ?
        WHERE game_id = ? AND predict_date = ?
    """, (actual_home_win, game_id, predict_date))

    # Log each value bet
    for side in ["home", "away"]:
        if not row.get(f"{side}_value"):
            continue

        model_prob = row[f"model_{side}_prob"]
        fair_prob  = row[f"{side}_fair_prob"]
        edge       = row[f"{side}_edge"]
        line       = row[f"{side}_price"]
        kelly      = row[f"{side}_kelly"]
        bet_team   = row[f"{side}_team"]

        # Determine result
        if side == "home":
            won = actual_home_win == 1
        else:
            won = actual_home_win == 0

        result = "WIN" if won else "LOSS"

        # Calculate profit in units (Kelly stake * win/loss)
        if won:
            if line > 0:
                profit = kelly * (line / 100)
            else:
                profit = kelly * (100 / abs(line))
        else:
            profit = -kelly

        conn.execute("""
            INSERT OR REPLACE INTO bet_log
            (predict_date, game_id, home_team, away_team, bet_side, bet_team,
             model_prob, fair_prob, edge, line, kelly_stake, result,
             profit_units, recorded_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        """, (predict_date, game_id, home_team, away_team, side, bet_team,
              model_prob, fair_prob, edge, line, kelly, result, profit))

        icon = "✅" if won else "❌"
        print(f"  {icon} {result}: {bet_team} | Edge: {edge:+.1%} | "
              f"P&L: {profit:+.3f} units")

    conn.commit()

def show_summary(conn):
    """Print full ROI summary."""
    df = pd.read_sql("""
        SELECT * FROM bet_log
        WHERE result IN ('WIN', 'LOSS')
        ORDER BY predict_date ASC
    """, conn)

    if df.empty:
        print("  No completed bets yet.")
        return

    total_bets  = len(df)
    wins        = (df["result"] == "WIN").sum()
    win_rate    = wins / total_bets
    total_units = df["profit_units"].sum()
    avg_edge    = df["edge"].mean()
    avg_kelly   = df["kelly_stake"].mean()

    # ROI by month
    df["month"] = pd.to_datetime(df["predict_date"]).dt.to_period("M").astype(str)
    monthly = df.groupby("month").agg(
        bets=("result","count"),
        wins=("result", lambda x: (x=="WIN").sum()),
        units=("profit_units","sum")
    ).reset_index()
    monthly["win_pct"] = monthly["wins"] / monthly["bets"]

    print(f"\n{'='*55}")
    print(f"  MODEL PERFORMANCE TRACKER")
    print(f"{'='*55}")
    print(f"  Total bets    : {total_bets}")
    print(f"  Win rate      : {win_rate:.1%}  ({wins}W - {total_bets-wins}L)")
    print(f"  Total P&L     : {total_units:+.3f} units")
    print(f"  Avg edge      : {avg_edge:+.1%}")
    print(f"  Avg Kelly     : {avg_kelly:.1%} of bankroll")

    # Streak
    results = df["result"].tolist()
    current_streak = 1
    for i in range(len(results)-2, -1, -1):
        if results[i] == results[-1]:
            current_streak += 1
        else:
            break
    streak_type = "W" if results[-1] == "WIN" else "L"
    print(f"  Current streak: {current_streak}{streak_type}")

    print(f"\n── Monthly breakdown ────────────────────────────────")
    print(f"  {'Month':<12} {'Bets':>6} {'W-L':>8} {'Win%':>8} {'Units':>8}")
    print(f"  {'─'*46}")
    for _, row in monthly.iterrows():
        wl = f"{int(row['wins'])}W-{int(row['bets']-row['wins'])}L"
        print(f"  {row['month']:<12} {int(row['bets']):>6} {wl:>8} "
              f"{row['win_pct']:>7.1%} {row['units']:>+8.3f}")

    print(f"\n── Best bets ─────────────────────────────────────────")
    top = df.nlargest(5, "profit_units")[["predict_date","bet_team","edge","line","result","profit_units"]]
    for _, r in top.iterrows():
        print(f"  {r['predict_date']} | {r['bet_team']:<28} | "
              f"Edge:{r['edge']:+.1%} | {r['result']} | {r['profit_units']:+.3f}u")

    print(f"\n── Worst bets ────────────────────────────────────────")
    bot = df.nsmallest(5, "profit_units")[["predict_date","bet_team","edge","line","result","profit_units"]]
    for _, r in bot.iterrows():
        print(f"  {r['predict_date']} | {r['bet_team']:<28} | "
              f"Edge:{r['edge']:+.1%} | {r['result']} | {r['profit_units']:+.3f}u")

    print(f"{'='*55}\n")

def interactive_update(conn):
    """Walk through pending predictions and record results."""
    pending = load_pending_predictions(conn)
    unresolved = pending[pending["actual_home_win"].isna() |
                         (pending["actual_home_win"] == "")]

    if unresolved.empty:
        print("  All predictions are resolved!")
        return

    print(f"\n  {len(unresolved)} game(s) need results:\n")
    for _, row in unresolved.iterrows():
        print(f"  {row['away_team']} @ {row['home_team']}  ({row['predict_date']})")
        result = input(f"  Who won? (h = {row['home_team']}, a = {row['away_team']}, s = skip): ").strip().lower()
        if result == "h":
            record_result(conn, row["game_id"], row["predict_date"],
                          row["home_team"], row["away_team"], 1)
        elif result == "a":
            record_result(conn, row["game_id"], row["predict_date"],
                          row["home_team"], row["away_team"], 0)
        else:
            print("  Skipped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NBA Bet Tracker")
    parser.add_argument("--results",  action="store_true", help="Show pending predictions")
    parser.add_argument("--update",   action="store_true", help="Interactive result entry")
    parser.add_argument("--summary",  action="store_true", help="Show ROI summary")
    args = parser.parse_args()

    conn = get_conn()
    init_tracker_tables(conn)

    if args.results:
        df = load_pending_predictions(conn)
        print(df[["predict_date","home_team","away_team",
                   "model_home_prob","home_edge","away_edge",
                   "home_value","away_value","actual_home_win"]].to_string())
    elif args.update:
        interactive_update(conn)
        show_summary(conn)
    elif args.summary:
        show_summary(conn)
    else:
        # Default: show pending then summary
        interactive_update(conn)
        show_summary(conn)

    conn.close()
