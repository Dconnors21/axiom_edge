"""AXIOM Edge serving layer (FastAPI). Read-only JSON over the prediction DBs."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import LEAGUES, connect, latest_slate_date, fetch_slate
from .ev import american_to_decimal, american_to_implied, ev_per_unit, kelly_fraction
from . import metrics
from .ladder import build_ladder
from .models import (
    Side, Game, Slate, Insight, Performance, CalibrationBucket, RocPoint,
    Roi, BetRow, EquityPoint, PropRow, PropsSlate, ResearchPlayer, Research,
    ResearchGame, ResearchDetail, Ladder, EVRequest, EVResponse,
)

app = FastAPI(title="AXIOM Edge API", version="0.1.0")

# CORS for the Next app only (dev origins). No credentials, no secrets to client.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.1.183:3000",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Realized-bet log tables per league (for /performance). Missing tables degrade gracefully.
_BET_LOG = {"nba": "bet_log", "mlb": "mlb_bet_log", "nhl": "nhl_bet_log"}
_AUC_NOTE = {
    "nba": "Calibrated XGBoost. The established edge.",
    "mlb": "Baseline. No out-of-sample edge yet, shown plainly.",
    "nhl": "Not yet established.",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(row: sqlite3.Row, key: str, default: float = 0.0) -> float:
    try:
        v = row[key]
        return float(v) if v is not None else default
    except (IndexError, KeyError, TypeError, ValueError):
        return default


def _price(row: sqlite3.Row, key: str):
    try:
        v = row[key]
        return int(v) if v is not None else None
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def _has(row: sqlite3.Row, key: str) -> bool:
    return key in row.keys()


def _side(row: sqlite3.Row, p: str) -> Side:
    prob = _f(row, f"model_{p}_prob", 0.5)
    fair = _f(row, f"{p}_fair_prob", 0.5)
    price = _price(row, f"{p}_price")
    return Side(
        team=row[f"{p}_team"],
        model_prob=prob,
        fair_prob=fair,
        edge=_f(row, f"{p}_edge"),
        ev_per_unit=ev_per_unit(prob, price) if price is not None else 0.0,
        kelly=_f(row, f"{p}_kelly"),
        price=price,
        is_value=int(_f(row, f"{p}_value")) == 1,
    )


def _game(row: sqlite3.Row, pitchers: bool) -> Game:
    g = Game(
        game_id=str(row["game_id"]),
        commence_time=str(row["commence_time"] or ""),
        home_team=row["home_team"],
        away_team=row["away_team"],
        bookmaker=str(row["bookmaker"] or ""),
        home=_side(row, "home"),
        away=_side(row, "away"),
        market_move=_f(row, "market_move"),
        market_flag=str(row["market_flag"]) if _has(row, "market_flag") and row["market_flag"] else "",
        actual_home_win=int(row["actual_home_win"]) if _has(row, "actual_home_win") and row["actual_home_win"] is not None else None,
    )
    if pitchers:
        g.home_pitcher = row["home_pitcher"] if _has(row, "home_pitcher") else None
        g.away_pitcher = row["away_pitcher"] if _has(row, "away_pitcher") else None
        g.home_era = _f(row, "home_era") or None
        g.away_era = _f(row, "away_era") or None
    return g


def _conviction(side: Side) -> float:
    """Composite: 40% edge, 35% probability conviction, 25% Kelly sizing."""
    return 0.40 * side.edge + 0.35 * max(0.0, side.model_prob - 0.50) + 0.25 * side.kelly


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "leagues": list(LEAGUES.keys())}


@app.get("/api/slate/{league}", response_model=Slate)
def slate(league: str) -> Slate:
    if league not in LEAGUES:
        raise HTTPException(404, f"Unknown league: {league}")
    cfg = LEAGUES[league]
    conn = connect(league)
    try:
        date = latest_slate_date(conn, cfg["ml_table"])
        rows = fetch_slate(conn, cfg["ml_table"], date) if date else []
    finally:
        conn.close()

    games = [_game(r, cfg["pitchers"]) for r in rows]
    value_count = sum(1 for g in games if g.home.is_value or g.away.is_value)
    best_edge = max((max(g.home.edge, g.away.edge) for g in games), default=0.0)
    return Slate(
        league=league, slate_date=date, generated_at=_now(),
        game_count=len(games), value_count=value_count,
        best_edge=best_edge, games=games,
    )


@app.get("/api/insight", response_model=Insight)
def insight() -> Insight:
    """Single highest-conviction value pick across all leagues' latest slates."""
    best = None  # (conviction, league, game, side)
    for league, cfg in LEAGUES.items():
        conn = connect(league)
        try:
            date = latest_slate_date(conn, cfg["ml_table"])
            if not date:
                continue
            rows = fetch_slate(conn, cfg["ml_table"], date)
        finally:
            conn.close()
        for r in rows:
            g = _game(r, cfg["pitchers"])
            for side in (g.home, g.away):
                if not side.is_value or side.price is None:
                    continue
                score = _conviction(side)
                if best is None or score > best[0]:
                    best = (score, league, g, side, date)

    if best is None:
        return Insight(available=False)

    _, league, g, side, date = best
    rationale = (
        f"Model reads {side.model_prob:.1%} versus the market's {side.fair_prob:.1%} "
        f"implied, a {side.edge:+.1%} edge. Quarter-Kelly sizes this at "
        f"{side.kelly * 100:.1f}% of bankroll."
    )
    return Insight(
        available=True, league=league,
        matchup=f"{g.away_team} @ {g.home_team}",
        pick=side.team, market="moneyline",
        confidence=side.model_prob, edge=side.edge,
        ev_per_unit=side.ev_per_unit, kelly=side.kelly, price=side.price,
        line_movement=g.market_flag, rationale=rationale, slate_date=date,
    )


