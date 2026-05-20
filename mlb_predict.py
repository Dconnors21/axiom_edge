# ── mlb_predict.py ────────────────────────────────────────────────────────────
# Generates MLB value bet predictions using tonight's actual starters.
# Usage: python mlb_predict.py

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from datetime import date, datetime, timezone, timedelta
from mlb_config import MLB_DB_PATH, MIN_EDGE, KELLY_FRACTION

MLB_NAME_TO_ABBREV = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",         "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN",      "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",     "Detroit Tigers": "DET",
    "Houston Astros": "HOU",       "Kansas City Royals": "KCR",
    "Los Angeles Angels": "LAA",   "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",        "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",      "New York Mets": "NYM",
    "New York Yankees": "NYY",     "Athletics": "OAK",
    "Oakland Athletics": "OAK",    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",   "San Diego Padres": "SDP",
    "Seattle Mariners": "SEA",     "San Francisco Giants": "SFG",
    "St. Louis Cardinals": "STL",  "Tampa Bay Rays": "TBR",
    "Texas Rangers": "TEX",        "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSN",
}

def _abbrev(name: str) -> str:
    return MLB_NAME_TO_ABBREV.get(name, name)

def get_conn():
    return sqlite3.connect(MLB_DB_PATH)

def american_to_implied(odds):
    if odds is None or (isinstance(odds, float) and np.isnan(odds)):
        return 0.5
    if odds > 0: return 100/(odds+100)
    return abs(odds)/(abs(odds)+100)

def kelly(edge, prob, odds, fraction=KELLY_FRACTION):
    if odds > 0: decimal = odds/100+1
    else: decimal = 100/abs(odds)+1
    b = decimal-1; q = 1-prob
    k = (b*prob-q)/b
    return max(0, k*fraction)

def fmt(price):
    try:
        p = int(price)
        return f"+{p}" if p > 0 else str(p)
    except Exception:
        return "N/A"

