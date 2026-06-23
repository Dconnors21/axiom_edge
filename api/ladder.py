"""Ladder Challenge: build a 2-4 leg play with combined odds near +100 from the
day's highest-confidence value bets, then project a let-it-ride streak.

Honest by design: the combined model probability and the real survival odds of
a 7-10 day run are surfaced, not hidden behind a 'double your money' pitch.
"""
from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations

from .db import LEAGUES, connect, latest_slate_date
from .ev import american_to_decimal
from .models import Ladder, LadderLeg, LadderRung


def _is_upcoming(commence_time: str) -> bool:
    """Only games that haven't started — excludes stale offseason slates and
    games already underway."""
    try:
        dt = datetime.fromisoformat(str(commence_time).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False

# Combined-decimal band that reads as "right around +100, roughly doubles"
# (-111 .. +130). 2-4 moderate favorites overshoot +100, so heavy favorites (or
# a single near-even play) are what land here — the search picks whatever does.
_TARGET_LO, _TARGET_HI = 1.90, 2.30
_MIN_LEG_PROB = 0.55     # a leg must be one the model is confident in
_MAX_POOL = 14           # cap candidates before the combinatorial search
_MIN_LEGS, _MAX_LEGS = 1, 4


def _decimal_to_american(d: float) -> int:
    return round((d - 1) * 100) if d >= 2 else round(-100 / (d - 1))


def _candidate_legs() -> list[dict]:
    legs: list[dict] = []

    # Moneyline value bets across leagues.
    for lg, cfg in LEAGUES.items():
        conn = connect(lg)
        try:
            d = latest_slate_date(conn, cfg["ml_table"])
            rows = conn.execute(
                f"SELECT * FROM {cfg['ml_table']} WHERE predict_date = ?", (d,)
            ).fetchall() if d else []
        finally:
            conn.close()
        for r in rows:
            if not _is_upcoming(r["commence_time"]):
                continue
            # The model's favored side — a confident pick, value-flagged or not.
            try:
                hp = float(r["model_home_prob"] or 0)
                ap = float(r["model_away_prob"] or 0)
            except (KeyError, IndexError, TypeError):
                continue
            side = "home" if hp >= ap else "away"
            prob = max(hp, ap)
            price = r[f"{side}_price"]
            if price is None or prob < _MIN_LEG_PROB:
                continue
            legs.append({
                "league": lg, "market": "Moneyline",
                "selection": r[f"{side}_team"],
                "matchup": f"{r['away_team']} @ {r['home_team']}",
                "game_id": f"{lg}:{r['game_id']}",
                "model_prob": prob, "price": int(price),
                "decimal": american_to_decimal(int(price)),
            })

    # Strikeout UNDER props (the validated soft-market edge).
    conn = connect("mlb")
    try:
        d = latest_slate_date(conn, "mlb_props_predictions_k")
        rows = conn.execute(
            "SELECT * FROM mlb_props_predictions_k WHERE predict_date = ? AND under_value = 1",
            (d,),
        ).fetchall() if d else []
    finally:
        conn.close()
    for r in rows:
        if not _is_upcoming(r["commence_time"]):
            continue
        price = r["under_price"]
        prob = float(r["under_prob"] or 0)
        if price is not None and prob >= _MIN_LEG_PROB:
            legs.append({
                "league": "mlb", "market": "Strikeouts",
                "selection": f"{r['player_name']} u{r['line']} K",
                "matchup": f"{r['away_team']} @ {r['home_team']}",
                "game_id": f"mlb_k:{r['game_id']}:{r['player_name']}",
                "model_prob": prob, "price": int(price),
                "decimal": american_to_decimal(int(price)),
            })

    # Most confident first; cap the pool for the combinatorial search.
    legs.sort(key=lambda x: x["model_prob"], reverse=True)
    return legs[:_MAX_POOL]


def _best_combo(legs: list[dict]):
    """Among 2-4 leg, distinct-game combos landing in the odds band, pick the one
    with the highest joint model probability (the safest ladder near +100)."""
    best = None
    for n in range(_MIN_LEGS, _MAX_LEGS + 1):
        for combo in combinations(legs, n):
            if len({l["game_id"] for l in combo}) != n:
                continue  # no two legs from the same game (correlation)
            dec = 1.0
            joint = 1.0
            for l in combo:
                dec *= l["decimal"]
                joint *= l["model_prob"]
            if _TARGET_LO <= dec <= _TARGET_HI:
                if best is None or joint > best[0]:
                    best = (joint, dec, combo)
    return best


def build_ladder(stake: float = 50.0, target_days: int = 10) -> Ladder:
    legs = _candidate_legs()
    if len(legs) < _MIN_LEGS:
        return Ladder(available=False,
                      reason="Not enough high-confidence value bets on the board today.")

    best = _best_combo(legs)
    if best is None:
        return Ladder(available=False,
                      reason="No 2-4 leg combination lands near +100 today.")

    joint, dec, combo = best
    american = _decimal_to_american(dec)
    break_even = 1.0 / dec
    projection = [LadderRung(day=i, balance=round(stake * dec ** i, 2))
                  for i in range(1, target_days + 1)]

    return Ladder(
        available=True,
        slate_date=None,
        legs=[LadderLeg(**{k: l[k] for k in
                           ("league", "market", "selection", "matchup",
                            "model_prob", "price", "decimal")}) for l in combo],
        combined_american=american,
        combined_decimal=round(dec, 3),
        combined_model_prob=round(joint, 4),
        break_even_prob=round(break_even, 4),
        ev_per_unit=round(joint * dec - 1, 4),
        edge=round(joint - break_even, 4),
        stake=stake,
        payout=round(stake * dec, 2),
        target_days=target_days,
        projection=projection,
        survival_7=round(joint ** 7 * 100, 1),
        survival_10=round(joint ** 10 * 100, 1),
    )
