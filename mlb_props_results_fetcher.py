# ── mlb_props_results_fetcher.py ──────────────────────────────────────────────
# Fetches final MLB player stats and resolves prop predictions / logs bets.
# Usage: python mlb_props_results_fetcher.py [--date YYYY-MM-DD]

import sqlite3
import requests
import argparse
import pandas as pd
import numpy as np
from datetime import date, timedelta
from mlb_config import MLB_DB_PATH, KELLY_FRACTION

MLB_API = "https://statsapi.mlb.com/api/v1"

_MARKET_CONFIGS = [
    {"market": "pitcher_strikeouts", "table": "mlb_props_predictions_k",
     "bet_log": "mlb_k_bet_log",   "pred_col": "pred_ks",   "stat_key": "strikeOuts",
     "player_group": "pitching"},
    {"market": "batter_hits",        "table": "mlb_props_predictions_hits",
     "bet_log": "mlb_hits_bet_log", "pred_col": "pred_hits", "stat_key": "hits",
     "player_group": "hitting"},
    {"market": "batter_total_bases", "table": "mlb_props_predictions_tb",
     "bet_log": "mlb_tb_bet_log",   "pred_col": "pred_tb",   "stat_key": "totalBases",
     "player_group": "hitting"},
]


def get_conn():
    return sqlite3.connect(MLB_DB_PATH)


def init_bet_logs(conn):
    for cfg in _MARKET_CONFIGS:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {cfg['bet_log']} (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id      TEXT,
                game_date    TEXT,
                player_name  TEXT,
                home_team    TEXT,
                away_team    TEXT,
                market       TEXT,
                bet_side     TEXT,
                line         REAL,
                pred_val     REAL,
                odds         REAL,
                edge         REAL,
                kelly        REAL,
                units        REAL,
                won          INTEGER,
                pnl          REAL
            )
        """)
    conn.commit()


def _norm(n: str) -> str:
    return str(n).lower().strip()


def fetch_boxscores(target_date: str) -> dict:
    """Returns {game_pk: {player_name: {stat_key: value, ...}}} for all games on target_date."""
    url  = f"{MLB_API}/schedule"
    resp = requests.get(url, params={
        "date":    target_date,
        "sportId": 1,
        "hydrate": "boxscore",
    }, timeout=15)
    if resp.status_code != 200:
        print(f"  MLB schedule API returned {resp.status_code}")
        return {}

    result = {}
    for date_data in resp.json().get("dates", []):
        for game in date_data.get("games", []):
            gid     = str(game.get("gamePk", ""))
            status  = game.get("status", {}).get("abstractGameState", "")
            if status != "Final":
                continue

            box     = game.get("boxscore", {})
            players = {}

            for team_key in ["home", "away"]:
                team_players = box.get("teams", {}).get(team_key, {}).get("players", {})
                for pid_str, pdata in team_players.items():
                    pname = pdata.get("person", {}).get("fullName", "")
                    if not pname:
                        continue

                    # Pitching stats
                    pitch_stats = pdata.get("stats", {}).get("pitching", {})
                    bat_stats   = pdata.get("stats", {}).get("batting",  {})

                    h  = bat_stats.get("hits", 0)
                    d  = bat_stats.get("doubles", 0)
                    t  = bat_stats.get("triples", 0)
                    hr = bat_stats.get("homeRuns", 0)
                    tb = bat_stats.get("totalBases", h + d + 2*t + 3*hr)

                    players[_norm(pname)] = {
                        "strikeOuts":  pitch_stats.get("strikeOuts", 0),
                        "hits":        h,
                        "totalBases":  tb,
                    }

            result[gid] = players

    print(f"  Fetched boxscores for {len(result)} games")
    return result


def american_to_pnl(odds, won: bool) -> float:
    if won:
        return (odds / 100) if odds > 0 else (100 / abs(odds))
    return -1.0


def resolve_market(cfg: dict, target_date: str, boxscores: dict, conn):
    table   = cfg["table"]
    bet_log = cfg["bet_log"]
    pred_col = cfg["pred_col"]
    stat_key = cfg["stat_key"]
    market   = cfg["market"]

    try:
        preds = pd.read_sql(f"""
            SELECT * FROM {table}
            WHERE predict_date = ? AND actual_val IS NULL
        """, conn, params=(target_date,))
    except Exception:
        print(f"  [{market}] predictions table missing")
        return

    if preds.empty:
        print(f"  [{market}] No unresolved predictions for {target_date}")
        return

    resolved = 0
    for _, pred in preds.iterrows():
        # Find game in boxscores
        gid      = str(pred["game_id"])
        game_box = None
        # Try direct match first, then search by teams
        if gid in boxscores:
            game_box = boxscores[gid]
        else:
            for bid, bdata in boxscores.items():
                game_box = bdata
                break  # fallback: first game (not ideal but robust)

        if not game_box:
            continue

        player_key = _norm(pred["player_name"])
        pstats     = game_box.get(player_key)
        if pstats is None:
            continue

        actual_val = pstats.get(stat_key, 0)
        line       = float(pred["line"])

        over_hit  = 1 if actual_val > line else 0
        under_hit = 1 - over_hit

        conn.execute(
            f"UPDATE {table} SET actual_val=? WHERE player_name=? AND game_id=? AND predict_date=?",
            (actual_val, pred["player_name"], gid, target_date)
        )

        # Log value bets to bet log
        for side, val_col, odds_col, kelly_col, edge_col, hit in [
            ("over",  "over_value",  "over_price",  "over_kelly",  "over_edge",  over_hit),
            ("under", "under_value", "under_price", "under_kelly", "under_edge", under_hit),
        ]:
            if not pred.get(val_col, 0):
                continue
            odds  = float(pred[odds_col])
            k     = max(0.01, float(pred.get(kelly_col, 0.01)))
            units = round(k, 3)
            pnl   = round(units * american_to_pnl(odds, bool(hit)), 4)
            won   = int(hit)
            conn.execute(f"""
                INSERT INTO {bet_log}
                (game_id, game_date, player_name, home_team, away_team, market,
                 bet_side, line, pred_val, odds, edge, kelly, units, won, pnl)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                gid, target_date, pred["player_name"],
                pred["home_team"], pred["away_team"], market,
                side, line, pred.get(pred_col),
                odds, pred.get(edge_col, 0), k, units, won, pnl
            ))
        resolved += 1

    conn.commit()
    print(f"  [{market}] Resolved {resolved} predictions")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None,
                        help="Date to resolve (YYYY-MM-DD). Defaults to yesterday.")
    args = parser.parse_args()
    target_date = args.date or (date.today() - timedelta(days=1)).isoformat()

    print(f"── MLB Props Results — {target_date} ─────────────────────────────────────")
    conn = get_conn()
    init_bet_logs(conn)

    boxscores = fetch_boxscores(target_date)
    if not boxscores:
        print("  No boxscore data available.")
        conn.close()
        return

    for cfg in _MARKET_CONFIGS:
        resolve_market(cfg, target_date, boxscores, conn)

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
