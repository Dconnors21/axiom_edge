# ── clv_tracker.py ────────────────────────────────────────────────────────────
# Closing Line Value (CLV) tracker.
# CLV measures whether the line moved toward or against your pick after you bet.
# Positive CLV = sharp money agreed with you = genuine edge signal.
#
# Usage: python clv_tracker.py --update   (enter closing lines)
#        python clv_tracker.py --report   (show CLV analysis)
#        python clv_tracker.py --auto     (auto-fetch closing lines from odds API)

import sqlite3
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from config import DB_PATH, ODDS_API_KEY, ODDS_SPORT, SHARP_BOOKS

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_clv_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS closing_lines (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            game_date       TEXT,
            game_id         TEXT,
            home_team       TEXT,
            away_team       TEXT,
            home_open       REAL,   -- opening home moneyline
            away_open       REAL,   -- opening away moneyline
            home_close      REAL,   -- closing home moneyline
            away_close      REAL,   -- closing away moneyline
            bookmaker       TEXT,
            recorded_at     TEXT,
            UNIQUE(game_date, game_id, bookmaker)
        )
    """)
    conn.commit()

def american_to_implied(odds: float) -> float:
    if odds is None or np.isnan(float(odds)):
        return 0.5
    odds = float(odds)
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def implied_to_american(prob: float) -> str:
    prob = max(0.01, min(0.99, prob))
    if prob >= 0.5:
        return f"-{round(prob/(1-prob)*100)}"
    return f"+{round((1-prob)/prob*100)}"

def fetch_closing_lines_auto(game_date: str) -> pd.DataFrame:
    """
    Fetch current odds from The Odds API.
    When run right before game time, these approximate closing lines.
    """
    url = f"https://api.the-odds-api.com/v4/sports/{ODDS_SPORT}/odds"
    params = {
        "apiKey":     ODDS_API_KEY,
        "regions":    "us",
        "markets":    "h2h",
        "oddsFormat": "american",
        "dateFormat": "iso",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"  Odds API returned {resp.status_code}")
            return pd.DataFrame()

        data     = resp.json()
        remaining = resp.headers.get("x-requests-remaining","?")
        print(f"  Fetched {len(data)} games (requests remaining: {remaining})")

        rows = []
        for game in data:
            for bookmaker in game.get("bookmakers", []):
                if bookmaker["key"] not in SHARP_BOOKS:
                    continue
                for market in bookmaker.get("markets", []):
                    if market["key"] != "h2h":
                        continue
                    outcomes = {o["name"]: o["price"]
                                for o in market.get("outcomes", [])}
                    home_price = outcomes.get(game["home_team"])
                    away_price = outcomes.get(game["away_team"])
                    rows.append({
                        "game_id":   game["id"],
                        "home_team": game["home_team"],
                        "away_team": game["away_team"],
                        "home_close": home_price,
                        "away_close": away_price,
                        "bookmaker":  bookmaker["key"],
                        "game_date":  game_date,
                    })
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"  Auto-fetch failed: {e}")
        return pd.DataFrame()

def manual_closing_line_entry(conn, game_date: str):
    """Interactive entry of closing lines for yesterday's games."""
    preds = pd.read_sql("""
        SELECT p.*, cl.home_close, cl.away_close
        FROM predictions p
        LEFT JOIN closing_lines cl ON p.game_id = cl.game_id
            AND cl.game_date = p.predict_date
        WHERE p.predict_date = ?
          AND (p.home_value = 1 OR p.away_value = 1)
    """, conn, params=(game_date,))

    if preds.empty:
        print(f"  No value bets found for {game_date}")
        return

    print(f"\n── Enter closing lines for {game_date} ──────────────────")
    print("  (Check DraftKings/FanDuel for the line right before tip-off)")
    print("  Format: American odds e.g. -150 or +130\n")

    for _, pred in preds.iterrows():
        # Skip if already have closing line
        if pd.notna(pred.get("home_close")):
            continue

        home = pred["home_team"]
        away = pred["away_team"]
        print(f"  {away} @ {home}")
        print(f"  Opening line — Home: {int(pred.get('home_price',0)):+d} "
              f"Away: {int(pred.get('away_price',0)):+d}")

        try:
            home_close = float(input(f"  Closing line — {home}: ").strip())
            away_close = float(input(f"  Closing line — {away}: ").strip())
        except ValueError:
            print("  Invalid input — skipping")
            continue

        conn.execute("""
            INSERT OR REPLACE INTO closing_lines
            (game_date, game_id, home_team, away_team,
             home_open, away_open, home_close, away_close,
             bookmaker, recorded_at)
            VALUES (?,?,?,?,?,?,?,?,'manual',datetime('now'))
        """, (game_date, pred["game_id"], home, away,
              pred.get("home_price"), pred.get("away_price"),
              home_close, away_close))
        conn.commit()
        print(f"  ✓ Saved closing line for {away} @ {home}\n")

