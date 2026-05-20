# ── mlb_results_fetcher.py ────────────────────────────────────────────────────
# Fetches final MLB scores from the free MLB Stats API and updates predictions.
#
# Usage:
#   python mlb_results_fetcher.py                    (yesterday + today)
#   python mlb_results_fetcher.py --date 2026-05-18  (specific date)

import sqlite3
import argparse
import requests
import time
import pandas as pd
from datetime import date, datetime, timedelta
from mlb_config import MLB_DB_PATH

def get_conn():
    return sqlite3.connect(MLB_DB_PATH)

def fetch_mlb_scores(game_date: str) -> pd.DataFrame:
    """Fetch final scores from the free MLB Stats API."""
    print(f"  Fetching MLB scores for {game_date}...")
    url = (f"https://statsapi.mlb.com/api/v1/schedule"
           f"?sportId=1&date={game_date}"
           f"&hydrate=linescore,team")
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            print(f"  MLB API returned {resp.status_code}")
            return pd.DataFrame()

        data  = resp.json()
        rows  = []
        for d in data.get("dates", []):
            for game in d.get("games", []):
                status    = game.get("status", {})
                game_pk   = game.get("gamePk")
                abstract  = status.get("abstractGameState","")
                detailed  = status.get("detailedState","")

                # Only process final games
                if abstract != "Final":
                    continue

                home      = game["teams"]["home"]
                away      = game["teams"]["away"]
                home_name = home["team"]["name"]
                away_name = away["team"]["name"]
                home_abbr = home["team"].get("abbreviation","")
                away_abbr = away["team"].get("abbreviation","")
                home_score = home.get("score", 0) or 0
                away_score = away.get("score", 0) or 0

                # Skip 0-0 (game not played / postponed)
                if home_score == 0 and away_score == 0:
                    continue

                rows.append({
                    "game_pk":    game_pk,
                    "home_name":  home_name,
                    "away_name":  away_name,
                    "home_abbr":  home_abbr,
                    "away_abbr":  away_abbr,
                    "home_score": int(home_score),
                    "away_score": int(away_score),
                    "home_win":   1 if int(home_score) > int(away_score) else 0,
                })

        df = pd.DataFrame(rows)
        if not df.empty:
            print(f"  Found {len(df)} final game(s).")
        else:
            print(f"  No final games for {game_date}.")
        return df

    except Exception as e:
        print(f"  Failed: {e}")
        return pd.DataFrame()

def match_team(api_name: str, pred_name: str) -> bool:
    """Fuzzy match between MLB API team name and our stored team name."""
    api_words  = [w for w in str(api_name).split() if len(w) > 3]
    pred_lower = str(pred_name).lower()
    return any(w.lower() in pred_lower for w in api_words)

