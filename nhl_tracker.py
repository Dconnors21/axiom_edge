# ── nhl_tracker.py ────────────────────────────────────────────────────────────
# Computes NHL ROI summary stats from the bet logs.
# Usage: python nhl_tracker.py   (prints a console summary)

import sqlite3
import pandas as pd
from nhl_config import NHL_DB_PATH

def get_conn():
    return sqlite3.connect(NHL_DB_PATH)

def _summary(df: pd.DataFrame, label: str):
    if df.empty:
        print(f"  {label}: no bets logged yet")
        return
    resolved = df.dropna(subset=["won"])
    if resolved.empty:
        print(f"  {label}: no resolved bets yet")
        return
    wins  = resolved["won"].sum()
    total = len(resolved)
    units = resolved["pnl"].sum()
    roi   = units / total * 100
    print(f"  {label}: {wins}-{total - wins} ({wins/total:.1%} WR) | "
          f"{units:+.2f}u | ROI {roi:+.1f}%")

def main():
    print("── NHL ROI Tracker ───────────────────────────────────────────────────────")
    conn = get_conn()

    for table, label in [
        ("nhl_bet_log",        "Moneyline"),
        ("nhl_ats_bet_log",    "Puck Line (ATS)"),
        ("nhl_totals_bet_log", "Totals (O/U)"),
    ]:
        try:
            df = pd.read_sql(f"SELECT * FROM {table}", conn)
            _summary(df, label)
        except Exception:
            print(f"  {label}: table not found — run nhl_results_fetcher.py first")

    conn.close()

if __name__ == "__main__":
    main()