def _is_win(result) -> int | None:
    if result is None:
        return None
    s = str(result).strip().lower()
    if s in ("win", "w", "1", "true"):
        return 1
    if s in ("loss", "l", "0", "false"):
        return 0
    if s in ("push", "p", "void", "tie"):
        return None
    return None


@app.get("/api/performance/{league}", response_model=Performance)
def performance(league: str) -> Performance:
    if league not in LEAGUES:
        raise HTTPException(404, f"Unknown league: {league}")
    cfg = LEAGUES[league]

    # Reliability/ROC from stored predictions (model prob vs realized outcome).
    conn = connect(league)
    try:
        pred_rows = conn.execute(
            f"SELECT model_home_prob AS p, actual_home_win AS y FROM {cfg['ml_table']} "
            f"WHERE actual_home_win IS NOT NULL AND model_home_prob IS NOT NULL"
        ).fetchall()
        # Realized betting record from the bet log (separate from model calibration).
        try:
            bet_rows = conn.execute(
                f"SELECT result, profit_units, clv FROM {_BET_LOG[league]}"
            ).fetchall()
        except sqlite3.OperationalError:
            bet_rows = []
    finally:
        conn.close()

    pairs = [(float(r["p"]), int(r["y"])) for r in pred_rows]
    graded_n = len(pairs)
    sufficient = graded_n >= metrics.MIN_SAMPLE

    calibration = (
        [CalibrationBucket(**b) for b in metrics.calibration(pairs)] if sufficient else []
    )
    roc = [RocPoint(**pt) for pt in metrics.roc_curve(pairs)] if sufficient else []

    bets = [(_is_win(r["result"]), r["profit_units"], r["clv"]) for r in bet_rows]
    bets = [b for b in bets if b[0] is not None]
    wins = sum(1 for w, _, _ in bets if w == 1)
    losses = sum(1 for w, _, _ in bets if w == 0)
    profits = [p for _, p, _ in bets if p is not None]
    clvs = [c for _, _, c in bets if c is not None]

    return Performance(
        league=league,
        training_auc=cfg["training_auc"], note=_AUC_NOTE[league],
        graded_n=graded_n, sufficient=sufficient,
        empirical_auc=metrics.empirical_auc(pairs) if sufficient else None,
        brier=metrics.brier(pairs) if sufficient else None,
        log_loss=metrics.log_loss(pairs) if sufficient else None,
        calibration=calibration, roc=roc,
        record_n=len(bets), wins=wins, losses=losses,
        roi=(sum(profits) / len(profits)) if profits else None,
        clv_avg=(sum(clvs) / len(clvs)) if clvs else None,
    )


