// Shared API contract — mirrors api/models.py (Pydantic). Keep in sync by hand.

export type League = "nba" | "mlb" | "nhl";

export interface Side {
  team: string;
  model_prob: number; // calibrated model win probability
  fair_prob: number; // book-implied
  edge: number; // model_prob - fair_prob
  ev_per_unit: number; // expected value per 1 unit staked
  kelly: number; // stored quarter-Kelly stake fraction
  price: number | null; // American odds
  is_value: boolean;
}

export interface Game {
  game_id: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  bookmaker: string;
  home: Side;
  away: Side;
  market_move: number;
  market_flag: string;
  home_pitcher: string | null;
  away_pitcher: string | null;
  home_era: number | null;
  away_era: number | null;
  actual_home_win: number | null;
}

export interface Slate {
  league: League;
  slate_date: string | null;
  generated_at: string;
  game_count: number;
  value_count: number;
  best_edge: number;
  games: Game[];
}

export interface Insight {
  available: boolean;
  league?: League;
  matchup?: string;
  pick?: string;
  market: string;
  confidence?: number;
  edge?: number;
  ev_per_unit?: number;
  kelly?: number;
  price?: number;
  line_movement: string;
  rationale?: string;
  slate_date?: string;
}

export interface CalibrationBucket {
  bucket: string;
  predicted: number;
  actual: number;
  n: number;
}

export interface RocPoint {
  fpr: number;
  tpr: number;
}

export interface Performance {
  league: League;
  training_auc: number | null;
  note: string;
  graded_n: number;
  sufficient: boolean;
  empirical_auc: number | null;
  brier: number | null;
  log_loss: number | null;
  calibration: CalibrationBucket[];
  roc: RocPoint[];
  record_n: number;
  wins: number;
  losses: number;
  roi: number | null;
  clv_avg: number | null;
}

export interface BetRow {
  date: string;
  matchup: string;
  pick: string;
  line: number | null;
  edge: number | null;
  result: string;
  profit: number | null;
}

export interface EquityPoint {
  date: string;
  cumulative: number;
}

export interface Roi {
  league: League;
  n_bets: number;
  wins: number;
  losses: number;
  pushes: number;
  win_rate: number | null;
  units_profit: number;
  roi: number | null;
  clv_avg: number | null;
  equity: EquityPoint[];
  bets: BetRow[];
}

export interface PropRow {
  player: string;
  market: string;
  matchup: string;
  line: number;
  pred: number;
  side: string;
  prob: number;
  edge: number;
  kelly: number;
  price: number | null;
}

export interface PropsSlate {
  league: League;
  slate_date: string | null;
  count: number;
  value_count: number;
  props: PropRow[];
}

export interface ResearchPlayer {
  player: string;
  team: string;
  games: number;
  stats: Record<string, number>;
}

export interface Research {
  league: League;
  query: string;
  stat_keys: string[];
  teams: string[];
  players: ResearchPlayer[];
}

export interface ResearchGame {
  date: string;
  opponent: string;
  home: boolean;
  stats: Record<string, number>;
}

export interface ResearchDetail {
  found: boolean;
  league: League;
  player: string;
  team: string;
  stat_keys: string[];
  games: ResearchGame[];
  averages: Record<string, number>;
  recent: Record<string, number>;
}

export interface EVRequest {
  prob: number;
  american_price: number;
  bankroll?: number;
  kelly_fraction?: number;
}

export interface EVResponse {
  decimal_odds: number;
  implied_prob: number;
  edge: number;
  ev_per_unit: number;
  full_kelly: number;
  sized_kelly: number;
  recommended_stake: number;
}
