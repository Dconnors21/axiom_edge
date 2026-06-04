# props_predict_stl.py
# Generates NBA player steals over/under predictions for today's props lines.
# P(over) = Normal CDF((pred_stl - line) / sigma)
#
# Usage: python props_predict_stl.py

import sqlite3
import json
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from scipy.stats import norm
from config import DB_PATH, KELLY_FRACTION

PROPS_MIN_EDGE     = 0.12
STAR_STL_CUTOFF    = 1.5    # avg steals above which suppress unders (high-activity defenders)
STAR_LINE_BUFFER   = 0.5    # skip unders when line is within 0.5 of season avg
PROPS_MARKET       = "player_steals"
PROPS_BOOKS        = ["draftkings", "fanduel"]

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS props_stl_predictions (
        player_name   TEXT,
        game_id       TEXT,
        predict_date  TEXT,
        home_team     TEXT,
        away_team     TEXT,
        commence_time TEXT,
        bookmaker     TEXT,
        line          REAL,
        pred_stl      REAL,
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
        props_sigma   REAL,
        actual_stl    REAL,
        PRIMARY KEY (player_name, game_id, predict_date)
    )
"""


def get_conn():
    return sqlite3.connect(DB_PATH)


def american_to_implied(odds):
    if odds is None or (isinstance(odds, float) and np.isnan(odds)):
        return 0.5
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def kelly(edge, prob, odds, fraction=KELLY_FRACTION):
    if odds > 0:
        decimal = odds / 100 + 1
    else:
        decimal = 100 / abs(odds) + 1
    b = decimal - 1
    q = 1 - prob
    k = (b * prob - q) / b
    return max(0, k * fraction)


def load_todays_stl_props(conn) -> pd.DataFrame:
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)
    try:
        df = pd.read_sql(
            "SELECT * FROM props_odds WHERE market=? ORDER BY pulled_at DESC",
            conn, params=(PROPS_MARKET,)
        )
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    df["commence_dt"] = pd.to_datetime(df["commence_time"], utc=True)
    df = df[(df["commence_dt"] >= now) & (df["commence_dt"] <= cutoff)]
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values("pulled_at", ascending=False)
    df = df.drop_duplicates(subset=["player_name", "game_id", "bookmaker"])

    best = []
    for (player, game_id), grp in df.groupby(["player_name", "game_id"]):
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
    total = best_df["over_implied"] + best_df["under_implied"]
    best_df["over_fair"]  = best_df["over_implied"] / total
    best_df["under_fair"] = best_df["under_implied"] / total
    return best_df


def build_player_features(props_df, conn, feature_cols) -> pd.DataFrame:
    logs = pd.read_sql("""
        SELECT player_id, player_name, team_abbreviation, game_id, game_date,
               season, matchup, is_home, min_played, stl
        FROM player_game_logs
        WHERE stl IS NOT NULL
        ORDER BY player_id, game_date ASC
    """, conn)

    if logs.empty:
        return pd.DataFrame()

    logs["game_date"] = pd.to_datetime(logs["game_date"])

    def_stats = pd.read_sql("""
        SELECT season, team_name, opp_pts, def_rtg, pace FROM team_season_stats
    """, conn)
    team_abbrev = pd.read_sql(
        "SELECT DISTINCT team_abbreviation, team_name FROM games", conn
    ).drop_duplicates("team_abbreviation")
    abbrev_map = team_abbrev.set_index("team_name")["team_abbreviation"].to_dict()
    def_stats["team_abbrev"] = def_stats["team_name"].map(abbrev_map)
    def_stats = def_stats.dropna(subset=["team_abbrev"])
    def_lookup = def_stats.set_index(["season", "team_abbrev"]).to_dict("index")

    def norm_name(n):
        return str(n).lower().strip()

    player_lookup = {norm_name(n): grp for n, grp in logs.groupby("player_name")}

    rows = []
    for _, prop in props_df.iterrows():
        pname = prop["player_name"]
        hist  = player_lookup.get(norm_name(pname))

        if hist is None or len(hist) < 3:
            continue

        hist = hist.sort_values("game_date")
        last = hist.iloc[-1]
        season = last["season"]

        stl_l3  = hist["stl"].tail(3).mean()
        stl_l5  = hist["stl"].tail(5).mean()
        stl_l10 = hist["stl"].tail(10).mean()
        stl_std = hist["stl"].tail(10).std()
        min_l5  = hist["min_played"].tail(5).mean()
        season_stl = hist[hist["season"] == season]["stl"].mean()

        home_stl = hist[hist["is_home"]==1]["stl"].tail(5).mean()
        away_stl = hist[hist["is_home"]==0]["stl"].tail(5).mean()

        today_ts  = pd.Timestamp(date.today())
        days_rest = min((today_ts - last["game_date"]).days, 7)

        home_team = prop.get("home_team", "")
        away_team = prop.get("away_team", "")
        team_abbr = last.get("team_abbreviation", "")
        opp_name  = away_team if team_abbr and team_abbr in str(home_team) else home_team
        opp_abbr  = abbrev_map.get(opp_name, opp_name.split()[-1][:3].upper())
        opp_info  = def_lookup.get((season, opp_abbr), {})
        opp_def_rtg = opp_info.get("def_rtg",  108.0)
        opp_pace    = opp_info.get("pace",      100.0)
        opp_opp_pts = opp_info.get("opp_pts",   110.0)

        is_home = int(team_abbr in str(home_team)) if team_abbr else 0

        feat = {
            "player_name":   pname,
            "game_id":       prop["game_id"],
            "home_team":     prop["home_team"],
            "away_team":     prop["away_team"],
            "commence_time": prop["commence_time"],
            "bookmaker":     prop["bookmaker"],
            "line":          prop["line"],
            "over_price":    prop["over_price"],
            "under_price":   prop["under_price"],
            "over_fair":     prop["over_fair"],
            "under_fair":    prop["under_fair"],
            "season_stl":    season_stl if not np.isnan(season_stl) else stl_l10,
            "stl_home_l5":   home_stl if not np.isnan(home_stl) else stl_l5,
            "stl_away_l5":   away_stl if not np.isnan(away_stl) else stl_l5,
        }
        for col in feature_cols:
            if col not in feat:
                feat[col] = locals().get(col, np.nan)

        rows.append(feat)

    return pd.DataFrame(rows)


def generate_predictions(features_df, model, feature_cols, sigma) -> pd.DataFrame:
    X = features_df[feature_cols].fillna(0)
    pred_stl = model.predict(X)

    df = features_df.copy()
    df["pred_stl"] = pred_stl

    df["over_prob"]  = df.apply(
        lambda r: float(norm.cdf((r["pred_stl"] - r["line"]) / sigma))
        if pd.notna(r.get("line")) else 0.5, axis=1
    )
    df["under_prob"] = 1.0 - df["over_prob"]

    df["over_edge"]  = df["over_prob"]  - df["over_fair"]
    df["under_edge"] = df["under_prob"] - df["under_fair"]

    df["over_kelly"]  = df.apply(
        lambda r: kelly(r["over_edge"], r["over_prob"], r["over_price"])
        if pd.notna(r.get("over_price")) else 0, axis=1
    )
    df["under_kelly"] = df.apply(
        lambda r: kelly(r["under_edge"], r["under_prob"], r["under_price"])
        if pd.notna(r.get("under_price")) else 0, axis=1
    )

    df["over_value"]  = (df["over_edge"]  > PROPS_MIN_EDGE).astype(int)
    df["under_value"] = (df["under_edge"] > PROPS_MIN_EDGE).astype(int)

    # Defender guard: don't fade a high-activity defender near their season avg
    if "season_stl" in df.columns:
        star_mask = (
            (df["season_stl"] > STAR_STL_CUTOFF) &
            (df["line"] >= df["season_stl"] - STAR_LINE_BUFFER)
        )
        suppressed = star_mask & (df["under_value"] == 1)
        if suppressed.any():
            for name in df.loc[suppressed, "player_name"]:
                print(f"  [guard] Suppressed steals under for {name} — line near season avg")
        df.loc[star_mask, "under_value"] = 0

    df["props_sigma"] = sigma
    return df


def save_predictions(df, conn):
    conn.execute(_CREATE_SQL)
    today = date.today().isoformat()
    conn.execute("DELETE FROM props_stl_predictions WHERE predict_date=?", (today,))
    df["predict_date"] = today
    df["actual_stl"]   = None

    save_cols = [c for c in df.columns if c in [
        "player_name","game_id","predict_date","home_team","away_team",
        "commence_time","bookmaker","line","pred_stl",
        "over_prob","under_prob","over_fair","under_fair",
        "over_edge","under_edge","over_value","under_value",
        "over_kelly","under_kelly","over_price","under_price",
        "props_sigma","actual_stl",
    ]]
    df[save_cols].to_sql("props_stl_predictions", conn,
                         if_exists="append", index=False, chunksize=100)
    conn.commit()
    print(f"  Steals predictions saved -> nba.db: props_stl_predictions")


if __name__ == "__main__":
    print("\n-- Props Predict: Player Steals ------------------------------------")

    for fname in ["props_stl_model.pkl", "props_stl_features.json",
                  "props_stl_model_std.json"]:
        if not Path(fname).exists():
            print(f"  ERROR: {fname} not found. Run python train_props_stl.py first.")
            exit(1)

    with open("props_stl_model.pkl", "rb") as f:
        model = pickle.load(f)
    with open("props_stl_features.json") as f:
        feature_cols = json.load(f)
    with open("props_stl_model_std.json") as f:
        sigma = json.load(f)["rmse"]

    print(f"  Model loaded. sigma={sigma:.2f} stl. Features: {len(feature_cols)}")

    conn = get_conn()

    props_df = load_todays_stl_props(conn)
    if props_df.empty:
        print("  No steals lines found. Run python props_odds.py first.")
        conn.close()
        exit()
    print(f"  Found {len(props_df)} player steals line(s) for today.")

    features_df = build_player_features(props_df, conn, feature_cols)
    if features_df.empty:
        print("  Could not build features — no player history found.")
        conn.close()
        exit()
    print(f"  Built features for {len(features_df)} player(s).")

    results = generate_predictions(features_df, model, feature_cols, sigma)

    value_over  = results[results["over_value"]  == 1]
    value_under = results[results["under_value"] == 1]
    value_count = len(value_over) + len(value_under)

    print(f"\n{'='*60}")
    print(f"  PLAYER STEALS PICKS  (min edge: {PROPS_MIN_EDGE:.0%})")
    print(f"{'='*60}")

    for _, g in results.sort_values("over_edge", ascending=False).head(15).iterrows():
        home = g["home_team"].split()[-1]
        away = g["away_team"].split()[-1]
        line = g["line"]
        print(f"  {g['player_name']} ({away} @ {home})")
        print(f"    Pred: {g['pred_stl']:.1f}  Line: {line}  "
              f"P(over): {g['over_prob']:.1%}  Over edge: {g['over_edge']:+.1%}")
        if g["over_value"]:
            print(f"    >> VALUE: OVER {line} STL")
        elif g["under_value"]:
            print(f"    >> VALUE: UNDER {line} STL")
        print()

    print(f"  Value picks: {value_count}")

    save_predictions(results, conn)
    conn.close()
