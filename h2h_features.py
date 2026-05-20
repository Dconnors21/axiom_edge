# ── h2h_features.py ───────────────────────────────────────────────────────────
# Builds head-to-head historical features between teams.
# Uses team abbreviations for reliable matching.
#
# Usage: python h2h_features.py

import sqlite3
import pandas as pd
import numpy as np
from config import DB_PATH

def get_conn():
    return sqlite3.connect(DB_PATH)

def build_h2h_features(conn) -> pd.DataFrame:
    print("  Loading data...")

    matchups = pd.read_sql(
        "SELECT * FROM matchups ORDER BY game_date ASC",
        conn, parse_dates=["game_date"]
    )

    # Load all games with home/away info
    games = pd.read_sql("""
        SELECT game_id, game_date, team_abbreviation, is_home, wl, pts, opp_pts, point_diff
        FROM games_featured
        ORDER BY game_date ASC
    """, conn, parse_dates=["game_date"])

    print(f"  Processing {len(matchups):,} matchups...")

    # Verify we have abbreviations in matchups
    sample = matchups[["home_team_abbreviation","away_team_abbreviation"]].head(3)
    print(f"  Sample abbreviations: {sample.values.tolist()}")

    # Build a dict of game_id -> {home_abbr, away_abbr} from matchups
    matchup_teams = matchups.set_index("game_id")[
        ["home_team_abbreviation","away_team_abbreviation","game_date"]
    ].to_dict("index")

    # Build game results indexed by (home_abbr, away_abbr, date)
    # For each game, create a row with both teams' abbreviations
    home_games = games[games["is_home"] == 1].copy()
    away_games = games[games["is_home"] == 0].copy()

    # Merge to get matchup pairs
    game_pairs = home_games[["game_id","game_date","team_abbreviation","wl","pts","opp_pts","point_diff"]].merge(
        away_games[["game_id","team_abbreviation"]].rename(
            columns={"team_abbreviation":"away_abbr"}),
        on="game_id", how="inner"
    ).rename(columns={"team_abbreviation":"home_abbr"})

    game_pairs = game_pairs.sort_values("game_date").reset_index(drop=True)

    print(f"  Built {len(game_pairs):,} game pair records")
    print(f"  Sample game pairs:")
    print(game_pairs[["game_date","home_abbr","away_abbr","wl","point_diff"]].head(3).to_string())

    N_MEETINGS = 8
    h2h_rows   = []

    for idx, matchup in matchups.iterrows():
        game_id   = matchup["game_id"]
        game_date = matchup["game_date"]
        home_abbr = matchup["home_team_abbreviation"]
        away_abbr = matchup["away_team_abbreviation"]

        if not home_abbr or not away_abbr:
            h2h_rows.append(_default_h2h(game_id))
            continue

        # Find all previous meetings between these exact two teams
        # in either home/away configuration
        prev = game_pairs[
            (game_pairs["game_date"] < game_date) &
            (
                ((game_pairs["home_abbr"] == home_abbr) &
                 (game_pairs["away_abbr"] == away_abbr))
                |
                ((game_pairs["home_abbr"] == away_abbr) &
                 (game_pairs["away_abbr"] == home_abbr))
            )
        ].tail(N_MEETINGS)

        if prev.empty:
            h2h_rows.append(_default_h2h(game_id))
            continue

        # Calculate stats from home team's perspective
        home_view = prev[prev["home_abbr"] == home_abbr]
        away_view = prev[prev["home_abbr"] == away_abbr]  # when home was away

        home_wins  = (home_view["wl"] == "W").sum()
        # When our home team played away, a "W" means they won as visitor
        home_wins += (away_view["wl"] == "L").sum()  # they lost = our "home" won

        total      = len(prev)
        win_rate   = home_wins / total

        # Point diff from home team perspective
        home_pdiffs  = home_view["point_diff"].tolist()
        # Flip sign for games where home team was away
        away_pdiffs  = [-x for x in away_view["point_diff"].tolist()]
        all_pdiffs   = home_pdiffs + away_pdiffs
        avg_pdiff    = np.mean(all_pdiffs) if all_pdiffs else 0.0

        home_pts_list = home_view["pts"].tolist() + away_view["opp_pts"].tolist()
        away_pts_list = home_view["opp_pts"].tolist() + away_view["pts"].tolist()

        avg_home_pts = np.mean(home_pts_list) if home_pts_list else 0.0
        avg_away_pts = np.mean(away_pts_list) if away_pts_list else 0.0
        cover_rate   = sum(1 for d in all_pdiffs if d > 3) / max(total, 1)

        h2h_rows.append({
            "game_id":             game_id,
            "h2h_home_win_rate":   round(win_rate, 4),
            "h2h_avg_point_diff":  round(avg_pdiff, 2),
            "h2h_meetings":        total,
            "h2h_home_avg_pts":    round(avg_home_pts, 2),
            "h2h_away_avg_pts":    round(avg_away_pts, 2),
            "h2h_home_cover_rate": round(cover_rate, 4),
            "h2h_last3_pdiff":     round(np.mean(all_pdiffs[-3:]), 2)
                                   if len(all_pdiffs) >= 3 else round(avg_pdiff, 2),
        })

        if (idx+1) % 1000 == 0:
            pct = (idx+1)/len(matchups)*100
            print(f"  {idx+1:,}/{len(matchups):,} ({pct:.0f}%)...")

    df = pd.DataFrame(h2h_rows)
    has_history = (df["h2h_meetings"] > 0).sum()
    print(f"  Done. {has_history:,} matchups ({has_history/len(df):.0%}) have H2H history.")
    return df

