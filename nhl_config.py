# ── nhl_config.py ─────────────────────────────────────────────────────────────
# Configuration for the NHL model.
# Keep this separate from config.py / mlb_config.py.

import os
from env_loader import require

# ── Database ──────────────────────────────────────────────────────────────────
NHL_DB_PATH = os.path.join(os.path.dirname(__file__), "nhl.db")

# ── Odds API ──────────────────────────────────────────────────────────────────
ODDS_API_KEY  = require("ODDS_API_KEY")
NHL_SPORT     = "icehockey_nhl"
SHARP_BOOKS   = ["pinnacle", "draftkings", "fanduel", "betmgm", "caesars"]

# ── Model settings ────────────────────────────────────────────────────────────
MIN_EDGE       = 0.05    # minimum edge to flag as value bet — 5% filters below typical vig
KELLY_FRACTION = 0.25   # quarter Kelly

# Training sample weights — exponential time decay.
# Games WEIGHT_HALF_LIFE days old get half the weight of today's games.
WEIGHT_HALF_LIFE = 365

# ── Rolling windows ───────────────────────────────────────────────────────────
ROLLING_SHORT = 5
ROLLING_LONG  = 15

# ── Seasons (NHL uses YYYYYYYY format e.g. 20242025) ──────────────────────────
NHL_SEASONS = ["20222023", "20232024", "20242025", "20252026"]

# ── NHL team abbreviations (32 teams) ─────────────────────────────────────────
NHL_TEAMS = [
    "ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ",
    "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NSH",
    "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SJS", "SEA",
    "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG",
]

# ── Odds API name → abbreviation mapping ──────────────────────────────────────
NHL_NAME_TO_ABBREV = {
    "Anaheim Ducks":        "ANA",
    "Boston Bruins":        "BOS",
    "Buffalo Sabres":       "BUF",
    "Calgary Flames":       "CGY",
    "Carolina Hurricanes":  "CAR",
    "Chicago Blackhawks":   "CHI",
    "Colorado Avalanche":   "COL",
    "Columbus Blue Jackets":"CBJ",
    "Dallas Stars":         "DAL",
    "Detroit Red Wings":    "DET",
    "Edmonton Oilers":      "EDM",
    "Florida Panthers":     "FLA",
    "Los Angeles Kings":    "LAK",
    "Minnesota Wild":       "MIN",
    "Montreal Canadiens":   "MTL",
    "Nashville Predators":  "NSH",
    "New Jersey Devils":    "NJD",
    "New York Islanders":   "NYI",
    "New York Rangers":     "NYR",
    "Ottawa Senators":      "OTT",
    "Philadelphia Flyers":  "PHI",
    "Pittsburgh Penguins":  "PIT",
    "San Jose Sharks":      "SJS",
    "Seattle Kraken":       "SEA",
    "St. Louis Blues":      "STL",
    "Tampa Bay Lightning":  "TBL",
    "Toronto Maple Leafs":  "TOR",
    "Utah Hockey Club":     "UTA",
    "Vancouver Canucks":    "VAN",
    "Vegas Golden Knights": "VGK",
    "Washington Capitals":  "WSH",
    "Winnipeg Jets":        "WPG",
}

# ── Feature columns for model training ───────────────────────────────────────
FEATURE_COLS = [
    # Rolling goals scored / allowed
    "home_goals_scored_last5",  "home_goals_scored_last15",
    "away_goals_scored_last5",  "away_goals_scored_last15",
    "home_goals_allowed_last5", "home_goals_allowed_last15",
    "away_goals_allowed_last5", "away_goals_allowed_last15",

    # Rolling shots for / against
    "home_shots_last5",         "home_shots_last15",
    "away_shots_last5",         "away_shots_last15",
    "home_shots_against_last5", "home_shots_against_last15",
    "away_shots_against_last5", "away_shots_against_last15",

    # Win rates
    "home_win_last5",  "home_win_last15",
    "away_win_last5",  "away_win_last15",

    # Goal differentials
    "home_goal_diff_last5",  "home_goal_diff_last15",
    "away_goal_diff_last5",  "away_goal_diff_last15",

    # Special teams (rolling 10)
    "home_pp_pct_last10",  "away_pp_pct_last10",
    "home_pk_pct_last10",  "away_pk_pct_last10",

    # Goalie save %
    "home_save_pct_last5", "away_save_pct_last5",

    # Streak and rest
    "home_win_streak", "away_win_streak",
    "home_rest_days",  "away_rest_days",

    # Season standing
    "home_season_win_pct", "away_season_win_pct",

    # H2H
    "h2h_home_win_rate",

    # Differentials (feature engineering)
    "goal_diff_diff_last5",  "goal_diff_diff_last15",
    "win_rate_diff_last5",   "win_rate_diff_last15",
    "season_win_pct_diff",
    "shot_diff_last5",

    # Home advantage
    "home_advantage",
]

TARGET = "home_win"
