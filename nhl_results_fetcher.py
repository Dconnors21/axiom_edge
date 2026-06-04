# ── nhl_results_fetcher.py ────────────────────────────────────────────────────
# Fetches final NHL scores and resolves predictions / updates bet logs.
# Usage: python nhl_results_fetcher.py [--date YYYY-MM-DD]

import sqlite3
import requests
import argparse
import pandas as pd
import numpy as np
from datetime import date, timedelta
from nhl_config import NHL_DB_PATH

NHL_API = "https://api-web.nhle.com/v1"

def get_conn():
    return sqlite3.connect(NHL_DB_PATH)

# ── Bet log tables ────────────────────────────────────────────────────────────

def init_bet_logs(conn):
    # Moneyline bet log
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nhl_bet_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id       TEXT,
            game_date     TEXT,
            home_team     TEXT,
            away_team     TEXT,
            bet_team      TEXT,
            bet_side      TEXT,
            odds          REAL,
            edge          REAL,
            kelly         REAL,
            units         REAL,
            won           INTEGER,
            pnl           REAL
        )
    """)
    # Puck line bet log
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nhl_ats_bet_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id       TEXT,
            game_date     TEXT,
            home_team     TEXT,
            away_team     TEXT,
            bet_team      TEXT,
            bet_side      TEXT,
            spread        REAL,
            odds          REAL,
            edge          REAL,
            kelly         REAL,
            units         REAL,
            won           INTEGER,
            pnl           REAL
        )
    """)
    # Totals bet log
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nhl_totals_bet_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id       TEXT,
            game_date     TEXT,
            home_team     TEXT,
            away_team     TEXT,
            bet_side      TEXT,
            line          REAL,
            pred_total    REAL,
            odds          REAL,
            edge          REAL,
            kelly         REAL,
            units         REAL,
            won           INTEGER,
            pnl           REAL
        )
    """)
    conn.commit()

# ── Fetch scores from NHL API ─────────────────────────────────────────────────

def fetch_scores(target_date: str) -> list:
    url  = f"{NHL_API}/score/{target_date}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"  NHL score API returned {resp.status_code}")
            return []
        data  = resp.json()
        games = data.get("games", [])
        print(f"  Found {len(games)} NHL games for {target_date}")
        return games
    except Exception as e:
        print(f"  Error fetching NHL scores: {e}")
        return []

def american_to_pnl(odds, won: bool) -> float:
    if won:
        if odds > 0: return odds / 100
        return 100 / abs(odds)
    return -1.0

# Predictions are keyed by an Odds-API game_id hash, but the NHL stats API uses
# numeric ids — they never match. So resolve by (date + team pair) instead.
# Normalize both sides' abbreviations to the NHL stats-API canonical form;
# _abbrev fallbacks in the predict scripts produce variants like MON/TAM/WAS.
_ABBR_ALIAS = {
    "MON": "MTL", "TAM": "TBL", "TB": "TBL", "WAS": "WSH", "WIN": "WPG",
    "VEG": "VGK", "LA": "LAK", "LOS": "LAK", "NJ": "NJD", "SJ": "SJS",
    "SAN": "SJS", "CLB": "CBJ", "CLS": "CBJ", "NAS": "NSH", "CGY": "CGY",
    "ANA": "ANA", "ARI": "UTA", "PHX": "UTA", "UTAH": "UTA",
}

def _norm_abbr(a) -> str:
    a = str(a or "").upper().strip()
    return _ABBR_ALIAS.get(a, a)

def _build_score_map(games: list) -> dict:
    """Map (home_abbr, away_abbr) -> game dict for FINAL/OFF games."""
    score_map = {}
    for g in games:
        if g.get("gameState", "") not in ("OFF", "FINAL"):
            continue
        h = g.get("homeTeam", {})
        a = g.get("awayTeam", {})
        h_score = h.get("score", 0)
        a_score = a.get("score", 0)
        key = (_norm_abbr(h.get("abbrev")), _norm_abbr(a.get("abbrev")))
        score_map[key] = {
            "home_score": h_score, "away_score": a_score,
            "home_win": 1 if h_score > a_score else 0,
            "goal_diff": h_score - a_score,
            "total_goals": h_score + a_score,
        }
    return score_map

def _lookup(score_map: dict, pred) -> dict | None:
    return score_map.get((_norm_abbr(pred["home_team"]), _norm_abbr(pred["away_team"])))

# ── Resolve moneyline predictions ─────────────────────────────────────────────

def resolve_ml(target_date: str, games: list, conn):
    preds = pd.read_sql("""
        SELECT * FROM nhl_predictions
        WHERE predict_date = ? AND actual_home_win IS NULL
    """, conn, params=(target_date,))

    if preds.empty:
        print("  No unresolved NHL ML predictions for this date")
        return

    score_map = _build_score_map(games)

    resolved = 0
    for _, pred in preds.iterrows():
        gid    = pred["game_id"]
        result = _lookup(score_map, pred)
        if result is None:
            continue
        home_win  = result["home_win"]
        conn.execute(
            "UPDATE nhl_predictions SET actual_home_win=? WHERE game_id=? AND predict_date=?",
            (home_win, gid, target_date)
        )

        # Log any value bets
        for side, val_col, odds_col, kelly_col, edge_col, abbrev in [
            ("home", "home_value", "home_price", "home_kelly", "home_edge", pred["home_team"]),
            ("away", "away_value", "away_price", "away_kelly", "away_edge", pred["away_team"]),
        ]:
            if not pred.get(val_col, 0):
                continue
            won   = (side == "home" and home_win == 1) or (side == "away" and home_win == 0)
            odds  = pred[odds_col]
            k     = max(0.01, float(pred.get(kelly_col, 0.01)))
            units = round(k, 3)
            pnl   = round(units * american_to_pnl(odds, won), 4)
            conn.execute("""
                INSERT INTO nhl_bet_log
                (game_id, game_date, home_team, away_team, bet_team, bet_side,
                 odds, edge, kelly, units, won, pnl)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (gid, target_date, pred["home_team"], pred["away_team"],
                  abbrev, side, odds, pred.get(edge_col, 0), k, units,
                  int(won), pnl))
        resolved += 1

    conn.commit()
    print(f"  Resolved {resolved} NHL ML predictions")

