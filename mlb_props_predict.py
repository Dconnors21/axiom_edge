# ── mlb_props_predict.py ──────────────────────────────────────────────────────
# Generates MLB player prop value-bet predictions.
# Markets: pitcher_strikeouts, batter_hits, batter_total_bases
# Usage: python mlb_props_predict.py

import sqlite3
import pickle
import json
import numpy as np
import pandas as pd
from datetime import date, datetime, timezone, timedelta
from scipy.stats import norm
from mlb_config import MLB_DB_PATH, KELLY_FRACTION

# Derived at import time — no hardcoded year
_CURRENT_SEASON = str(date.today().year)

PROPS_MIN_EDGE = 0.08   # 8% edge required for props (higher than game-level)
PROPS_BOOKS    = ["draftkings", "fanduel"]

# Value policy from a 4-week realized backtest (2026-05-27 .. 06-22):
#   - Strikeout UNDERS in a moderate edge band won (+15% ROI, 61% hit); overs
#     lost (-22%) and the model's 20%+ "edges" were overconfident (-5.5%).
#   - Batter hits / total-bases value flags were net-negative (~-7% ROI), so
#     they're suppressed until they demonstrate an edge.
# Predictions are still stored for every market (calibration / research); this
# only governs what gets flagged as an actionable value bet.
_VALUE_POLICY = {
    "pitcher_strikeouts": {"over": False, "under": True,  "edge_min": 0.08, "edge_max": 0.20},
    "batter_hits":        {"over": False, "under": False, "edge_min": 0.08, "edge_max": 1.00},
    "batter_total_bases": {"over": False, "under": False, "edge_min": 0.08, "edge_max": 1.00},
}
_DEFAULT_POLICY = {"over": True, "under": True, "edge_min": PROPS_MIN_EDGE, "edge_max": 1.00}

_MARKET_CONFIGS = [
    {
        "market":     "pitcher_strikeouts",
        "model_pkl":  "mlb_k_model.pkl",
        "meta_json":  "mlb_k_model_meta.json",
        "pred_col":   "pred_ks",
        "table":      "mlb_props_predictions_k",
    },
    {
        "market":     "batter_hits",
        "model_pkl":  "mlb_hits_model.pkl",
        "meta_json":  "mlb_hits_model_meta.json",
        "pred_col":   "pred_hits",
        "table":      "mlb_props_predictions_hits",
    },
    {
        "market":     "batter_total_bases",
        "model_pkl":  "mlb_tb_model.pkl",
        "meta_json":  "mlb_tb_model_meta.json",
        "pred_col":   "pred_tb",
        "table":      "mlb_props_predictions_tb",
    },
]

_CREATE_PRED_SQL = """
    CREATE TABLE IF NOT EXISTS {table} (
        player_name   TEXT,
        game_id       TEXT,
        predict_date  TEXT,
        home_team     TEXT,
        away_team     TEXT,
        commence_time TEXT,
        bookmaker     TEXT,
        line          REAL,
        {pred_col}    REAL,
        over_prob     REAL,
        under_prob    REAL,
        over_fair     REAL,
        under_fair    REAL,
        over_edge     REAL,
        under_edge    REAL,
        over_value    INTEGER,
        under_value   INTEGER,
        over_kelly    REAL,
        under_kelly   REAL,
        over_price    REAL,
        under_price   REAL,
        sigma         REAL,
        actual_val    REAL,
        PRIMARY KEY (player_name, game_id, predict_date)
    )
"""


def get_conn():
    return sqlite3.connect(MLB_DB_PATH)


# ── Current opponent quality (real-time, no shift needed for prediction) ─────

def _current_team_k_rates(conn) -> dict:
    """
    Returns {team_upper: rolling_k_rate} from the last 10 team games in
    mlb_batter_game_logs — no shift needed since we're predicting a future game.
    Falls back to 0.22 (league avg) if data is missing.
    """
    try:
        df = pd.read_sql(
            "SELECT team, game_date, strikeouts, at_bats FROM mlb_batter_game_logs",
            conn, parse_dates=["game_date"]
        )
    except Exception:
        return {}
    if df.empty:
        return {}

    tg = df.groupby(["team", "game_date"]).agg(
        k=("strikeouts", "sum"),
        ab=("at_bats", "sum")
    ).reset_index()

    result = {}
    for team, grp in tg.groupby("team"):
        grp = grp.sort_values("game_date").tail(10)
        total_k  = grp["k"].sum()
        total_ab = grp["ab"].sum()
        result[str(team).upper()] = (total_k / total_ab) if total_ab > 0 else 0.22
    return result