def init_predictions(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_predictions (
            game_id          TEXT,
            predict_date     TEXT,
            home_team        TEXT,
            away_team        TEXT,
            commence_time    TEXT,
            home_pitcher     TEXT,
            away_pitcher     TEXT,
            home_era         REAL,
            away_era         REAL,
            model_home_prob  REAL,
            model_away_prob  REAL,
            home_fair_prob   REAL,
            away_fair_prob   REAL,
            home_edge        REAL,
            away_edge        REAL,
            home_value       INTEGER,
            away_value       INTEGER,
            home_kelly       REAL,
            away_kelly       REAL,
            home_price       REAL,
            away_price       REAL,
            bookmaker        TEXT,
            actual_home_win  INTEGER,
            PRIMARY KEY (game_id, predict_date)
        )
    """)
    conn.commit()

def load_todays_odds(conn):
    """Load only games starting within the next 24 hours."""
    df = pd.read_sql("SELECT * FROM mlb_odds ORDER BY pulled_at DESC", conn)
    if df.empty:
        return pd.DataFrame()

    now     = datetime.now(timezone.utc)
    cutoff  = now + timedelta(hours=24)
    df["commence_dt"] = pd.to_datetime(df["commence_time"], utc=True)
    df = df[df["commence_dt"] >= now]
    df = df[df["commence_dt"] <= cutoff]

    if df.empty:
        return pd.DataFrame()

    # Best line per game
    df = df.sort_values("pulled_at", ascending=False).drop_duplicates("game_id")
    print(f"  Found {len(df)} games tonight.")
    return df

def build_features(odds_df, starters_df, conn, feature_cols):
    # Most recent home stats per team
    home_stats = pd.read_sql("""
        SELECT * FROM mlb_games_featured g
        WHERE game_date = (
            SELECT MAX(game_date) FROM mlb_games_featured g2
            WHERE g2.home_team = g.home_team
        )
    """, conn)
    home_stats = home_stats.drop_duplicates(subset=["home_team"])
    home_lookup = home_stats.set_index("home_team").to_dict("index")

    # Most recent away stats per team
    away_stats = pd.read_sql("""
        SELECT * FROM mlb_games_featured g
        WHERE game_date = (
            SELECT MAX(game_date) FROM mlb_games_featured g2
            WHERE g2.away_team = g.away_team
        )
    """, conn)
    away_stats = away_stats.drop_duplicates(subset=["away_team"])
    away_lookup = away_stats.set_index("away_team").to_dict("index")

    # Merge starters
    if not starters_df.empty:
        odds_df = odds_df.merge(
            starters_df[["home_team","away_team","home_pitcher","away_pitcher",
                          "home_era","away_era","home_whip","away_whip"]],
            on=["home_team","away_team"], how="left"
        )

    # Fill missing starter data
    for col, default in [("home_era",4.20),("away_era",4.20),
                          ("home_whip",1.30),("away_whip",1.30),
                          ("home_pitcher","TBD"),("away_pitcher","TBD")]:
        if col not in odds_df.columns:
            odds_df[col] = default
        else:
            odds_df[col] = odds_df[col].fillna(default)

    park_factors = {
        "COL":1.18,"BOS":1.08,"CIN":1.07,"TEX":1.06,"PHI":1.05,
        "NYY":1.04,"BAL":1.03,"ATL":1.02,"CHC":1.01,"LAD":0.99,
        "HOU":0.98,"TBR":0.98,"NYM":0.97,"SFG":0.97,"SEA":0.96,
        "MIA":0.96,"SDP":0.96,"PIT":0.96,"DET":0.96,"CHW":0.95,
        "LAA":0.95,"CLE":0.95,"KCR":0.94,"TOR":0.94,"WSN":0.94,"ARI":0.97,
    }

    rows = []
    for _, game in odds_df.iterrows():
        home = game["home_team"]; away = game["away_team"]
        hs   = home_lookup.get(_abbrev(home), {})
        as_  = away_lookup.get(_abbrev(away), {})
        home_era = float(game.get("home_era") or 4.20)
        away_era = float(game.get("away_era") or 4.20)

        row = {
            "game_id":       game["game_id"],
            "home_team":     home,
            "away_team":     away,
            "commence_time": game["commence_time"],
            "home_price":    game.get("home_price"),
            "away_price":    game.get("away_price"),
            "bookmaker":     game.get("bookmaker",""),
            "home_pitcher":  game.get("home_pitcher","TBD"),
            "away_pitcher":  game.get("away_pitcher","TBD"),
            "home_era":      home_era,
            "away_era":      away_era,
        }

        # Abbreviation for park factor
        home_abbr = home.split()[-1][:3].upper()

        for col in feature_cols:
            if col == "home_advantage":
                row[col] = 1.0
            elif col == "park_factor":
                row[col] = park_factors.get(home_abbr, 1.0)
            elif col == "home_sp_era_season":
                row[col] = home_era
            elif col == "away_sp_era_season":
                row[col] = away_era
            elif col == "home_sp_whip_season":
                row[col] = float(game.get("home_whip") or 1.30)
            elif col == "away_sp_whip_season":
                row[col] = float(game.get("away_whip") or 1.30)
            elif col == "sp_era_diff":
                row[col] = away_era - home_era
            elif col.startswith("home_"):
                row[col] = hs.get(col, np.nan)
            elif col.startswith("away_"):
                row[col] = as_.get(col, np.nan)
            elif "diff" in col:
                h_col = f"home_{col.replace('_diff','')}"
                a_col = f"away_{col.replace('_diff','')}"
                hv = hs.get(h_col, np.nan)
                av = as_.get(a_col, np.nan)
                row[col] = hv-av if not (np.isnan(float(hv if hv is not None else np.nan)) or
                                          np.isnan(float(av if av is not None else np.nan))) else 0.0
            else:
                row[col] = np.nan

        rows.append(row)

    return pd.DataFrame(rows)

def generate_predictions(features_df, model, feature_cols, odds_df):
    X     = features_df[feature_cols].fillna(0)
    probs = model.predict_proba(X)

    features_df = features_df.copy()
    features_df["model_home_prob"] = probs[:,1]
    features_df["model_away_prob"] = probs[:,0]

    best_odds = odds_df.drop_duplicates("game_id")[
        ["game_id","home_price","away_price","bookmaker"]]

    results = features_df.merge(best_odds, on="game_id", how="left",
                                suffixes=("","_odds"))

    results["home_implied"] = results["home_price"].apply(american_to_implied)
    results["away_implied"] = results["away_price"].apply(american_to_implied)
    vig = results["home_implied"] + results["away_implied"]
    results["home_fair_prob"] = results["home_implied"] / vig
    results["away_fair_prob"] = results["away_implied"] / vig

    results["home_edge"]  = results["model_home_prob"] - results["home_fair_prob"]
    results["away_edge"]  = results["model_away_prob"] - results["away_fair_prob"]
    results["home_value"] = (results["home_edge"] > MIN_EDGE).astype(int)
    results["away_value"] = (results["away_edge"] > MIN_EDGE).astype(int)

    results["home_kelly"] = results.apply(
        lambda r: kelly(r["home_edge"], r["model_home_prob"], r["home_price"])
        if pd.notna(r.get("home_price")) else 0, axis=1)
    results["away_kelly"] = results.apply(
        lambda r: kelly(r["away_edge"], r["model_away_prob"], r["away_price"])
        if pd.notna(r.get("away_price")) else 0, axis=1)

    return results

def print_report(results):
    today = date.today().strftime("%A, %B %d %Y")
    print(f"\n{'='*64}")
    print(f"  MLB VALUE BETS — {today}")
    print(f"  Min edge: {MIN_EDGE:.0%} | Kelly: {KELLY_FRACTION:.0%}")
    print(f"{'='*64}\n")

    value_count = 0
    for _, game in results.iterrows():
        home=game["home_team"]; away=game["away_team"]
        hv=game["home_value"]==1; av=game["away_value"]==1
        has_val = hv or av
        try:
            tip = pd.to_datetime(game["commence_time"], utc=True)\
                    .tz_convert("America/New_York")\
                    .strftime("%I:%M %p ET").lstrip("0")
        except Exception:
            tip = str(game["commence_time"])

        hp=game.get("home_pitcher","TBD"); ap=game.get("away_pitcher","TBD")
        he=float(game.get("home_era") or 4.20)
        ae=float(game.get("away_era") or 4.20)
        hm=float(game.get("model_home_prob",0.5))
        am=float(game.get("model_away_prob",0.5))
        hf=float(game.get("home_fair_prob",0.5))
        af=float(game.get("away_fair_prob",0.5))
        hedg=float(game.get("home_edge",0))
        aedg=float(game.get("away_edge",0))
        hprc=game.get("home_price")
        aprc=game.get("away_price")
        hk=float(game.get("home_kelly",0))
        ak=float(game.get("away_kelly",0))

        print(f"  {away} @ {home}  |  {tip}")
        print(f"  {ap} ({ae:.2f} ERA) vs {hp} ({he:.2f} ERA)")
        print(f"  {'─'*58}")
        print(f"  {'Team':<28} {'Model%':>8} {'Book%':>8} {'Edge':>8} {'Line':>8}")
        print(f"  {'─'*64}")
        print(f"  {home:<28} {hm:>7.1%} {hf:>7.1%} {hedg:>+7.1%} {fmt(hprc):>8}")
        print(f"  {away:<28} {am:>7.1%} {af:>7.1%} {aedg:>+7.1%} {fmt(aprc):>8}")

        if hv:
            print(f"\n  🔥 VALUE: {home} | Edge: {hedg:+.1%} | Kelly: {hk*100:.1f}% | {fmt(hprc)}")
            value_count += 1
        if av:
            print(f"\n  🔥 VALUE: {away} | Edge: {aedg:+.1%} | Kelly: {ak*100:.1f}% | {fmt(aprc)}")
            value_count += 1
        if not has_val:
            print(f"\n  ⚪ No value — skip")
        print()

    print(f"{'='*64}")
    print(f"  Value bets today: {value_count}")
    print(f"{'='*64}\n")
    return value_count

if __name__ == "__main__":
    print("\n── MLB Predict ──────────────────────────────────────────")

    with open("mlb_model.pkl","rb") as f: model = pickle.load(f)
    with open("mlb_features.json") as f: feature_cols = json.load(f)
    print(f"  Model loaded. Features: {len(feature_cols)}")

    conn = get_conn()
    init_predictions(conn)

    odds_df = load_todays_odds(conn)
    if odds_df.empty:
        print("  No games in next 24 hours. Run python mlb_odds.py first.")
        exit()

    starters_df = pd.read_sql("""
        SELECT * FROM probable_starters WHERE game_date = ?
    """, conn, params=(date.today().isoformat(),))
    print(f"  Starters loaded: {len(starters_df)} games.")

    features_df = build_features(odds_df, starters_df, conn, feature_cols)
    if features_df.empty:
        print("  Could not build features.")
        exit()

    results = generate_predictions(features_df, model, feature_cols, odds_df)
    print_report(results)

    today = date.today().isoformat()
    conn.execute("DELETE FROM mlb_predictions WHERE predict_date = ?", (today,))
    results["predict_date"]    = today
    results["actual_home_win"] = None
    save_cols = [c for c in [
        "game_id","predict_date","home_team","away_team","commence_time",
        "home_pitcher","away_pitcher","home_era","away_era",
        "model_home_prob","model_away_prob","home_fair_prob","away_fair_prob",
        "home_edge","away_edge","home_value","away_value",
        "home_kelly","away_kelly","home_price","away_price",
        "bookmaker","actual_home_win"
    ] if c in results.columns]
    results[save_cols].to_sql("mlb_predictions", conn, if_exists="append",
                              index=False, chunksize=50)
    conn.commit()
    print(f"  Predictions saved to mlb.db")
    conn.close()