def _record_spread_result(conn, spread_pred, home_score, away_score):
    actual_margin     = home_score - away_score
    home_point        = spread_pred.get("home_point")
    if home_point is None:
        return
    actual_home_cover = 1 if (actual_margin + home_point) > 0 else 0

    conn.execute("""
        UPDATE mlb_spread_predictions SET actual_home_cover = ?
        WHERE game_id=? AND predict_date=?
    """, (actual_home_cover, spread_pred["game_id"], spread_pred["predict_date"]))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_ats_bet_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date  TEXT, game_id TEXT,
            home_team     TEXT, away_team TEXT,
            bet_side      TEXT, bet_team TEXT,
            spread        REAL, pred_margin REAL,
            cover_prob    REAL, edge REAL,
            line          REAL, kelly_stake REAL,
            result        TEXT, profit_units REAL,
            clv           REAL,
            recorded_at   TEXT
        )
    """)

    for side in ["home", "away"]:
        if not spread_pred.get(f"{side}_ats_value"):
            continue
        bet_team = spread_pred["home_team"] if side == "home" else spread_pred["away_team"]
        won      = (side == "home" and actual_home_cover == 1) or \
                   (side == "away" and actual_home_cover == 0)
        result   = "WIN" if won else "LOSS"
        line     = spread_pred[f"{side}_price"]
        kelly_s  = spread_pred[f"{side}_ats_kelly"]
        spread   = spread_pred.get(f"{side}_point")
        profit   = kelly_s * ((line/100) if line > 0 else (100/abs(line))) if won else -kelly_s

        icon = "✅" if won else "❌"
        print(f"    {icon} RL {result}: {bet_team} {f'{spread:+.1f}' if spread else ''} | "
              f"P&L: {profit:+.4f}u")

        # CLV = closing vig-free prob minus opening vig-free prob
        closing = conn.execute("""
            SELECT close_fair_prob FROM mlb_closing_odds
            WHERE game_id=? AND market='spreads' AND side=?
        """, (spread_pred["game_id"], side)).fetchone()
        open_fair = (spread_pred.get(f"{side}_cover_prob") or 0.5) - (spread_pred.get(f"{side}_ats_edge") or 0)
        clv = float(closing[0]) - open_fair if closing else None

        existing = conn.execute("""
            SELECT id FROM mlb_ats_bet_log
            WHERE game_id=? AND predict_date=? AND bet_side=?
        """, (spread_pred["game_id"], spread_pred["predict_date"], side)).fetchone()

        if existing:
            conn.execute("""
                UPDATE mlb_ats_bet_log SET result=?, profit_units=?, clv=?
                WHERE game_id=? AND predict_date=? AND bet_side=?
            """, (result, profit, clv, spread_pred["game_id"], spread_pred["predict_date"], side))
        else:
            conn.execute("""
                INSERT INTO mlb_ats_bet_log
                (predict_date, game_id, home_team, away_team, bet_side, bet_team,
                 spread, pred_margin, cover_prob, edge, line, kelly_stake,
                 result, profit_units, clv, recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (spread_pred["predict_date"], spread_pred["game_id"],
                  spread_pred["home_team"], spread_pred["away_team"],
                  side, bet_team,
                  spread, spread_pred.get("pred_home_margin"),
                  spread_pred.get(f"{side}_cover_prob"), spread_pred.get(f"{side}_ats_edge"),
                  line, kelly_s, result, profit, clv))


def _record_totals_result(conn, pred, home_score, away_score):
    actual_total = home_score + away_score
    total_line   = pred.get("total_line")
    if total_line is None:
        return

    actual_over = 1 if actual_total > total_line else 0

    conn.execute("""
        UPDATE mlb_totals_predictions SET actual_total = ?
        WHERE game_id=? AND predict_date=?
    """, (actual_total, pred["game_id"], pred["predict_date"]))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_totals_bet_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date  TEXT, game_id TEXT,
            home_team     TEXT, away_team TEXT,
            bet_side      TEXT,
            total_line    REAL, pred_total REAL,
            ou_prob       REAL, edge REAL,
            line          REAL, kelly_stake REAL,
            result        TEXT, profit_units REAL,
            clv           REAL,
            recorded_at   TEXT
        )
    """)

    for side in ["over", "under"]:
        if not pred.get(f"{side}_value"):
            continue
        won    = (side == "over" and actual_over == 1) or \
                 (side == "under" and actual_over == 0)
        result = "WIN" if won else "LOSS"
        price  = pred[f"{side}_price"]
        kelly_s = pred[f"{side}_kelly"]
        profit = kelly_s * ((price/100) if price > 0 else (100/abs(price))) if won else -kelly_s

        icon  = "✅" if won else "❌"
        label = f"O{total_line:.1f}" if side == "over" else f"U{total_line:.1f}"
        print(f"    {icon} TOTALS {result}: {label} | "
              f"Edge: {pred[f'{side}_edge']:+.1%} | P&L: {profit:+.4f}u")

        # CLV = closing vig-free prob minus opening vig-free prob
        closing = conn.execute("""
            SELECT close_fair_prob FROM mlb_closing_odds
            WHERE game_id=? AND market='totals' AND side=?
        """, (pred["game_id"], side)).fetchone()
        open_fair = (pred.get(f"{side}_prob") or 0.5) - (pred.get(f"{side}_edge") or 0)
        clv = float(closing[0]) - open_fair if closing else None

        existing = conn.execute("""
            SELECT id FROM mlb_totals_bet_log
            WHERE game_id=? AND predict_date=? AND bet_side=?
        """, (pred["game_id"], pred["predict_date"], side)).fetchone()

        if existing:
            conn.execute("""
                UPDATE mlb_totals_bet_log SET result=?, profit_units=?, clv=?
                WHERE game_id=? AND predict_date=? AND bet_side=?
            """, (result, profit, clv, pred["game_id"], pred["predict_date"], side))
        else:
            conn.execute("""
                INSERT INTO mlb_totals_bet_log
                (predict_date, game_id, home_team, away_team, bet_side,
                 total_line, pred_total, ou_prob, edge, line, kelly_stake,
                 result, profit_units, clv, recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (pred["predict_date"], pred["game_id"],
                  pred["home_team"], pred["away_team"],
                  side, total_line, pred.get("pred_total"),
                  pred.get(f"{side}_prob"), pred.get(f"{side}_edge"),
                  price, kelly_s, result, profit, clv))