@app.get("/api/roi/{league}", response_model=Roi)
def roi(league: str) -> Roi:
    if league not in LEAGUES:
        raise HTTPException(404, f"Unknown league: {league}")
    table = _BET_LOG[league]
    rows: list[sqlite3.Row] = []
    conn = connect(league)
    try:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        except sqlite3.OperationalError:
            rows = []
    finally:
        conn.close()

    # The bet logs differ slightly by league; access columns defensively.
    def col(r: sqlite3.Row, *names):
        keys = r.keys()
        for n in names:
            if n in keys:
                return r[n]
        return None

    usable = [r for r in rows if col(r, "result") is not None]
    usable.sort(key=lambda r: (str(col(r, "recorded_at", "predict_date") or ""),))

    wins = losses = pushes = 0
    cum = 0.0
    equity: list[EquityPoint] = []
    bets: list[BetRow] = []
    profits: list[float] = []
    clvs: list[float] = []

    for r in usable:
        w = _is_win(col(r, "result"))
        res = str(col(r, "result") or "").strip().upper()
        profit = col(r, "profit_units")
        profit = float(profit) if profit is not None else None
        if w == 1:
            wins += 1
        elif w == 0:
            losses += 1
        else:
            pushes += 1
        if profit is not None:
            cum += profit
            profits.append(profit)
            equity.append(EquityPoint(date=str(col(r, "predict_date") or ""), cumulative=round(cum, 4)))
        clv = col(r, "clv")
        if clv is not None:
            clvs.append(float(clv))
        home, away = col(r, "home_team"), col(r, "away_team")
        line = col(r, "line")
        edge = col(r, "edge")
        bets.append(BetRow(
            date=str(col(r, "predict_date") or ""),
            matchup=f"{away} @ {home}" if home and away else "",
            pick=str(col(r, "bet_team") or ""),
            line=int(line) if line is not None else None,
            edge=float(edge) if edge is not None else None,
            result=res or "—",
            profit=profit,
        ))

    graded = wins + losses
    bets.reverse()  # most recent first for the log
    return Roi(
        league=league, n_bets=len(usable), wins=wins, losses=losses, pushes=pushes,
        win_rate=(wins / graded) if graded else None,
        units_profit=round(cum, 4),
        roi=(sum(profits) / len(profits)) if profits else None,
        clv_avg=(sum(clvs) / len(clvs)) if clvs else None,
        equity=equity, bets=bets[:50],
    )


_MLB_PROP_TABLES = [
    ("mlb_props_predictions_k", "pred_ks", "Strikeouts"),
    ("mlb_props_predictions_hits", "pred_hits", "Hits"),
    ("mlb_props_predictions_tb", "pred_tb", "Total Bases"),
]


@app.get("/api/props/{league}", response_model=PropsSlate)
def props(league: str) -> PropsSlate:
    if league not in LEAGUES:
        raise HTTPException(404, f"Unknown league: {league}")
    if league != "mlb":
        return PropsSlate(league=league, slate_date=None, count=0, value_count=0, props=[])

    conn = connect(league)
    rows: list[PropRow] = []
    total = 0
    latest: str | None = None
    try:
        for table, pred_col, market in _MLB_PROP_TABLES:
            try:
                d = latest_slate_date(conn, table)
            except sqlite3.OperationalError:
                continue
            if not d:
                continue
            latest = max(latest, d) if latest else d
            for r in conn.execute(f"SELECT * FROM {table} WHERE predict_date = ?", (d,)):
                total += 1
                over_val = int(_f(r, "over_value")) == 1
                under_val = int(_f(r, "under_value")) == 1
                if not (over_val or under_val):
                    continue
                side = "Over" if over_val else "Under"
                pre = "over" if over_val else "under"
                rows.append(PropRow(
                    player=r["player_name"], market=market,
                    matchup=f"{r['away_team']} @ {r['home_team']}",
                    line=_f(r, "line"), pred=_f(r, pred_col), side=side,
                    prob=_f(r, f"{pre}_prob"), edge=_f(r, f"{pre}_edge"),
                    kelly=_f(r, f"{pre}_kelly"), price=_price(r, f"{pre}_price"),
                ))
    finally:
        conn.close()

    rows.sort(key=lambda p: p.edge, reverse=True)
    return PropsSlate(
        league=league, slate_date=latest, count=total,
        value_count=len(rows), props=rows,
    )


# Research: recent per-player form from game logs. (label, sql_expr, is_avg)
_RESEARCH = {
    "nba": {
        "table": "player_game_logs", "team_col": "team_abbreviation", "opp_col": "matchup",
        "keys": ["MIN", "PTS", "REB", "AST"],
        "cols": {"MIN": "min_played", "PTS": "pts", "REB": "reb", "AST": "ast"},
    },
    "mlb": {
        "table": "mlb_batter_game_logs", "team_col": "team", "opp_col": "opponent",
        "keys": ["PA", "H", "TB", "HR"],
        "cols": {"PA": "at_bats", "H": "hits", "TB": "total_bases", "HR": "home_runs"},
    },
}


