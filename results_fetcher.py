# ── results_fetcher.py ────────────────────────────────────────────────────────
# Fetches final NBA scores using ScoreboardV3 and updates prediction results.
#
# Usage:
#   python results_fetcher.py                    (yesterday + today)
#   python results_fetcher.py --date 2026-05-16  (specific date)

import sqlite3
import argparse
import time
import pandas as pd
from datetime import date, datetime, timedelta
from nba_api.stats.endpoints import scoreboardv3
from config import DB_PATH

def get_conn():
    return sqlite3.connect(DB_PATH)

def fetch_scores_for_date(game_date: str):
    print(f"  Fetching scores for {game_date}...")
    time.sleep(0.6)
    try:
        dt       = datetime.strptime(game_date, "%Y-%m-%d")
        api_date = dt.strftime("%m/%d/%Y")

        board       = scoreboardv3.ScoreboardV3(game_date=api_date, league_id="00")
        game_header = board.game_header.get_data_frame()
        line_score  = board.line_score.get_data_frame()

        if game_header.empty:
            print(f"  No games found for {game_date}.")
            return pd.DataFrame(), pd.DataFrame()

        # Normalize to lowercase
        game_header.columns = [c.lower() for c in game_header.columns]
        line_score.columns  = [c.lower() for c in line_score.columns]

        # Filter to final games only (gameStatus == 3)
        if "gamestatus" in game_header.columns:
            final = game_header[game_header["gamestatus"] == 3]
        elif "gamestatustext" in game_header.columns:
            final = game_header[
                game_header["gamestatustext"].str.strip().str.lower() == "final"
            ]
        else:
            final = game_header

        if final.empty:
            print(f"  No final games yet for {game_date}.")
            return pd.DataFrame(), pd.DataFrame()

        final_ids  = final["gameid"].astype(str).tolist()
        line_score = line_score[line_score["gameid"].astype(str).isin(final_ids)]
        print(f"  Found {len(final)} final game(s).")
        return line_score, game_header

    except Exception as e:
        print(f"  Failed to fetch scores: {e}")
        return pd.DataFrame(), pd.DataFrame()

def match_team(nba_name: str, pred_name: str) -> bool:
    words = [w for w in str(nba_name).split() if len(w) > 3]
    return any(w.lower() in str(pred_name).lower() for w in words)

