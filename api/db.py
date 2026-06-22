"""Read-only access to the precomputed prediction databases."""
from __future__ import annotations

import sqlite3
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# League -> database + moneyline table. The moneyline tables share a common shape
# across leagues (model_*_prob, *_fair_prob, *_edge, *_value, *_kelly, *_price,
# market_flag/market_move); MLB adds probable pitchers + ERA.
LEAGUES: dict[str, dict] = {
    "nba": {"db": "nba.db", "ml_table": "predictions",     "pitchers": False, "training_auc": 0.7147},
    "mlb": {"db": "mlb.db", "ml_table": "mlb_predictions", "pitchers": True,  "training_auc": 0.5309},
    "nhl": {"db": "nhl.db", "ml_table": "nhl_predictions", "pitchers": False, "training_auc": None},
}


def db_path(league: str) -> Path:
    return _ROOT / LEAGUES[league]["db"]


def connect(league: str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path(league)))
    conn.row_factory = sqlite3.Row
    return conn


def latest_slate_date(conn: sqlite3.Connection, table: str) -> str | None:
    """Most recent predict_date present. Robust to the local-vs-UTC date skew
    (predict scripts write local date.today(); we never assume UTC 'today')."""
    row = conn.execute(f"SELECT MAX(predict_date) AS d FROM {table}").fetchone()
    return row["d"] if row and row["d"] else None


def fetch_slate(conn: sqlite3.Connection, table: str, date: str) -> list[sqlite3.Row]:
    return conn.execute(
        f"SELECT * FROM {table} WHERE predict_date = ? ORDER BY commence_time",
        (date,),
    ).fetchall()