def calculate_clv(conn, game_date: str) -> pd.DataFrame:
    """
    Calculate CLV for all value bets on a given date.
    CLV = (closing implied prob - opening implied prob) * direction
    Positive CLV means the line moved in your favor.
    """
    df = pd.read_sql("""
        SELECT p.game_id, p.predict_date, p.home_team, p.away_team,
               p.home_value, p.away_value,
               p.model_home_prob, p.model_away_prob,
               p.home_fair_prob, p.away_fair_prob,
               p.home_edge, p.away_edge,
               p.home_price, p.away_price,
               p.actual_home_win,
               cl.home_open, cl.away_open,
               cl.home_close, cl.away_close
        FROM predictions p
        LEFT JOIN closing_lines cl ON p.game_id = cl.game_id
            AND cl.game_date = p.predict_date
        WHERE p.predict_date = ?
          AND (p.home_value = 1 OR p.away_value = 1)
    """, conn, params=(game_date,))

    if df.empty:
        return pd.DataFrame()

    rows = []
    for _, row in df.iterrows():
        for side in ["home", "away"]:
            if not row.get(f"{side}_value"):
                continue

            open_line  = row.get(f"{side}_price")
            close_line = row.get(f"{side}_close")

            if pd.isna(open_line) or pd.isna(close_line):
                clv = None
            else:
                open_implied  = american_to_implied(open_line)
                close_implied = american_to_implied(close_line)
                # CLV: positive means line got worse (book moved against you)
                # which paradoxically means sharp money disagreed = bad sign
                # We want: close_implied < open_implied (line got better for us)
                clv = open_implied - close_implied

            won = (side=="home" and row.get("actual_home_win")==1) or \
                  (side=="away" and row.get("actual_home_win")==0)

            rows.append({
                "date":        row["predict_date"],
                "matchup":     f"{row['away_team']} @ {row['home_team']}",
                "bet_side":    side,
                "bet_team":    row[f"{side}_team"] if f"{side}_team" in row else
                               row["home_team"] if side=="home" else row["away_team"],
                "open_line":   open_line,
                "close_line":  close_line,
                "model_edge":  row.get(f"{side}_edge"),
                "clv":         clv,
                "result":      "WIN" if won else ("LOSS" if row.get("actual_home_win") is not None else "PENDING"),
            })

    return pd.DataFrame(rows)

def update_bet_log_clv(clv_df: pd.DataFrame, conn):
    """Write CLV values back to bet_log."""
    if clv_df.empty:
        return
    for _, row in clv_df.iterrows():
        if row["clv"] is not None:
            conn.execute("""
                UPDATE bet_log SET clv = ?
                WHERE predict_date = ?
                  AND bet_side = ?
                  AND home_team = ?
            """, (row["clv"], row["date"], row["bet_side"],
                  row["matchup"].split(" @ ")[1]))
    conn.commit()