# ── Resolve puck line predictions ─────────────────────────────────────────────

def resolve_spread(target_date: str, games: list, conn):
    preds = pd.read_sql("""
        SELECT * FROM nhl_spread_predictions
        WHERE predict_date = ? AND actual_home_covered IS NULL
    """, conn, params=(target_date,))

    if preds.empty:
        print("  No unresolved NHL spread predictions")
        return

    score_map = _build_score_map(games)

    resolved = 0
    for _, pred in preds.iterrows():
        gid    = pred["game_id"]
        result = _lookup(score_map, pred)
        if result is None:
            continue
        diff         = result["goal_diff"]
        home_covered = 1 if diff >= 2 else 0  # puck line always -1.5
        conn.execute(
            "UPDATE nhl_spread_predictions SET actual_home_covered=? WHERE game_id=? AND predict_date=?",
            (home_covered, gid, target_date)
        )

        for side, val_col, odds_col, kelly_col, edge_col in [
            ("home", "home_value", "home_price", "home_kelly", "home_edge"),
            ("away", "away_value", "away_price", "away_kelly", "away_edge"),
        ]:
            if not pred.get(val_col, 0):
                continue
            won   = (side == "home" and home_covered == 1) or (side == "away" and home_covered == 0)
            odds  = pred[odds_col]
            k     = max(0.01, float(pred.get(kelly_col, 0.01)))
            units = round(k, 3)
            pnl   = round(units * american_to_pnl(odds, won), 4)
            spread = pred.get("home_point", -1.5) if side == "home" else pred.get("away_point", 1.5)
            conn.execute("""
                INSERT INTO nhl_ats_bet_log
                (game_id, game_date, home_team, away_team, bet_team, bet_side,
                 spread, odds, edge, kelly, units, won, pnl)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (gid, target_date, pred["home_team"], pred["away_team"],
                  pred["home_team"] if side == "home" else pred["away_team"], side,
                  spread, odds, pred.get(edge_col, 0), k, units, int(won), pnl))
        resolved += 1

    conn.commit()
    print(f"  Resolved {resolved} NHL spread predictions")

# ── Resolve totals predictions ────────────────────────────────────────────────

def resolve_totals(target_date: str, games: list, conn):
    preds = pd.read_sql("""
        SELECT * FROM nhl_totals_predictions
        WHERE predict_date = ? AND actual_total IS NULL
    """, conn, params=(target_date,))

    if preds.empty:
        print("  No unresolved NHL totals predictions")
        return

    score_map = _build_score_map(games)

    resolved = 0
    for _, pred in preds.iterrows():
        gid    = pred["game_id"]
        result = _lookup(score_map, pred)
        if result is None:
            continue
        actual_total = result["total_goals"]
        book_line    = pred["book_line"]
        over_hit     = 1 if actual_total > book_line else 0
        conn.execute(
            "UPDATE nhl_totals_predictions SET actual_total=? WHERE game_id=? AND predict_date=?",
            (actual_total, gid, target_date)
        )

        for side, val_col, odds_col, kelly_col, edge_col in [
            ("over",  "over_value",  "over_price",  "over_kelly",  "over_edge"),
            ("under", "under_value", "under_price", "under_kelly", "under_edge"),
        ]:
            if not pred.get(val_col, 0):
                continue
            won   = (side == "over" and over_hit == 1) or (side == "under" and over_hit == 0)
            odds  = pred[odds_col]
            k     = max(0.01, float(pred.get(kelly_col, 0.01)))
            units = round(k, 3)
            pnl   = round(units * american_to_pnl(odds, won), 4)
            conn.execute("""
                INSERT INTO nhl_totals_bet_log
                (game_id, game_date, home_team, away_team, bet_side, line,
                 pred_total, odds, edge, kelly, units, won, pnl)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (gid, target_date, pred["home_team"], pred["away_team"],
                  side, book_line, pred.get("pred_total"), odds,
                  pred.get(edge_col, 0), k, units, int(won), pnl))
        resolved += 1

    conn.commit()
    print(f"  Resolved {resolved} NHL totals predictions")

