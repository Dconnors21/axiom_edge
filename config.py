# ── config.py ─────────────────────────────────────────────────────────────────
# Central config for the NBA value bets model.
# Replace YOUR_ODDS_API_KEY_HERE with your actual key from the-odds-api.com

# ── API Keys ──────────────────────────────────────────────────────────────────
import os
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "590ce3633c52e978993d60e6c1507b46")

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = "nba.db"

# ── Model settings ────────────────────────────────────────────────────────────
# Seasons to pull historical data for (used for training)
SEASONS = ["2023-24", "2024-25", "2025-26"]

# Minimum edge (model prob - implied book prob) to flag as a value bet
MIN_EDGE = 0.03        # 3% edge required

# Kelly fraction — use 1/4 Kelly for conservative sizing
KELLY_FRACTION = 0.25

# Rolling window sizes for feature engineering
ROLLING_SHORT = 5      # last 5 games
ROLLING_LONG  = 10     # last 10 games

# ── Odds API settings ─────────────────────────────────────────────────────────
ODDS_SPORT    = "basketball_nba"
ODDS_REGIONS  = "us"
ODDS_MARKETS  = "h2h,spreads,totals"   # moneyline, spread, over/under
ODDS_FORMAT   = "american"

# ── Sportsbooks to pull lines from (ranked by sharpness) ─────────────────────
# Pinnacle is the sharpest book — their line = market consensus
# We use it as the benchmark for implied probability
SHARP_BOOKS = ["pinnacle", "draftkings", "fanduel", "betmgm", "caesars"]

