# ── mlb_config.py ─────────────────────────────────────────────────────────────
# Configuration for the MLB model.
# Keep this separate from config.py so NBA and MLB don't interfere.

import os

# ── Database ──────────────────────────────────────────────────────────────────
MLB_DB_PATH = os.path.join(os.path.dirname(__file__), "mlb.db")

# ── Odds API ──────────────────────────────────────────────────────────────────
ODDS_API_KEY  = os.getenv("ODDS_API_KEY", "590ce3633c52e978993d60e6c1507b46")
MLB_SPORT     = "baseball_mlb"
SHARP_BOOKS   = ["pinnacle","draftkings","fanduel","betmgm","caesars"]

# ── Model settings ────────────────────────────────────────────────────────────
MIN_EDGE      = 0.05    # minimum edge to flag as value bet — 5% filters below typical vig
KELLY_FRACTION = 0.25   # quarter Kelly

# Training sample weights — exponential time decay.
# Games WEIGHT_HALF_LIFE days old get half the weight of today's games.
WEIGHT_HALF_LIFE = 365

# ── Rolling windows ───────────────────────────────────────────────────────────
ROLLING_SHORT = 5
ROLLING_LONG  = 15      # longer window for MLB — 162 game season

# ── Seasons ───────────────────────────────────────────────────────────────────
MLB_SEASONS   = ["2023", "2024", "2025", "2026"]  # MLB uses single year format

# ── Key MLB features (different from NBA) ────────────────────────────────────
# Starting pitcher ERA, team batting average, bullpen ERA,
# home/away splits, run differential, park factors

FEATURE_COLS = [
    # Team rolling offense
    "home_runs_scored_last5",  "home_runs_scored_last15",
    "away_runs_scored_last5",  "away_runs_scored_last15",

    # Team rolling defense (runs allowed)
    "home_runs_allowed_last5", "home_runs_allowed_last15",
    "away_runs_allowed_last5", "away_runs_allowed_last15",

    # Win rates
    "home_win_last5",  "home_win_last15",
    "away_win_last5",  "away_win_last15",

    # Run differentials
    "home_run_diff_last5",  "home_run_diff_last15",
    "away_run_diff_last5",  "away_run_diff_last15",

    # Streaks and rest
    "home_win_streak",   "away_win_streak",
    "home_rest_days",    "away_rest_days",

    # Season standing
    "home_season_win_pct", "away_season_win_pct",

    # Starting pitcher (key MLB signal)
    "home_sp_era_last3",   "away_sp_era_last3",
    "home_sp_era_season",  "away_sp_era_season",
    "home_sp_whip_season", "away_sp_whip_season",

    # Bullpen
    "home_bullpen_era_last7", "away_bullpen_era_last7",

    # Home/away splits
    "home_win_pct_home",  "away_win_pct_away",

    # H2H
    "h2h_home_win_rate",  "h2h_avg_run_diff",

    # Differentials
    "run_diff_diff_last5", "run_diff_diff_last15",
    "win_rate_diff_last5", "win_rate_diff_last15",
    "season_win_pct_diff",
    "sp_era_diff",

    # Park factor (some parks favor hitters/pitchers)
    "park_factor",

    # Home advantage
    "home_advantage",
]

TARGET = "home_win"