def _default_h2h(game_id):
    return {
        "game_id":             game_id,
        "h2h_home_win_rate":   0.5,
        "h2h_avg_point_diff":  0.0,
        "h2h_meetings":        0,
        "h2h_home_avg_pts":    0.0,
        "h2h_away_avg_pts":    0.0,
        "h2h_home_cover_rate": 0.5,
        "h2h_last3_pdiff":     0.0,
    }

def merge_and_save(h2h_df: pd.DataFrame, conn):
    matchups = pd.read_sql("SELECT * FROM matchups", conn,
                           parse_dates=["game_date"])

    # Drop old H2H cols if they exist
    old_h2h = [c for c in matchups.columns if c.startswith("h2h_")]
    if old_h2h:
        matchups = matchups.drop(columns=old_h2h)

    matchups = matchups.merge(h2h_df, on="game_id", how="left")

    # Fill any remaining NaN
    for col in [c for c in matchups.columns if c.startswith("h2h_")]:
        if "win_rate" in col or "cover_rate" in col:
            matchups[col] = matchups[col].fillna(0.5)
        else:
            matchups[col] = matchups[col].fillna(0.0)

    matchups.to_sql("matchups", conn, if_exists="replace", index=False)
    conn.commit()

    h2h_cols = [c for c in matchups.columns if c.startswith("h2h_")]
    print(f"  Saved {len(h2h_cols)} H2H columns to matchups table.")

    # Show correlations
    print(f"\n── H2H correlations with home_win ───────────────────────")
    num = matchups[h2h_cols + ["home_win"]].select_dtypes(include=[np.number])
    corr = num.corr()["home_win"].drop("home_win").abs().sort_values(ascending=False)
    for feat, val in corr.items():
        print(f"  {feat:<35} {val:.4f}")

    return h2h_cols

if __name__ == "__main__":
    print("\n── H2H Feature Builder ──────────────────────────────────")
    conn    = get_conn()
    h2h_df  = build_h2h_features(conn)
    h2h_cols = merge_and_save(h2h_df, conn)

    print(f"\n── Next steps ───────────────────────────────────────────")
    print(f"  Add these to FEATURE_COLS in train.py:")
    for c in h2h_cols:
        print(f"    '{c}',")
    print(f"\n  Then run: python train.py\n")
    conn.close()
