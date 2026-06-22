"""Stake-sizing math. Numbers only — no opinions, no coercion."""
from __future__ import annotations


def american_to_decimal(price: float) -> float:
    """American odds -> decimal odds (total return per 1 staked)."""
    p = float(price)
    if p > 0:
        return p / 100.0 + 1.0
    return 100.0 / abs(p) + 1.0


def american_to_implied(price: float) -> float:
    """American odds -> implied probability (with vig)."""
    p = float(price)
    if p > 0:
        return 100.0 / (p + 100.0)
    return abs(p) / (abs(p) + 100.0)


def ev_per_unit(prob: float, price: float) -> float:
    """Expected value per 1 unit staked: p*(d-1) - (1-p) = p*d - 1."""
    d = american_to_decimal(price)
    return prob * d - 1.0


def kelly_fraction(prob: float, price: float) -> float:
    """Full Kelly fraction of bankroll. Clamped at 0 (never stake on -EV)."""
    d = american_to_decimal(price)
    b = d - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - prob
    f = (b * prob - q) / b
    return max(0.0, f)
