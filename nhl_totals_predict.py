# ── nhl_totals_predict.py ─────────────────────────────────────────────────────
# Generates NHL over/under value-bet predictions.
# Usage: python nhl_totals_predict.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from datetime import date, datetime, timezone, timedelta
from nhl_config import NHL_DB_PATH, MIN_EDGE, KELLY_FRACTION, NHL_NAME_TO_ABBREV
from nhl_train_totals import TOTALS_FEATURE_COLS
import market_signal as ms

def get_conn():
    return sqlite3.connect(NHL_DB_PATH)

def _abbrev(name: str) -> str:
    return NHL_NAME_TO_ABBREV.get(name, name[:3].upper())

def american_to_implied(odds):
    if odds is None or (isinstance(odds, float) and np.isnan(odds)):
        return 0.5
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def kelly_totals(edge, prob, odds, fraction=KELLY_FRACTION):
    if odds > 0: decimal = odds / 100 + 1
    else:        decimal = 100 / abs(odds) + 1
    b = decimal - 1; q = 1 - prob
    k = (b * prob - q) / b
    return max(0.0, k * fraction)

def fmt(price):
    try:
        p = int(price)
        return f"+{p}" if p > 0 else str(p)
    except Exception:
        return "N/A"

def init_totals_predictions(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nhl_totals_predictions (
            game_id           TEXT,
            predict_date      TEXT,
            home_team         TEXT,
            away_team         TEXT,
            commence_time     TEXT,
            pred_total        REAL,
            book_line         REAL,
            over_prob         REAL,
            under_prob        REAL,
            over_fair_prob    REAL,
            under_fair_prob   REAL,
            over_edge         REAL,
            under_edge        REAL,
            over_value        INTEGER,
            under_value       INTEGER,
            over_kelly        REAL,
            under_kelly       REAL,
            over_price        REAL,
            under_price       REAL,
            bookmaker         TEXT,
            actual_total      REAL,
            market_flag       TEXT,
            market_move       REAL,
            PRIMARY KEY (game_id, predict_date)
        )
    """)
    for col, decl in [("market_flag", "TEXT"), ("market_move", "REAL")]:
        try:
            conn.execute(f"ALTER TABLE nhl_totals_predictions ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass
    conn.commit()

def load_todays_totals_odds(conn):
    df = pd.read_sql("SELECT * FROM nhl_totals_odds ORDER BY pulled_at DESC", conn)
    if df.empty:
        return pd.DataFrame()
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)
    df["commence_dt"] = pd.to_datetime(df["commence_time"], utc=True, errors="coerce")
    df = df[df["commence_dt"] >= now]
    df = df[df["commence_dt"] <= cutoff]
    pref = {"pinnacle": 0, "draftkings": 1, "fanduel": 2}
    df["pref"] = df["bookmaker"].map(pref).fillna(99)
    df = df.sort_values("pref").groupby("game_id").first().reset_index()
    return df

def build_features(home: str, away: str, conn, feature_cols: list) -> pd.DataFrame:
    query = """
        SELECT * FROM nhl_games_featured
        WHERE (home_team = ? OR away_team = ?)
        ORDER BY game_date DESC LIMIT 20
    """
    home_recent = pd.read_sql(query, conn, params=(home, home))
    away_recent = pd.read_sql(query, conn, params=(away, away))
    if home_recent.empty or away_recent.empty:
        return pd.DataFrame()
    row = {}
    if not home_recent.empty:
        for col in feature_cols:
            if col in home_recent.columns:
                row[col] = home_recent.iloc[0][col]
    if not away_recent.empty:
        src = away_recent[away_recent["away_team"] == away]
        if not src.empty:
            for col in feature_cols:
                if col.startswith("away_") and col in src.columns:
                    row[col] = src.iloc[0][col]
    row["home_advantage"] = 1.0
    return pd.DataFrame([row])

def main():
    print("── NHL Totals Predictions ────────────────────────────────────────────────")
    conn = get_conn()
    init_totals_predictions(conn)

    try:
        with open("nhl_totals_model.pkl",       "rb") as f: model = pickle.load(f)
        with open("nhl_totals_model_meta.json", "r") as f: meta  = json.load(f)
        feature_cols = meta["feature_cols"]
        skill        = float(meta.get("skill", 1.0))
    except FileNotFoundError:
        print("  nhl_totals_model.pkl not found. Run nhl_train_totals.py first.")
        conn.close()
        return

    if skill <= 0.0:
        print("  NOTE: skill=0 (model has no out-of-sample edge) -> predictions "
              "shrink to the market line, no value bets will be flagged.")

    odds_df = load_todays_totals_odds(conn)
    if odds_df.empty:
        print("  No NHL totals odds found.")
        conn.close()
        return

    today    = date.today().isoformat()
    saved    = 0
    value_ct = 0

    try:
        sigs = ms.compute_signals(
            conn, "nhl_totals_odds", "total",
            point_col="total_line", market_filter=None)
    except Exception as e:
        print(f"  Market signals skipped: {e}")
        sigs = {}

    for _, row in odds_df.iterrows():
        home      = _abbrev(row["home_team"])
        away      = _abbrev(row["away_team"])
        gid       = row["game_id"]
        ct        = row["commence_time"]
        book_line = row.get("total_line")
        o_price   = row.get("over_price")
        u_price   = row.get("under_price")

        if pd.isna(book_line) or pd.isna(o_price) or pd.isna(u_price):
            continue

        feat_df = build_features(home, away, conn, feature_cols)
        if feat_df.empty:
            feat_df = pd.DataFrame([{c: 0.0 for c in feature_cols}])
        feat_df = feat_df.reindex(columns=feature_cols, fill_value=0.0).fillna(0.0)

        try:
            pred_total = float(model.predict(feat_df.values)[0])
        except Exception as e:
            print(f"  Error {home} vs {away}: {e}")
            continue

        # Shrink prediction toward the market line by the model's skill factor.
        # skill=0 (R2<=0) => pred collapses to book_line => ~0 edge => no bets.
        pred_total = book_line + skill * (pred_total - book_line)

        # Convert predicted total to over/under probability via Normal CDF
        diff       = pred_total - book_line
        sigma      = meta.get("rmse", 1.4)   # data-driven from training — not hardcoded
        from scipy.stats import norm
        prob_over  = float(norm.cdf(diff / sigma))
        prob_under = 1.0 - prob_over

        impl_over  = american_to_implied(o_price)
        impl_under = american_to_implied(u_price)
        vig        = impl_over + impl_under
        fair_over  = impl_over  / vig
        fair_under = impl_under / vig
        edge_over  = prob_over  - fair_over
        edge_under = prob_under - fair_under
        k_over     = kelly_totals(edge_over,  prob_over,  o_price)
        k_under    = kelly_totals(edge_under, prob_under, u_price)
        val_over   = 1 if edge_over  >= MIN_EDGE else 0
        val_under  = 1 if edge_under >= MIN_EDGE else 0

        # Market signal soft gate (side A = over).
        sig = sigs.get(str(gid))
        if val_over:
            pick_a = True
        elif val_under:
            pick_a = False
        else:
            pick_a = edge_over >= edge_under
        mult, mkt_flag, mkt_move = ms.gate_pick(sig, pick_a)
        if mult < 1.0:
            if pick_a: k_over  *= mult
            else:      k_under *= mult
        if mkt_flag:
            print(f"  Market: {away} @ {home} {mkt_flag} ({ms.describe(sig)})")

        if val_over or val_under:
            value_ct += 1
            side = "OVER" if val_over else "UNDER"
            edge = max(edge_over, edge_under)
            print(f"  VALUE: {away} @ {home} — {side} {book_line} | pred={pred_total:.2f} | edge={edge:.1%}")

        conn.execute("""
            INSERT OR REPLACE INTO nhl_totals_predictions VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, (
            gid, today, home, away, ct,
            round(pred_total, 3), book_line,
            round(prob_over,  4), round(prob_under, 4),
            round(fair_over,  4), round(fair_under, 4),
            round(edge_over,  4), round(edge_under, 4),
            val_over, val_under,
            round(k_over,  4), round(k_under, 4),
            o_price, u_price, row["bookmaker"],
            None,
            mkt_flag, round(float(mkt_move), 4),
        ))
        saved += 1

    conn.commit()
    conn.close()
    print(f"\n  {saved} totals predictions saved | {value_ct} value bets found")
    print("Done.")

if __name__ == "__main__":
    main()