def _current_team_starter_era(conn) -> dict:
    """
    Returns {team_upper: rolling_ERA} from the last 5 starts in
    mlb_pitcher_game_logs (IP >= 4 filter for starters).
    Falls back to 4.0 (league avg) if data is missing.
    """
    try:
        df = pd.read_sql(
            "SELECT team, game_date, earned_runs, innings_pitched "
            "FROM mlb_pitcher_game_logs",
            conn, parse_dates=["game_date"]
        )
    except Exception:
        return {}
    if df.empty:
        return {}

    starters = df[df["innings_pitched"] >= 4].copy()
    tg = (starters
          .sort_values("innings_pitched", ascending=False)
          .groupby(["team", "game_date"])[["earned_runs", "innings_pitched"]]
          .first()
          .reset_index())

    result = {}
    for team, grp in tg.groupby("team"):
        grp = grp.sort_values("game_date").tail(5)
        total_er = grp["earned_runs"].sum()
        total_ip = grp["innings_pitched"].sum()
        result[str(team).upper()] = (total_er / total_ip * 9) if total_ip > 0 else 4.0
    return result


def american_to_implied(odds):
    if odds is None or (isinstance(odds, float) and np.isnan(odds)):
        return 0.5
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def kelly(edge, prob, odds, fraction=KELLY_FRACTION):
    if odds > 0: decimal = odds / 100 + 1
    else:        decimal = 100 / abs(odds) + 1
    b = decimal - 1; q = 1 - prob
    k = (b * prob - q) / b
    return max(0.0, k * fraction)


def _norm_name(n: str) -> str:
    return str(n).lower().strip()


def load_todays_props(conn, market: str) -> pd.DataFrame:
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)
    try:
        df = pd.read_sql(
            "SELECT * FROM mlb_prop_odds WHERE market=? ORDER BY pulled_at DESC",
            conn, params=(market,)
        )
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    df["commence_dt"] = pd.to_datetime(df["commence_time"], utc=True, errors="coerce")
    df = df[(df["commence_dt"] >= now) & (df["commence_dt"] <= cutoff)]
    df = df.sort_values("pulled_at", ascending=False)

    best = []
    for (player, gid), grp in df.groupby(["player_name", "game_id"]):
        for book in PROPS_BOOKS:
            row = grp[grp["bookmaker"] == book]
            if not row.empty:
                best.append(row.iloc[0])
                break
    if not best:
        return pd.DataFrame()

    best_df = pd.DataFrame(best)
    best_df["over_implied"]  = best_df["over_price"].apply(american_to_implied)
    best_df["under_implied"] = best_df["under_price"].apply(american_to_implied)
    vig = best_df["over_implied"] + best_df["under_implied"]
    best_df["over_fair"]  = best_df["over_implied"] / vig
    best_df["under_fair"] = best_df["under_implied"] / vig
    return best_df