# ── Also update nhl_games with actual scores ──────────────────────────────────

def update_game_results(target_date: str, games: list, conn):
    for g in games:
        gid   = str(g.get("id", ""))
        state = g.get("gameState", "")
        if state not in ("OFF", "FINAL"):
            continue
        h = g.get("homeTeam", {})
        a = g.get("awayTeam", {})
        h_score = h.get("score", 0)
        a_score = a.get("score", 0)
        h_win   = 1 if h_score > a_score else 0
        conn.execute("""
            UPDATE nhl_games
            SET home_score=?, away_score=?, home_win=?,
                goal_diff=?, total_goals=?
            WHERE game_id=? AND home_score IS NULL
        """, (h_score, a_score, h_win, h_score - a_score, h_score + a_score, gid))
    conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None,
                        help="Date to resolve (YYYY-MM-DD). Defaults to yesterday.")
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    else:
        target_date = (date.today() - timedelta(days=1)).isoformat()

    print(f"── NHL Results Fetcher — {target_date} ────────────────────────────────")
    conn = get_conn()
    init_bet_logs(conn)

    games = fetch_scores(target_date)
    if not games:
        print("  No NHL game data available for this date.")
        conn.close()
        return

    update_game_results(target_date, games, conn)
    resolve_ml(target_date, games, conn)
    resolve_spread(target_date, games, conn)
    resolve_totals(target_date, games, conn)

    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
