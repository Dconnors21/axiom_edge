"""Pydantic response models. The frontend's types/api.ts mirrors this contract."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel

League = Literal["nba", "mlb", "nhl"]


class Side(BaseModel):
    team: str
    model_prob: float          # calibrated model win probability
    fair_prob: float           # book-implied (de-vigged where available)
    edge: float                # model_prob - fair_prob
    ev_per_unit: float         # expected value per 1 unit staked
    kelly: float               # stored quarter-Kelly stake fraction
    price: Optional[int]       # American odds
    is_value: bool


class Game(BaseModel):
    game_id: str
    commence_time: str
    home_team: str
    away_team: str
    bookmaker: str
    home: Side
    away: Side
    market_move: float = 0.0
    market_flag: str = ""
    # MLB only
    home_pitcher: Optional[str] = None
    away_pitcher: Optional[str] = None
    home_era: Optional[float] = None
    away_era: Optional[float] = None
    # settled result, if graded
    actual_home_win: Optional[int] = None


class Slate(BaseModel):
    league: League
    slate_date: Optional[str]
    generated_at: str
    game_count: int
    value_count: int
    best_edge: float
    games: list[Game]


class Insight(BaseModel):
    """The single highest-conviction read of the day, across leagues."""
    available: bool
    league: Optional[League] = None
    matchup: Optional[str] = None
    pick: Optional[str] = None
    market: str = "moneyline"
    confidence: Optional[float] = None     # calibrated model prob
    edge: Optional[float] = None
    ev_per_unit: Optional[float] = None
    kelly: Optional[float] = None
    price: Optional[int] = None
    line_movement: str = ""
    rationale: Optional[str] = None
    slate_date: Optional[str] = None


class CalibrationBucket(BaseModel):
    bucket: str          # e.g. "50-60%"
    predicted: float     # mean predicted prob in bucket
    actual: float        # realized hit rate
    n: int


class RocPoint(BaseModel):
    fpr: float
    tpr: float


class Performance(BaseModel):
    league: League
    training_auc: Optional[float]      # headline (training holdout); None when not established
    note: str
    # Evaluated from stored predictions vs realized outcomes:
    graded_n: int
    sufficient: bool                   # enough graded games to plot reliability honestly
    empirical_auc: Optional[float]
    brier: Optional[float]
    log_loss: Optional[float]
    calibration: list[CalibrationBucket]
    roc: list[RocPoint]
    # Realized betting record (from the bet log):
    record_n: int
    wins: int
    losses: int
    roi: Optional[float]               # realized, in units
    clv_avg: Optional[float]


class BetRow(BaseModel):
    date: str
    matchup: str
    pick: str
    line: Optional[int]
    edge: Optional[float]
    result: str
    profit: Optional[float]


class EquityPoint(BaseModel):
    date: str
    cumulative: float


class Roi(BaseModel):
    league: League
    n_bets: int
    wins: int
    losses: int
    pushes: int
    win_rate: Optional[float]
    units_profit: float
    roi: Optional[float]            # mean profit per 1-unit bet
    clv_avg: Optional[float]
    equity: list[EquityPoint]
    bets: list[BetRow]


class PropRow(BaseModel):
    player: str
    market: str          # "Strikeouts" / "Hits" / "Total Bases"
    matchup: str
    line: float
    pred: float
    side: str            # "Over" / "Under"
    prob: float
    edge: float
    kelly: float
    price: Optional[int]


class PropsSlate(BaseModel):
    league: League
    slate_date: Optional[str]
    count: int
    value_count: int
    props: list[PropRow]


class ResearchPlayer(BaseModel):
    player: str
    team: str
    games: int
    stats: dict[str, float]


class Research(BaseModel):
    league: League
    query: str
    stat_keys: list[str]
    teams: list[str]
    players: list[ResearchPlayer]


class ResearchGame(BaseModel):
    date: str
    opponent: str        # opponent abbrev ("" when not captured, e.g. MLB logs)
    home: bool
    stats: dict[str, float]


class ResearchDetail(BaseModel):
    found: bool
    league: League
    player: str
    team: str
    stat_keys: list[str]
    games: list[ResearchGame]          # chronological, oldest -> newest
    averages: dict[str, float]
    recent: dict[str, float]           # last-3 average, for a hot/cold read


class EVRequest(BaseModel):
    prob: float
    american_price: int
    bankroll: float = 0.0
    kelly_fraction: float = 0.25


class EVResponse(BaseModel):
    decimal_odds: float
    implied_prob: float
    edge: float
    ev_per_unit: float
    full_kelly: float
    sized_kelly: float
    recommended_stake: float