def update_results(game_date: str, conn) -> int:
    scores = fetch_mlb_scores(game_date)
    if scores.empty:
        return 0

    # Load all unresolved MLB predictions
    preds = pd.read_sql("""
        SELECT * FROM mlb_predictions
        WHERE actual_home_win IS NULL
    """, conn)

    if preds.empty:
        print("  No unresolved MLB predictions.")
        return 0

    updated = 0
    for _, pred in preds.iterrows():
        home_team = pred["home_team"]
        away_team = pred["away_team"]

        # Match by team name
        matched = None
        for _, score in scores.iterrows():
            if (match_team(score["home_name"], home_team) and
                    match_team(score["away_name"], away_team)):
                matched = score
                break
            # Also try abbreviation match
            if (score["home_abbr"] in home_team or
                    any(w in home_team for w in score["home_name"].split() if len(w) > 4)):
                if (score["away_abbr"] in away_team or
                        any(w in away_team for w in score["away_name"].split() if len(w) > 4)):
                    matched = score
                    break

        if matched is None:
            continue

        home_score     = int(matched["home_score"])
        away_score     = int(matched["away_score"])
        actual_home_win = 1 if home_score > away_score else 0
        winner = home_team if actual_home_win == 1 else away_team

        print(f"  ✓ {away_team} @ {home_team} → "
              f"{home_score}-{away_score} | {winner} wins")

        # Update predictions table
        conn.execute("""
            UPDATE mlb_predictions SET actual_home_win = ?
            WHERE game_id = ? AND predict_date = ?
        """, (actual_home_win, pred["game_id"], pred["predict_date"]))

        # Also resolve spread prediction if one exists
        try:
            sp = pd.read_sql("""
                SELECT * FROM mlb_spread_predictions
                WHERE game_id=? AND predict_date=? AND actual_home_cover IS NULL
            """, conn, params=(str(pred["game_id"]), pred["predict_date"]))
            if not sp.empty:
                _record_spread_result(conn, sp.iloc[0], home_score, away_score)
        except Exception:
            pass

        # Also resolve totals prediction if one exists
        try:
            tp = pd.read_sql("""
                SELECT * FROM mlb_totals_predictions
                WHERE game_id=? AND predict_date=? AND actual_total IS NULL
            """, conn, params=(str(pred["game_id"]), pred["predict_date"]))
            if not tp.empty:
                _record_totals_result(conn, tp.iloc[0], home_score, away_score)
        except Exception:
            pass

        # Log to bet_log if this was a value bet
        for side in ["home","away"]:
            if not pred.get(f"{side}_value"):
                continue

            model_prob = pred[f"model_{side}_prob"]
            fair_prob  = pred[f"{side}_fair_prob"]
            edge       = pred[f"{side}_edge"]
            line       = pred[f"{side}_price"]
            kelly_s    = pred[f"{side}_kelly"]
            bet_team   = pred["home_team"] if side=="home" else pred["away_team"]

            won    = (side=="home" and actual_home_win==1) or \
                     (side=="away" and actual_home_win==0)
            result = "WIN" if won else "LOSS"

            if won:
                profit = kelly_s * ((line/100) if line > 0 else (100/abs(line)))
            else:
                profit = -kelly_s

            icon = "✅" if won else "❌"
            print(f"    {icon} {result}: {bet_team} | "
                  f"Edge: {edge:+.1%} | P&L: {profit:+.4f} units")

            # Init bet_log table if needed
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mlb_bet_log (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    predict_date TEXT, game_id TEXT,
                    home_team    TEXT, away_team TEXT,
                    bet_side     TEXT, bet_team TEXT,
                    model_prob   REAL, fair_prob REAL,
                    edge         REAL, line REAL,
                    kelly_stake  REAL, result TEXT,
                    profit_units REAL, clv REAL,
                    recorded_at  TEXT
                )
            """)

            # CLV = closing vig-free prob minus opening vig-free market prob
            ml_closing = conn.execute("""
                SELECT close_fair_prob FROM mlb_closing_odds
                WHERE game_id=? AND market='h2h' AND side=?
            """, (pred["game_id"], side)).fetchone()
            ml_clv = float(ml_closing[0]) - fair_prob if ml_closing else None

            existing = conn.execute("""
                SELECT id FROM mlb_bet_log
                WHERE game_id=? AND predict_date=? AND bet_side=?
            """, (pred["game_id"], pred["predict_date"], side)).fetchone()

            if existing:
                conn.execute("""
                    UPDATE mlb_bet_log SET result=?, profit_units=?, clv=?
                    WHERE game_id=? AND predict_date=? AND bet_side=?
                """, (result, profit, ml_clv, pred["game_id"], pred["predict_date"], side))
            else:
                conn.execute("""
                    INSERT INTO mlb_bet_log
                    (predict_date, game_id, home_team, away_team, bet_side, bet_team,
                     model_prob, fair_prob, edge, line, kelly_stake, result,
                     profit_units, clv, recorded_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
                """, (pred["predict_date"], pred["game_id"],
                      pred["home_team"], pred["away_team"],
                      side, bet_team, model_prob, fair_prob,
                      edge, line, kelly_s, result, profit, ml_clv))

        conn.commit()
        updated += 1

    return updated

def print_summary(conn):
    try:
        df = pd.read_sql("""
            SELECT result, profit_units FROM mlb_bet_log
            WHERE result IN ('WIN','LOSS')
        """, conn)
        if df.empty:
            print("  No completed MLB bets yet.")
            return
        tb = len(df)
        tw = (df["result"]=="WIN").sum()
        tu = df["profit_units"].sum()
        print(f"\n── MLB Running record ───────────────────────────────────")
        print(f"  All time : {tw}W - {tb-tw}L ({tw/tb:.1%})")
        print(f"  Units P&L: {tu:+.4f}")
    except Exception:
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None,
                        help="Date to fetch (YYYY-MM-DD). Default: yesterday + today.")
    args = parser.parse_args()

    if args.date:
        dates_to_try = [args.date]
    else:
        today     = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        dates_to_try = [yesterday, today]

    print(f"\n── MLB Results Fetcher ──────────────────────────────────")

    conn = get_conn()
    total = 0
    for d in dates_to_try:
        print(f"\n  Checking {d}...")
        n = update_results(d, conn)
        total += n

    print(f"\n  Total updated: {total} game(s).")
    print_summary(conn)
    conn.close()