def _record_spread_result(conn, pred, home_pts, away_pts):
    """Resolve spread_predictions and log to ats_bet_log."""
    actual_margin   = home_pts - away_pts
    home_point      = pred.get("home_point")
    away_point      = pred.get("away_point")
    if home_point is None:
        return

    # Home covers if actual margin exceeds the line they were given
    # e.g. home_point=-7.5 means home must win by 8+, so margin > 7.5
    actual_home_cover = 1 if (actual_margin + home_point) > 0 else 0
    winner_side = "home" if actual_home_cover == 1 else "away"

    conn.execute("""
        UPDATE spread_predictions SET actual_home_cover = ?
        WHERE game_id = ? AND predict_date = ?
    """, (actual_home_cover, pred["game_id"], pred["predict_date"]))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ats_bet_log (
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
        if not pred.get(f"{side}_ats_value"):
            continue
        bet_team  = pred["home_team"] if side == "home" else pred["away_team"]
        won       = (side == "home" and actual_home_cover == 1) or \
                    (side == "away" and actual_home_cover == 0)
        result    = "WIN" if won else "LOSS"
        line      = pred[f"{side}_price"]
        kelly_s   = pred[f"{side}_ats_kelly"]
        spread    = pred.get(f"{side}_point")
        profit    = kelly_s * ((line/100) if line > 0 else (100/abs(line))) if won else -kelly_s

        icon = "✅" if won else "❌"
        print(f"    {icon} ATS {result}: {bet_team} {f'{spread:+.1f}' if spread else ''} | "
              f"Edge: {pred[f'{side}_ats_edge']:+.1%} | P&L: {profit:+.4f}u")

        # CLV = closing vig-free prob minus opening vig-free prob
        closing = conn.execute("""
            SELECT close_fair_prob FROM closing_odds
            WHERE game_id=? AND market='spreads' AND side=?
        """, (pred["game_id"], side)).fetchone()
        open_fair = (pred.get(f"{side}_cover_prob") or 0.5) - (pred.get(f"{side}_ats_edge") or 0)
        clv = float(closing[0]) - open_fair if closing else None

        existing = conn.execute("""
            SELECT id FROM ats_bet_log
            WHERE game_id=? AND predict_date=? AND bet_side=?
        """, (pred["game_id"], pred["predict_date"], side)).fetchone()

        if existing:
            conn.execute("""
                UPDATE ats_bet_log SET result=?, profit_units=?, clv=?
                WHERE game_id=? AND predict_date=? AND bet_side=?
            """, (result, profit, clv, pred["game_id"], pred["predict_date"], side))
        else:
            conn.execute("""
                INSERT INTO ats_bet_log
                (predict_date, game_id, home_team, away_team, bet_side, bet_team,
                 spread, pred_margin, cover_prob, edge, line, kelly_stake,
                 result, profit_units, clv, recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (pred["predict_date"], pred["game_id"],
                  pred["home_team"], pred["away_team"],
                  side, bet_team,
                  spread, pred.get("pred_home_margin"),
                  pred.get(f"{side}_cover_prob"), pred.get(f"{side}_ats_edge"),
                  line, kelly_s, result, profit, clv))


def _record_totals_result(conn, pred, home_pts, away_pts):
    """Resolve totals_predictions and log to totals_bet_log."""
    actual_total = home_pts + away_pts
    total_line   = pred.get("total_line")
    if total_line is None:
        return

    actual_over = 1 if actual_total > total_line else 0

    conn.execute("""
        UPDATE totals_predictions SET actual_total = ?
        WHERE game_id = ? AND predict_date = ?
    """, (actual_total, pred["game_id"], pred["predict_date"]))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS totals_bet_log (
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
        kelly  = pred[f"{side}_kelly"]
        profit = kelly * ((price/100) if price > 0 else (100/abs(price))) if won else -kelly

        icon = "✅" if won else "❌"
        label = f"O{total_line:.1f}" if side == "over" else f"U{total_line:.1f}"
        print(f"    {icon} TOTALS {result}: {label} | "
              f"Edge: {pred[f'{side}_edge']:+.1%} | P&L: {profit:+.4f}u")

        # CLV = closing vig-free prob minus opening vig-free prob
        closing = conn.execute("""
            SELECT close_fair_prob FROM closing_odds
            WHERE game_id=? AND market='totals' AND side=?
        """, (pred["game_id"], side)).fetchone()
        open_fair = (pred.get(f"{side}_prob") or 0.5) - (pred.get(f"{side}_edge") or 0)
        clv = float(closing[0]) - open_fair if closing else None

        existing = conn.execute("""
            SELECT id FROM totals_bet_log
            WHERE game_id=? AND predict_date=? AND bet_side=?
        """, (pred["game_id"], pred["predict_date"], side)).fetchone()

        if existing:
            conn.execute("""
                UPDATE totals_bet_log SET result=?, profit_units=?, clv=?
                WHERE game_id=? AND predict_date=? AND bet_side=?
            """, (result, profit, clv, pred["game_id"], pred["predict_date"], side))
        else:
            conn.execute("""
                INSERT INTO totals_bet_log
                (predict_date, game_id, home_team, away_team, bet_side,
                 total_line, pred_total, ou_prob, edge, line, kelly_stake,
                 result, profit_units, clv, recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (pred["predict_date"], pred["game_id"],
                  pred["home_team"], pred["away_team"],
                  side, total_line, pred.get("pred_total"),
                  pred.get(f"{side}_prob"), pred.get(f"{side}_edge"),
                  price, kelly, result, profit, clv))


def _record_result(conn, pred, actual_home_win, home_pts, away_pts):
    home_team = pred["home_team"]
    away_team = pred["away_team"]
    winner    = home_team if actual_home_win == 1 else away_team
    print(f"  ✓ {away_team} @ {home_team} → "
          f"{home_pts:.0f}-{away_pts:.0f} | {winner} wins")

    conn.execute("""
        UPDATE predictions SET actual_home_win = ?
        WHERE game_id = ? AND predict_date = ?
    """, (actual_home_win, pred["game_id"], pred["predict_date"]))

    # Resolve matching spread prediction
    try:
        spread_pred = pd.read_sql("""
            SELECT * FROM spread_predictions
            WHERE game_id=? AND predict_date=? AND actual_home_cover IS NULL
        """, conn, params=(str(pred["game_id"]), pred["predict_date"]))
        if not spread_pred.empty:
            _record_spread_result(conn, spread_pred.iloc[0], home_pts, away_pts)
    except Exception:
        pass

    # Resolve matching totals prediction
    try:
        totals_pred = pd.read_sql("""
            SELECT * FROM totals_predictions
            WHERE game_id=? AND predict_date=? AND actual_total IS NULL
        """, conn, params=(str(pred["game_id"]), pred["predict_date"]))
        if not totals_pred.empty:
            _record_totals_result(conn, totals_pred.iloc[0], home_pts, away_pts)
    except Exception:
        pass

    for side in ["home", "away"]:
        if not pred.get(f"{side}_value"):
            continue

        model_prob = pred[f"model_{side}_prob"]
        fair_prob  = pred[f"{side}_fair_prob"]
        edge       = pred[f"{side}_edge"]
        line       = pred[f"{side}_price"]
        kelly      = pred[f"{side}_kelly"]
        bet_team   = (pred["home_team"] if side == "home" else pred["away_team"])

        won    = (side=="home" and actual_home_win==1) or \
                 (side=="away" and actual_home_win==0)
        result = "WIN" if won else "LOSS"

        if won:
            profit = kelly * ((line/100) if line > 0 else (100/abs(line)))
        else:
            profit = -kelly

        icon = "✅" if won else "❌"
        print(f"    {icon} {result}: {bet_team} | "
              f"Edge: {edge:+.1%} | P&L: {profit:+.4f} units")

        # CLV = closing vig-free prob minus opening vig-free market prob
        ml_closing = conn.execute("""
            SELECT close_fair_prob FROM closing_odds
            WHERE game_id=? AND market='h2h' AND side=?
        """, (pred["game_id"], side)).fetchone()
        ml_clv = float(ml_closing[0]) - fair_prob if ml_closing else None

        existing = conn.execute("""
            SELECT id FROM bet_log
            WHERE game_id = ? AND predict_date = ? AND bet_side = ?
        """, (pred["game_id"], pred["predict_date"], side)).fetchone()

        if existing:
            conn.execute("""
                UPDATE bet_log SET result = ?, profit_units = ?, clv = ?
                WHERE game_id = ? AND predict_date = ? AND bet_side = ?
            """, (result, profit, ml_clv, pred["game_id"], pred["predict_date"], side))
        else:
            conn.execute("""
                INSERT INTO bet_log
                (predict_date, game_id, home_team, away_team, bet_side, bet_team,
                 model_prob, fair_prob, edge, line, kelly_stake, result,
                 profit_units, clv, recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (pred["predict_date"], pred["game_id"],
                  pred["home_team"], pred["away_team"],
                  side, bet_team, model_prob, fair_prob,
                  edge, line, kelly, result, profit, ml_clv))
    conn.commit()

def update_results(game_date: str, conn) -> int:
    line_score, game_header = fetch_scores_for_date(game_date)
    if line_score.empty:
        return 0

    # Load all unresolved predictions
    preds = pd.read_sql("""
        SELECT * FROM predictions
        WHERE actual_home_win IS NULL
    """, conn)

    if preds.empty:
        print("  No unresolved predictions.")
        return 0

    updated = 0
    for _, pred in preds.iterrows():
        home_team   = pred["home_team"]
        away_team   = pred["away_team"]
        game_id_str = str(pred["game_id"])

        # Try matching by game_id first
        game_rows = line_score[
            line_score["gameid"].astype(str) == game_id_str
        ]

        # Fallback: match by team name
        if game_rows.empty:
            for gid in line_score["gameid"].unique():
                g = line_score[line_score["gameid"] == gid]
                for col in ["teamname","teamcity","teamtricode"]:
                    if col in g.columns:
                        teams = g[col].tolist()
                        if any(match_team(t, home_team) for t in teams):
                            game_rows = g
                            break
                if not game_rows.empty:
                    break

        if game_rows.empty:
            print(f"  Could not match score for {away_team} @ {home_team}")
            continue

        try:
            score_col = "score"
            if score_col not in game_rows.columns:
                print(f"  No score column. Columns: {game_rows.columns.tolist()}")
                continue

            # Try matching home/away rows by team name
            home_row = game_rows[game_rows.apply(
                lambda r: any(match_team(str(r.get(c,"")), home_team)
                              for c in ["teamname","teamcity","teamtricode"]), axis=1
            )]
            away_row = game_rows[game_rows.apply(
                lambda r: any(match_team(str(r.get(c,"")), away_team)
                              for c in ["teamname","teamcity","teamtricode"]), axis=1
            )]

            if home_row.empty or away_row.empty:
                # Fallback: use gamecode to extract tricodes
                gh_row = game_header[
                    game_header["gameid"].astype(str) == game_id_str
                ] if not game_header.empty else pd.DataFrame()

                if not gh_row.empty and "gamecode" in gh_row.columns:
                    gc = str(gh_row["gamecode"].iloc[0])
                    if "/" in gc:
                        teams_code = gc.split("/")[1]
                        away_tri   = teams_code[:3]
                        home_tri   = teams_code[3:]
                        home_score_row = game_rows[game_rows["teamtricode"] == home_tri]
                        away_score_row = game_rows[game_rows["teamtricode"] == away_tri]
                        if not home_score_row.empty and not away_score_row.empty:
                            home_pts = float(home_score_row["score"].iloc[0] or 0)
                            away_pts = float(away_score_row["score"].iloc[0] or 0)

                            # Skip if game hasn't been played
                            if home_pts == 0 and away_pts == 0:
                                print(f"  Skipping {away_team} @ {home_team} "
                                      f"— score is 0-0, game not finished")
                                continue

                            actual_home_win = 1 if home_pts > away_pts else 0
                            _record_result(conn, pred, actual_home_win,
                                           home_pts, away_pts)
                            updated += 1
                continue

            home_pts = float(home_row["score"].iloc[0] or 0)
            away_pts = float(away_row["score"].iloc[0] or 0)

            # Skip if game hasn't been played
            if home_pts == 0 and away_pts == 0:
                print(f"  Skipping {away_team} @ {home_team} "
                      f"— score is 0-0, game not finished")
                continue

            actual_home_win = 1 if home_pts > away_pts else 0
            _record_result(conn, pred, actual_home_win, home_pts, away_pts)
            updated += 1

        except Exception as e:
            print(f"  Error processing {away_team} @ {home_team}: {e}")
            continue

    return updated

def print_daily_summary(conn):
    all_bets = pd.read_sql("""
        SELECT result, profit_units FROM bet_log
        WHERE result IN ('WIN','LOSS')
    """, conn)

    if not all_bets.empty:
        tb = len(all_bets)
        tw = (all_bets["result"]=="WIN").sum()
        tu = all_bets["profit_units"].sum()
        print(f"\n── Running record ───────────────────────────────────────")
        print(f"  All time : {tw}W - {tb-tw}L ({tw/tb:.1%})")
        print(f"  Units P&L: {tu:+.4f}")
    else:
        print("  No completed bets recorded yet.")

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

    print(f"\n── NBA Results Fetcher (ScoreboardV3) ───────────────────")

    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bet_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date TEXT, game_id TEXT,
            home_team TEXT, away_team TEXT,
            bet_side TEXT, bet_team TEXT,
            model_prob REAL, fair_prob REAL,
            edge REAL, line REAL, kelly_stake REAL,
            result TEXT, profit_units REAL,
            clv REAL, notes TEXT, recorded_at TEXT
        )
    """)
    conn.commit()

    total_updated = 0
    for d in dates_to_try:
        print(f"\n  Checking {d}...")
        n = update_results(d, conn)
        total_updated += n

    print(f"\n  Total updated: {total_updated} game(s).")
    print_daily_summary(conn)
    conn.close()