def build_pitcher_features(props_df, conn, feature_cols, opp_k_rates: dict = None) -> pd.DataFrame:
    logs = pd.read_sql("""
        SELECT * FROM mlb_pitcher_game_logs ORDER BY player_id, game_date ASC
    """, conn, parse_dates=["game_date"])

    if logs.empty:
        return pd.DataFrame()

    player_lookup = {_norm_name(n): grp for n, grp in logs.groupby("player_name")}

    rows = []
    for _, prop in props_df.iterrows():
        pname = prop["player_name"]
        hist  = player_lookup.get(_norm_name(pname))
        if hist is None or len(hist) < 3:
            continue

        hist = hist.sort_values("game_date")
        k3   = hist["strikeouts"].tail(3).mean()
        k5   = hist["strikeouts"].tail(5).mean()
        k10  = hist["strikeouts"].tail(10).mean()
        ip3  = hist["innings_pitched"].tail(3).mean()
        ip5  = hist["innings_pitched"].tail(5).mean()
        k9   = (k5 / ip5 * 9) if ip5 > 0 else 0
        w5   = hist["walks"].tail(5).mean()
        er5  = hist["earned_runs"].tail(5).mean()
        era5 = (er5 / ip5 * 9) if ip5 > 0 else 4.0
        season_k = hist[hist["season"] == _CURRENT_SEASON]["strikeouts"].mean()
        if pd.isna(season_k):
            season_k = k5

        prev_date = hist["game_date"].iloc[-1]
        days_rest = min((pd.Timestamp(date.today()) - prev_date).days, 10)

        # Determine home/away and opponent team before building feat dict
        last_team = hist["team"].iloc[-1]
        is_home   = int(last_team in str(prop.get("home_team", "")))
        opp_team  = (str(prop.get("away_team", "")).upper() if is_home
                     else str(prop.get("home_team", "")).upper())

        feat = {
            "player_name": pname, "game_id": prop["game_id"],
            "home_team": prop["home_team"], "away_team": prop["away_team"],
            "commence_time": prop["commence_time"], "bookmaker": prop["bookmaker"],
            "line": prop["line"], "over_price": prop["over_price"],
            "under_price": prop["under_price"],
            "over_fair": prop["over_fair"], "under_fair": prop["under_fair"],
            "k_last3": k3, "k_last5": k5, "k_last10": k10,
            "ip_last3": ip3, "ip_last5": ip5,
            "k_per9_last5": k9, "walks_last5": w5, "era_last5": era5,
            "is_home": is_home,
            "days_rest": days_rest,
            "opp_k_pct_last10": (opp_k_rates or {}).get(opp_team, 0.22),
            "season_k_avg": float(season_k),
        }
        rows.append(feat)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def build_batter_features(props_df, conn, feature_cols, target_col, opp_era: dict = None) -> pd.DataFrame:
    logs = pd.read_sql("""
        SELECT * FROM mlb_batter_game_logs ORDER BY player_id, game_date ASC
    """, conn, parse_dates=["game_date"])

    if logs.empty:
        return pd.DataFrame()

    player_lookup = {_norm_name(n): grp for n, grp in logs.groupby("player_name")}

    rows = []
    for _, prop in props_df.iterrows():
        pname = prop["player_name"]
        hist  = player_lookup.get(_norm_name(pname))
        if hist is None or len(hist) < 5:
            continue

        hist = hist.sort_values("game_date")
        ab5  = hist["at_bats"].tail(5).replace(0, 1).mean()
        h5   = hist["hits"].tail(5).mean()
        h10  = hist["hits"].tail(10).mean()
        h15  = hist["hits"].tail(15).mean()
        ba10 = hist["hits"].tail(10).sum() / max(hist["at_bats"].tail(10).sum(), 1)
        ba15 = hist["hits"].tail(15).sum() / max(hist["at_bats"].tail(15).sum(), 1)
        tb5  = hist["total_bases"].tail(5).mean()
        tb10 = hist["total_bases"].tail(10).mean()
        tb15 = hist["total_bases"].tail(15).mean()
        hr10 = hist["home_runs"].tail(10).mean()
        xbh10 = (hist["doubles"].tail(10) + hist["triples"].tail(10) + hist["home_runs"].tail(10)).sum()
        xbh_rate10 = xbh10 / max(hist["at_bats"].tail(10).sum(), 1)

        season_h  = hist[hist["season"] == _CURRENT_SEASON]["hits"].mean()
        season_tb = hist[hist["season"] == _CURRENT_SEASON]["total_bases"].mean()
        if pd.isna(season_h):  season_h  = h10
        if pd.isna(season_tb): season_tb = tb10

        prev_date = hist["game_date"].iloc[-1]
        days_rest = min((pd.Timestamp(date.today()) - prev_date).days, 7)

        last_team = hist["team"].iloc[-1]
        is_home   = int(last_team in str(prop.get("home_team", "")))

        feat = {
            "player_name": pname, "game_id": prop["game_id"],
            "home_team": prop["home_team"], "away_team": prop["away_team"],
            "commence_time": prop["commence_time"], "bookmaker": prop["bookmaker"],
            "line": prop["line"], "over_price": prop["over_price"],
            "under_price": prop["under_price"],
            "over_fair": prop["over_fair"], "under_fair": prop["under_fair"],
            "hits_last5": h5, "hits_last10": h10, "hits_last15": h15,
            "ba_last10": ba10, "ba_last15": ba15,
            "ab_last5": ab5,
            "tb_last5": tb5, "tb_last10": tb10, "tb_last15": tb15,
            "hr_last10": hr10,
            "xbh_rate_last10": xbh_rate10,
            "is_home": is_home,
            "days_rest": days_rest,
            "season_hit_avg": float(season_h),
            "season_tb_avg":  float(season_tb),
            "opp_era_last5": (opp_era or {}).get(
                str(prop.get("away_team", "")).upper()
                if is_home else
                str(prop.get("home_team", "")).upper(), 4.0),
        }
        rows.append(feat)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def run_market(cfg: dict, conn, today: str, opp_k_rates: dict = None, opp_era: dict = None):
    market    = cfg["market"]
    table     = cfg["table"]
    pred_col  = cfg["pred_col"]

    # Init predictions table
    conn.execute(_CREATE_PRED_SQL.format(table=table, pred_col=pred_col))
    conn.commit()

    # Load model
    try:
        with open(cfg["model_pkl"], "rb") as f: model = pickle.load(f)
        with open(cfg["meta_json"], "r") as f:  meta  = json.load(f)
    except FileNotFoundError:
        print(f"  [{market}] model not found — skipping. Run mlb_props_train.py first.")
        return 0

    feature_cols = meta["feature_cols"]
    sigma        = meta.get("sigma", 1.0)

    # Load today's odds
    props_df = load_todays_props(conn, market)
    if props_df.empty:
        print(f"  [{market}] No prop odds found.")
        return 0

    # Build features
    if "pitcher" in market:
        feat_df = build_pitcher_features(props_df, conn, feature_cols, opp_k_rates)
    else:
        feat_df = build_batter_features(props_df, conn, feature_cols, pred_col, opp_era)

    if feat_df.empty:
        print(f"  [{market}] No historical data found for today's players.")
        return 0

    fc_avail = [c for c in feature_cols if c in feat_df.columns]
    X        = feat_df[fc_avail].fillna(0).values
    preds    = model.predict(X)

    saved    = 0
    value_ct = 0

    for i, (_, row) in enumerate(feat_df.iterrows()):
        pred_val = float(preds[i])
        line     = float(row["line"])

        diff      = pred_val - line
        prob_over = float(norm.cdf(diff / sigma))
        prob_under = 1.0 - prob_over

        of = float(row["over_fair"])
        uf = float(row["under_fair"])
        edge_over  = prob_over  - of
        edge_under = prob_under - uf
        op = float(row["over_price"])
        up = float(row["under_price"])
        k_over  = kelly(edge_over,  prob_over,  op)
        k_under = kelly(edge_under, prob_under, up)
        pol = _VALUE_POLICY.get(market, _DEFAULT_POLICY)
        val_over  = 1 if pol["over"]  and pol["edge_min"] <= edge_over  <= pol["edge_max"] else 0
        val_under = 1 if pol["under"] and pol["edge_min"] <= edge_under <= pol["edge_max"] else 0

        if val_over or val_under:
            value_ct += 1
            side = "OVER" if val_over else "UNDER"
            edge = max(edge_over, edge_under)
            price = op if val_over else up
            p = int(price)
            fmt_p = f"+{p}" if p > 0 else str(p)
            print(f"  VALUE [{market}]: {row['player_name']} {side} {line} {fmt_p} | pred={pred_val:.2f} | edge={edge:.1%}")

        conn.execute(f"""
            INSERT OR REPLACE INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            row["player_name"], row["game_id"], today,
            row["home_team"], row["away_team"], row["commence_time"],
            row["bookmaker"], line,
            round(pred_val, 3),
            round(prob_over,  4), round(prob_under, 4),
            round(of, 4),  round(uf, 4),
            round(edge_over, 4), round(edge_under, 4),
            val_over, val_under,
            round(k_over,  4), round(k_under, 4),
            op, up, round(sigma, 3),
            None,  # actual_val filled later
        ))
        saved += 1

    conn.commit()
    print(f"  [{market}] {saved} predictions | {value_ct} value bets")
    return value_ct


def main():
    print("── MLB Props Predictions ─────────────────────────────────────────────────")
    conn  = get_conn()
    today = date.today().isoformat()

    print("  Building opponent quality lookups...")
    opp_k_rates = _current_team_k_rates(conn)
    opp_era     = _current_team_starter_era(conn)
    print(f"  Team K-rate entries: {len(opp_k_rates)} | Starter ERA entries: {len(opp_era)}")

    total_value = 0
    for cfg in _MARKET_CONFIGS:
        total_value += run_market(cfg, conn, today, opp_k_rates, opp_era)

    conn.close()
    print(f"\nTotal value bets found: {total_value}")
    print("Done.")


if __name__ == "__main__":
    main()