@app.get("/api/research/{league}", response_model=Research)
def research(league: str, q: str = "", team: str = "", limit: int = 40, window: int = 10) -> Research:
    if league not in _RESEARCH:
        raise HTTPException(404, f"Research not available for: {league}")
    cfg = _RESEARCH[league]
    tcol = cfg["team_col"]
    conn = connect(league)
    players: list[ResearchPlayer] = []
    teams: list[str] = []
    try:
        teams = [
            r[0] for r in conn.execute(
                f"SELECT DISTINCT {tcol} FROM {cfg['table']} "
                f"WHERE {tcol} IS NOT NULL AND {tcol} != '' ORDER BY {tcol}"
            ).fetchall()
        ]
        like = f"%{q.strip()}%"
        where = "player_name LIKE ?"
        params: list = [like]
        if team:
            where += f" AND {tcol} = ?"
            params.append(team)
        cand = conn.execute(
            f"SELECT player_name, COUNT(*) n FROM {cfg['table']} "
            f"WHERE {where} GROUP BY player_name ORDER BY n DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        for c in cand:
            name = c["player_name"]
            recent = conn.execute(
                f"SELECT * FROM {cfg['table']} WHERE player_name = ? "
                f"ORDER BY game_date DESC LIMIT ?", (name, window),
            ).fetchall()
            if not recent:
                continue
            stats = {
                k: round(sum(_f(r, col) for r in recent) / len(recent), 2)
                for k, col in cfg["cols"].items()
            }
            players.append(ResearchPlayer(
                player=name, team=str(recent[0][cfg["team_col"]] or ""),
                games=len(recent), stats=stats,
            ))
    finally:
        conn.close()
    return Research(
        league=league, query=q, stat_keys=cfg["keys"], teams=teams, players=players,
    )


@app.get("/api/research/{league}/player", response_model=ResearchDetail)
def research_player(league: str, name: str, window: int = 10) -> ResearchDetail:
    if league not in _RESEARCH:
        raise HTTPException(404, f"Research not available for: {league}")
    cfg = _RESEARCH[league]
    empty = ResearchDetail(
        found=False, league=league, player=name, team="", stat_keys=cfg["keys"],
        games=[], averages={}, recent={},
    )
    conn = connect(league)
    try:
        rows = conn.execute(
            f"SELECT * FROM {cfg['table']} WHERE player_name = ? "
            f"ORDER BY game_date DESC LIMIT ?", (name, window),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return empty

    def _opp_home(r) -> tuple[str, bool]:
        home = bool(int(_f(r, "is_home")))
        if league == "nba":
            m = str(r["matchup"] or "")
            if "@" in m:
                return m.split("@")[-1].strip().upper(), False
            if "vs" in m.lower():
                return m.lower().split("vs")[-1].replace(".", "").strip().upper(), True
            return "", home
        return str(r["opponent"] or "").upper(), home

    chrono = list(reversed(rows))  # oldest -> newest for the trend line
    games = []
    for r in chrono:
        opp, home = _opp_home(r)
        games.append(ResearchGame(
            date=str(r["game_date"] or "")[:10],
            opponent=opp, home=home,
            stats={k: _f(r, col) for k, col in cfg["cols"].items()},
        ))
    averages = {
        k: round(sum(_f(r, col) for r in rows) / len(rows), 2)
        for k, col in cfg["cols"].items()
    }
    last3 = rows[:3]
    recent = {
        k: round(sum(_f(r, col) for r in last3) / len(last3), 2)
        for k, col in cfg["cols"].items()
    }
    return ResearchDetail(
        found=True, league=league, player=rows[0]["player_name"],
        team=str(rows[0][cfg["team_col"]] or ""), stat_keys=cfg["keys"],
        games=games, averages=averages, recent=recent,
    )


@app.get("/api/ladder", response_model=Ladder)
def ladder(stake: float = 50.0, days: int = 10) -> Ladder:
    return build_ladder(stake=stake, target_days=days)


@app.post("/api/ev", response_model=EVResponse)
def ev(req: EVRequest) -> EVResponse:
    implied = american_to_implied(req.american_price)
    full = kelly_fraction(req.prob, req.american_price)
    sized = full * req.kelly_fraction
    return EVResponse(
        decimal_odds=american_to_decimal(req.american_price),
        implied_prob=implied,
        edge=req.prob - implied,
        ev_per_unit=ev_per_unit(req.prob, req.american_price),
        full_kelly=full,
        sized_kelly=sized,
        recommended_stake=sized * req.bankroll,
    )