def print_clv_report(conn):
    """Full CLV analysis report."""
    df = pd.read_sql("""
        SELECT bl.*, cl.home_close, cl.away_close
        FROM bet_log bl
        LEFT JOIN closing_lines cl ON bl.game_id = cl.game_id
            AND cl.game_date = bl.predict_date
        WHERE bl.result IN ('WIN','LOSS')
        ORDER BY bl.predict_date DESC
    """, conn)

    if df.empty:
        print("  No completed bets with CLV data yet.")
        return

    has_clv = df[df["clv"].notna()]

    print(f"\n{'='*58}")
    print(f"  CLOSING LINE VALUE ANALYSIS")
    print(f"{'='*58}")
    print(f"  Total bets tracked    : {len(df)}")
    print(f"  Bets with CLV data    : {len(has_clv)}")

    if not has_clv.empty:
        avg_clv   = has_clv["clv"].mean()
        pos_clv   = (has_clv["clv"] > 0).sum()
        neg_clv   = (has_clv["clv"] <= 0).sum()
        avg_edge  = has_clv["edge"].mean()

        print(f"\n── CLV Summary ──────────────────────────────────────────")
        print(f"  Avg CLV              : {avg_clv:+.2%}")
        print(f"  Positive CLV bets    : {pos_clv} ({pos_clv/len(has_clv):.0%})")
        print(f"  Negative CLV bets    : {neg_clv} ({neg_clv/len(has_clv):.0%})")
        print(f"  Avg model edge       : {avg_edge:+.2%}")

        # CLV vs outcomes
        pos_clv_wins = has_clv[has_clv["clv"] > 0]["result"].value_counts()
        neg_clv_wins = has_clv[has_clv["clv"] <= 0]["result"].value_counts()

        pos_win_rate = pos_clv_wins.get("WIN",0) / max(len(has_clv[has_clv["clv"]>0]),1)
        neg_win_rate = neg_clv_wins.get("WIN",0) / max(len(has_clv[has_clv["clv"]<=0]),1)

        print(f"\n── CLV vs Results ───────────────────────────────────────")
        print(f"  Win rate w/ pos CLV  : {pos_win_rate:.1%}  "
              f"({len(has_clv[has_clv['clv']>0])} bets)")
        print(f"  Win rate w/ neg CLV  : {neg_win_rate:.1%}  "
              f"({len(has_clv[has_clv['clv']<=0])} bets)")

        if pos_win_rate > neg_win_rate:
            print(f"\n  ✓ Positive CLV bets are winning at a higher rate —")
            print(f"    sharp money is agreeing with your model!")
        else:
            print(f"\n  ⚠ Negative CLV bets winning more — model may need")
            print(f"    recalibration or sample size is too small.")

        print(f"\n── Individual CLV records ───────────────────────────────")
        print(f"  {'Date':<12} {'Team':<25} {'Open':>8} {'Close':>8} "
              f"{'CLV':>7} {'Result':<8}")
        print(f"  {'─'*70}")
        for _, row in has_clv.sort_values("predict_date", ascending=False).iterrows():
            open_str  = f"{int(row['open_line']):+d}"  if pd.notna(row.get('open_line'))  else "N/A"
            close_str = f"{int(row['close_line']):+d}" if pd.notna(row.get('close_line')) else "N/A"
            clv_str   = f"{row['clv']:+.1%}" if pd.notna(row['clv']) else "N/A"
            result_icon = "✅" if row["result"]=="WIN" else "❌"
            bet_team = str(row.get('bet_team',''))[:23]
            print(f"  {str(row['predict_date'])[:10]:<12} {bet_team:<25} "
                  f"{open_str:>8} {close_str:>8} {clv_str:>7} "
                  f"{result_icon} {row['result']}")

    print(f"\n  Tip: Sustained positive CLV (>0%) over 50+ bets")
    print(f"  is the strongest indicator of genuine model edge.")
    print(f"{'='*58}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CLV Tracker")
    parser.add_argument("--update", action="store_true",
                        help="Enter closing lines manually")
    parser.add_argument("--auto",   action="store_true",
                        help="Auto-fetch closing lines from Odds API")
    parser.add_argument("--report", action="store_true",
                        help="Show CLV analysis report")
    parser.add_argument("--date",   default=None,
                        help="Date to process (YYYY-MM-DD), default: yesterday")
    args = parser.parse_args()

    from datetime import timedelta
    game_date = args.date or (date.today() - timedelta(days=1)).isoformat()

    print(f"\n── CLV Tracker — {game_date} ─────────────────────────────")

    conn = get_conn()
    init_clv_table(conn)

    if args.auto:
        print("  Fetching closing lines from Odds API...")
        cl_df = fetch_closing_lines_auto(game_date)
        if not cl_df.empty:
            cl_df["home_open"] = None
            cl_df["away_open"] = None
            cl_df["game_date"] = game_date
            cl_df["recorded_at"] = datetime.utcnow().isoformat()
            cl_df.to_sql("closing_lines", conn, if_exists="append",
                         index=False)
            conn.commit()
            print(f"  Saved {len(cl_df)} closing lines")
            clv_df = calculate_clv(conn, game_date)
            if not clv_df.empty:
                update_bet_log_clv(clv_df, conn)

    elif args.update:
        manual_closing_line_entry(conn, game_date)
        clv_df = calculate_clv(conn, game_date)
        if not clv_df.empty:
            update_bet_log_clv(clv_df, conn)
            print("\n── CLV for today's bets ─────────────────────────────────")
            for _, row in clv_df.iterrows():
                clv_str = f"{row['clv']:+.1%}" if row["clv"] is not None else "pending"
                print(f"  {row['bet_team'][:28]:<28} CLV: {clv_str}")

    if args.report or not (args.update or args.auto):
        print_clv_report(conn)

    conn.close()
