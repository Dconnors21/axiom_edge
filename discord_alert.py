"""
discord_alert.py — Sends today's AXIOM Edge best bets to Discord as rich embeds.

Called automatically by run_daily.py at the end of the morning pipeline.
Run manually any time: python discord_alert.py

Setup: add your webhook URL to .env → DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
"""

import json
import sqlite3
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path
import pandas as pd

# ── Constants ─────────────────────────────────────────────────────────────────
NBA_DB       = Path("nba.db")
MLB_DB       = Path("mlb.db")
NHL_DB       = Path("nhl.db")
NBA_MIN_EDGE = 0.03
MLB_MIN_EDGE = 0.03
NHL_MIN_EDGE = 0.03

NBA_COLOR  = int("6366f1", 16)   # indigo  #6366f1
MLB_COLOR  = int("22c55e", 16)   # green   #22c55e
NHL_COLOR  = int("38bdf8", 16)   # sky     #38bdf8 (matches NHL dashboard)
SKIP_COLOR = int("2a2a35", 16)   # dark gray (no pick)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_env() -> dict:
    """Parse .env for DISCORD_WEBHOOK_URL without requiring python-dotenv."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return {}
    result = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result

def _load(db: Path, query: str, params=None) -> pd.DataFrame:
    if not db.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(db)
    try:
        df = pd.read_sql(query, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

def _fmt_price(price) -> str:
    try:
        p = int(price)
        return f"+{p}" if p > 0 else str(p)
    except Exception:
        return "N/A"

def _fmt_tip(commence_time) -> str:
    try:
        return pd.to_datetime(commence_time, utc=True) \
                 .tz_convert("America/New_York") \
                 .strftime("%I:%M %p ET").lstrip("0")
    except Exception:
        return str(commence_time)

def _get_best(preds: pd.DataFrame, min_edge: float):
    if preds.empty:
        return None
    candidates = []
    for _, game in preds.iterrows():
        for side in ["home", "away"]:
            if not game.get(f"{side}_value"):
                continue
            edge  = float(game.get(f"{side}_edge", 0))
            prob  = float(game.get(f"model_{side}_prob", 0))
            kelly = float(game.get(f"{side}_kelly", 0))
            price = game.get(f"{side}_price")
            if edge < min_edge or prob < 0.50 or kelly < 0.005:
                continue
            bet_team = game["home_team"] if side == "home" else game["away_team"]
            candidates.append({
                "bet_team":      bet_team,
                "edge":          edge,
                "prob":          prob,
                "fair_prob":     float(game.get(f"{side}_fair_prob", 0.5)),
                "price":         price,
                "kelly":         kelly,
                "commence_time": game.get("commence_time", ""),
                "bookmaker":     str(game.get("bookmaker", "")).upper(),
                "home_team":     game["home_team"],
                "away_team":     game["away_team"],
                "home_pitcher":  game.get("home_pitcher"),
                "away_pitcher":  game.get("away_pitcher"),
                "home_era":      game.get("home_era"),
                "away_era":      game.get("away_era"),
                "market_flag":   str(game.get("market_flag", "") or ""),
            })
    if not candidates:
        return None
    # Prefer ladder-eligible (price <= -250 or <= +250 favorite), then highest edge
    candidates.sort(key=lambda x: (
        int(float(x["price"]) <= 250) if x["price"] else 0,
        x["edge"]
    ), reverse=True)
    return candidates[0]


# ── Headline / market-pick rendering ──────────────────────────────────────────
# The card headline is the single highest-edge value play across ALL markets
# (moneyline / spread / totals), not forced to be the moneyline. Whichever market
# wins the headline gets a full block; the remaining markets render compactly.

def _ladder_str(price) -> str:
    try:
        return "Yes 🪜" if float(price) <= 250 else "No"
    except Exception:
        return "—"

def _market_field(p):
    """Optional '📈 Market' field when a line-movement signal is attached."""
    flag = str(p.get("market_flag", "") or "").strip()
    if not flag:
        return None
    return {"name": "📈 Market", "value": flag, "inline": True}


def _ml_headline(p, cfg) -> list:
    fields = [
        {"name": "🎯 Best Bet — Moneyline", "value": f"**{p['bet_team']}** `{_fmt_price(p['price'])}`", "inline": True},
        {"name": cfg["tip"],          "value": _fmt_tip(p["commence_time"]) or "—",     "inline": True},
        {"name": "📚 Book",           "value": p["bookmaker"] or "—",                   "inline": True},
        {"name": "📈 Edge",           "value": f"**{p['edge']:+.1%}**",                 "inline": True},
        {"name": "🤖 Model Prob",     "value": f"{p['prob']:.1%}",                      "inline": True},
        {"name": "📊 Book Implied",   "value": f"{p['fair_prob']:.1%}",                 "inline": True},
        {"name": "💰 Kelly Stake",    "value": f"{p['kelly']*100:.1f}% of bankroll",    "inline": True},
        {"name": "🪜 Ladder",         "value": _ladder_str(p["price"]),                 "inline": True},
        {"name": "🏟️ Matchup",       "value": f"{p['away_team']} @ {p['home_team']}",   "inline": False},
    ]
    mf = _market_field(p)
    if mf: fields.insert(-1, mf)
    return fields

def _ats_headline(p, cfg) -> list:
    spr = f"{p['spread']:+.1f}" if p.get("spread") is not None else ""
    margin = ""
    if cfg.get("margin_unit") and p.get("pred_home_margin") is not None:
        margin = f"  ·  Pred margin: {p['pred_home_margin']:+.1f} {cfg['margin_unit']}"
    fields = [
        {"name": f"🎯 Best Bet — {cfg['spread_short']}", "value": f"**{p['bet_team']} {spr}** `{_fmt_price(p['price'])}`", "inline": True},
        {"name": cfg["tip"],        "value": _fmt_tip(p.get("commence_time", "")) or "—", "inline": True},
        {"name": "📚 Book",         "value": (str(p.get("bookmaker")) or "—").upper(),    "inline": True},
        {"name": "📈 Edge",         "value": f"**{p['edge']:+.1%}**",                     "inline": True},
        {"name": "📐 P(cover)",     "value": f"{p['cover_prob']:.1%}",                    "inline": True},
        {"name": "💰 Kelly Stake",  "value": f"{p['kelly']*100:.1f}% of bankroll",        "inline": True},
        {"name": "🏟️ Matchup",     "value": f"{p['away_team']} @ {p['home_team']}{margin}", "inline": False},
    ]
    mf = _market_field(p)
    if mf: fields.insert(-1, mf)
    return fields

def _total_headline(p, cfg) -> list:
    side = "OVER" if p["side"] == "over" else "UNDER"
    line = f"{p['total_line']:.1f}" if p.get("total_line") is not None else "N/A"
    fields = [
        {"name": "🎯 Best Bet — Total", "value": f"**{side} {line}** `{_fmt_price(p['price'])}`", "inline": True},
        {"name": cfg["tip"],        "value": _fmt_tip(p.get("commence_time", "")) or "—", "inline": True},
        {"name": "📚 Book",         "value": (str(p.get("bookmaker")) or "—").upper(),    "inline": True},
        {"name": "📈 Edge",         "value": f"**{p['edge']:+.1%}**",                     "inline": True},
        {"name": "🎯 P(hit)",       "value": f"{p['ou_prob']:.1%}",                       "inline": True},
        {"name": "💰 Kelly Stake",  "value": f"{p['kelly']*100:.1f}% of bankroll",        "inline": True},
        {"name": "🏟️ Matchup",     "value": f"{p['away_team']} @ {p['home_team']}  ·  Pred total: {p['pred_total']:.1f} {cfg['total_unit']}", "inline": False},
    ]
    mf = _market_field(p)
    if mf: fields.insert(-1, mf)
    return fields

def _market_suffix(p) -> str:
    flag = str(p.get("market_flag", "") or "").strip()
    return f"  · 📈 {flag}" if flag else ""

def _ml_compact(p, cfg) -> dict:
    return {"name": "💵 Moneyline Pick", "inline": False, "value": (
        f"**{p['bet_team']}** `{_fmt_price(p['price'])}`  "
        f"Model: {p['prob']:.1%}  Edge: **{p['edge']:+.1%}**  Kelly: {p['kelly']*100:.1f}%"
        f"{_market_suffix(p)}"
    )}

def _ats_compact(p, cfg) -> dict:
    spr = f"{p['spread']:+.1f}" if p.get("spread") is not None else ""
    margin = ""
    if cfg.get("margin_unit") and p.get("pred_home_margin") is not None:
        margin = f"  Pred margin: {p['pred_home_margin']:+.1f} {cfg['margin_unit']}"
    return {"name": cfg["spread_label"], "inline": False, "value": (
        f"**{p['bet_team']} {spr}** `{_fmt_price(p['price'])}`  "
        f"P(cover): {p['cover_prob']:.1%}  Edge: **{p['edge']:+.1%}**{margin}"
        f"{_market_suffix(p)}"
    )}

def _total_compact(p, cfg) -> dict:
    side = "OVER" if p["side"] == "over" else "UNDER"
    line = f"{p['total_line']:.1f}" if p.get("total_line") is not None else "N/A"
    return {"name": "🎯 Totals Pick", "inline": False, "value": (
        f"**{side} {line}** `{_fmt_price(p['price'])}`  "
        f"P(hit): {p['ou_prob']:.1%}  Edge: **{p['edge']:+.1%}**  "
        f"Pred total: {p['pred_total']:.1f} {cfg['total_unit']}"
        f"{_market_suffix(p)}"
    )}

_HEADLINE = {"ml": _ml_headline, "ats": _ats_headline, "total": _total_headline}
_COMPACT  = {"ml": _ml_compact,  "ats": _ats_compact,  "total": _total_compact}

def _team_market_fields(best, ats_best, totals_best, cfg):
    """Return (fields, picks) for the ML/spread/totals trio. The highest-edge
    available pick becomes the headline block; the rest render compactly. Returns
    ([], []) when no market qualifies, signalling a 'No Bet' card."""
    picks = []
    if best:        picks.append(("ml",    best,        float(best["edge"])))
    if ats_best:    picks.append(("ats",   ats_best,    float(ats_best["edge"])))
    if totals_best: picks.append(("total", totals_best, float(totals_best["edge"])))
    if not picks:
        return [], []
    picks.sort(key=lambda x: x[2], reverse=True)
    head_kind, head_pick, _ = picks[0]
    fields = list(_HEADLINE[head_kind](head_pick, cfg))
    for kind, p, _ in picks[1:]:
        fields.append(_COMPACT[kind](p, cfg))
    return fields, picks

def _count_value(df) -> int:
    """Games in a predictions frame that carry at least one value flag, across
    whatever *_value columns it has (home_value/away_value, *_ats_value, over/under_value)."""
    if df is None or df.empty:
        return 0
    vcols = [c for c in df.columns if c.endswith("_value")]
    if not vcols:
        return 0
    return int((df[vcols] == 1).any(axis=1).sum())


# ── Embed builders ────────────────────────────────────────────────────────────

def _get_best_ats(spread_preds: pd.DataFrame, min_edge: float):
    if spread_preds.empty:
        return None
    candidates = []
    for _, g in spread_preds.iterrows():
        for side in ["home", "away"]:
            edge  = float(g.get(f"{side}_ats_edge", 0))
            prob  = float(g.get(f"{side}_cover_prob", 0))
            kelly = float(g.get(f"{side}_ats_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_ats_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005:
                continue
            candidates.append({
                "side":             side,
                "bet_team":         g["home_team"] if side == "home" else g["away_team"],
                "home_team":        g["home_team"],
                "away_team":        g["away_team"],
                "spread":           g.get(f"{side}_point"),
                "pred_home_margin": float(g.get("pred_home_margin", 0)),
                "cover_prob":       prob,
                "edge":             edge,
                "kelly":            kelly,
                "price":            price,
                "commence_time":    g.get("commence_time", ""),
                "bookmaker":        str(g.get("bookmaker", "")),
                "market_flag":      str(g.get("market_flag", "") or ""),
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _get_best_threes_prop(threes_preds: pd.DataFrame, min_edge: float):
    if threes_preds.empty:
        return None
    candidates = []
    for _, g in threes_preds.iterrows():
        for side in ["over", "under"]:
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005 or price is None:
                continue
            candidates.append({
                "side":          side,
                "player_name":   g["player_name"],
                "home_team":     g["home_team"],
                "away_team":     g["away_team"],
                "bookmaker":     str(g.get("bookmaker", "")).upper(),
                "line":          g.get("line"),
                "pred_threes":   float(g.get("pred_threes", 0)),
                "ou_prob":       prob,
                "edge":          edge,
                "kelly":         kelly,
                "price":         price,
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _get_best_stl_prop(stl_preds: pd.DataFrame, min_edge: float):
    if stl_preds.empty:
        return None
    candidates = []
    for _, g in stl_preds.iterrows():
        for side in ["over", "under"]:
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005 or price is None:
                continue
            candidates.append({
                "side":        side,
                "player_name": g["player_name"],
                "home_team":   g["home_team"],
                "away_team":   g["away_team"],
                "bookmaker":   str(g.get("bookmaker", "")).upper(),
                "line":        g.get("line"),
                "pred_stl":    float(g.get("pred_stl", 0)),
                "ou_prob":     prob,
                "edge":        edge,
                "kelly":       kelly,
                "price":       price,
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _get_best_blk_prop(blk_preds: pd.DataFrame, min_edge: float):
    if blk_preds.empty:
        return None
    candidates = []
    for _, g in blk_preds.iterrows():
        for side in ["over", "under"]:
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005 or price is None:
                continue
            candidates.append({
                "side":        side,
                "player_name": g["player_name"],
                "home_team":   g["home_team"],
                "away_team":   g["away_team"],
                "bookmaker":   str(g.get("bookmaker", "")).upper(),
                "line":        g.get("line"),
                "pred_blk":    float(g.get("pred_blk", 0)),
                "ou_prob":     prob,
                "edge":        edge,
                "kelly":       kelly,
                "price":       price,
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _get_best_ast_prop(ast_preds: pd.DataFrame, min_edge: float):
    if ast_preds.empty:
        return None
    candidates = []
    for _, g in ast_preds.iterrows():
        for side in ["over", "under"]:
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005 or price is None:
                continue
            candidates.append({
                "side":         side,
                "player_name":  g["player_name"],
                "home_team":    g["home_team"],
                "away_team":    g["away_team"],
                "bookmaker":    str(g.get("bookmaker", "")).upper(),
                "line":         g.get("line"),
                "pred_ast":     float(g.get("pred_ast", 0)),
                "ou_prob":      prob,
                "edge":         edge,
                "kelly":        kelly,
                "price":        price,
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _get_best_reb_prop(reb_preds: pd.DataFrame, min_edge: float):
    if reb_preds.empty:
        return None
    candidates = []
    for _, g in reb_preds.iterrows():
        for side in ["over", "under"]:
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005 or price is None:
                continue
            candidates.append({
                "side":         side,
                "player_name":  g["player_name"],
                "home_team":    g["home_team"],
                "away_team":    g["away_team"],
                "bookmaker":    str(g.get("bookmaker", "")).upper(),
                "line":         g.get("line"),
                "pred_reb":     float(g.get("pred_reb", 0)),
                "ou_prob":      prob,
                "edge":         edge,
                "kelly":        kelly,
                "price":        price,
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _get_best_prop(props_preds: pd.DataFrame, min_edge: float):
    if props_preds.empty:
        return None
    candidates = []
    for _, g in props_preds.iterrows():
        for side in ["over", "under"]:
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005 or price is None:
                continue
            candidates.append({
                "side":         side,
                "player_name":  g["player_name"],
                "home_team":    g["home_team"],
                "away_team":    g["away_team"],
                "bookmaker":    str(g.get("bookmaker", "")).upper(),
                "line":         g.get("line"),
                "pred_pts":     float(g.get("pred_pts", 0)),
                "ou_prob":      prob,
                "edge":         edge,
                "kelly":        kelly,
                "price":        price,
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _get_best_total(totals_preds: pd.DataFrame, min_edge: float):
    if totals_preds.empty:
        return None
    candidates = []
    for _, g in totals_preds.iterrows():
        for side in ["over", "under"]:
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005 or price is None:
                continue
            candidates.append({
                "side":       side,
                "home_team":  g["home_team"],
                "away_team":  g["away_team"],
                "commence_time": g.get("commence_time", ""),
                "bookmaker":  g.get("bookmaker", ""),
                "total_line": g.get("total_line"),
                "pred_total": float(g.get("pred_total", 0)),
                "ou_prob":    prob,
                "edge":       edge,
                "kelly":      kelly,
                "price":      price,
                "market_flag": str(g.get("market_flag", "") or ""),
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _build_nba_embed(today: str) -> dict:
    preds = _load(NBA_DB,
                  "SELECT * FROM predictions WHERE predict_date=? ORDER BY commence_time",
                  params=(today,))
    spread_preds = _load(NBA_DB,
                         "SELECT * FROM spread_predictions WHERE predict_date=? ORDER BY commence_time",
                         params=(today,))
    totals_preds = _load(NBA_DB,
                         "SELECT * FROM totals_predictions WHERE predict_date=? ORDER BY commence_time",
                         params=(today,))
    props_preds  = _load(NBA_DB,
                         "SELECT * FROM props_predictions WHERE predict_date=? ORDER BY over_edge DESC",
                         params=(today,))
    reb_preds    = _load(NBA_DB,
                         "SELECT * FROM props_reb_predictions WHERE predict_date=? ORDER BY over_edge DESC",
                         params=(today,))
    ast_preds    = _load(NBA_DB,
                         "SELECT * FROM props_ast_predictions WHERE predict_date=? ORDER BY over_edge DESC",
                         params=(today,))
    threes_preds = _load(NBA_DB,
                         "SELECT * FROM props_threes_predictions WHERE predict_date=? ORDER BY over_edge DESC",
                         params=(today,))
    stl_preds    = _load(NBA_DB,
                         "SELECT * FROM props_stl_predictions WHERE predict_date=? ORDER BY over_edge DESC",
                         params=(today,))
    blk_preds    = _load(NBA_DB,
                         "SELECT * FROM props_blk_predictions WHERE predict_date=? ORDER BY over_edge DESC",
                         params=(today,))
    NBA_CFG = {"tip": "⏰ Tip (ET)", "spread_short": "Spread",
               "spread_label": "📐 ATS Pick", "margin_unit": "pts", "total_unit": "pts"}
    best         = _get_best(preds, NBA_MIN_EDGE)
    ats_best     = _get_best_ats(spread_preds, NBA_MIN_EDGE)
    totals_best  = _get_best_total(totals_preds, NBA_MIN_EDGE)
    props_best   = _get_best_prop(props_preds, 0.08)
    reb_best     = _get_best_reb_prop(reb_preds, 0.08)
    ast_best     = _get_best_ast_prop(ast_preds, 0.08)
    threes_best  = _get_best_threes_prop(threes_preds, 0.08)
    stl_best     = _get_best_stl_prop(stl_preds, 0.08)
    blk_best     = _get_best_blk_prop(blk_preds, 0.08)
    val_count = _count_value(preds) + _count_value(spread_preds) + _count_value(totals_preds)
    props_val = int(((props_preds["over_value"]==1)|(props_preds["under_value"]==1)).sum()) \
                if not props_preds.empty else 0
    reb_val   = int(((reb_preds["over_value"]==1)|(reb_preds["under_value"]==1)).sum()) \
                if not reb_preds.empty else 0
    ast_val    = int(((ast_preds["over_value"]==1)|(ast_preds["under_value"]==1)).sum()) \
                 if not ast_preds.empty else 0
    threes_val = int(((threes_preds["over_value"]==1)|(threes_preds["under_value"]==1)).sum()) \
                 if not threes_preds.empty else 0
    stl_val    = int(((stl_preds["over_value"]==1)|(stl_preds["under_value"]==1)).sum()) \
                 if not stl_preds.empty else 0
    blk_val    = int(((blk_preds["over_value"]==1)|(blk_preds["under_value"]==1)).sum()) \
                 if not blk_preds.empty else 0
    game_count = len(preds)

    fields, picks = _team_market_fields(best, ats_best, totals_best, NBA_CFG)
    any_prop = any([props_best, reb_best, ast_best, threes_best, stl_best, blk_best])

    if picks or any_prop:
        if props_best:
            side_label = "OVER" if props_best["side"] == "over" else "UNDER"
            away = props_best["away_team"].split()[-1]
            home = props_best["home_team"].split()[-1]
            fields.append({
                "name": "🎲 Props Pick (Points)",
                "value": (
                    f"**{props_best['player_name']} {side_label} {props_best['line']}** `{_fmt_price(props_best['price'])}`  "
                    f"({away} @ {home})  "
                    f"P(hit): {props_best['ou_prob']:.1%}  "
                    f"Edge: **{props_best['edge']:+.1%}**  "
                    f"Pred: {props_best['pred_pts']:.1f} pts"
                ),
                "inline": False,
            })
        if reb_best:
            side_label = "OVER" if reb_best["side"] == "over" else "UNDER"
            away = reb_best["away_team"].split()[-1]
            home = reb_best["home_team"].split()[-1]
            fields.append({
                "name": "🏀 Props Pick (Rebounds)",
                "value": (
                    f"**{reb_best['player_name']} {side_label} {reb_best['line']}** `{_fmt_price(reb_best['price'])}`  "
                    f"({away} @ {home})  "
                    f"P(hit): {reb_best['ou_prob']:.1%}  "
                    f"Edge: **{reb_best['edge']:+.1%}**  "
                    f"Pred: {reb_best['pred_reb']:.1f} reb"
                ),
                "inline": False,
            })
        if ast_best:
            side_label = "OVER" if ast_best["side"] == "over" else "UNDER"
            away = ast_best["away_team"].split()[-1]
            home = ast_best["home_team"].split()[-1]
            fields.append({
                "name": "🎯 Props Pick (Assists)",
                "value": (
                    f"**{ast_best['player_name']} {side_label} {ast_best['line']}** `{_fmt_price(ast_best['price'])}`  "
                    f"({away} @ {home})  "
                    f"P(hit): {ast_best['ou_prob']:.1%}  "
                    f"Edge: **{ast_best['edge']:+.1%}**  "
                    f"Pred: {ast_best['pred_ast']:.1f} ast"
                ),
                "inline": False,
            })
        if threes_best:
            side_label = "OVER" if threes_best["side"] == "over" else "UNDER"
            away = threes_best["away_team"].split()[-1]
            home = threes_best["home_team"].split()[-1]
            fields.append({
                "name": "3️⃣ Props Pick (3-Pointers)",
                "value": (
                    f"**{threes_best['player_name']} {side_label} {threes_best['line']}** `{_fmt_price(threes_best['price'])}`  "
                    f"({away} @ {home})  "
                    f"P(hit): {threes_best['ou_prob']:.1%}  "
                    f"Edge: **{threes_best['edge']:+.1%}**  "
                    f"Pred: {threes_best['pred_threes']:.1f} 3PM"
                ),
                "inline": False,
            })
        if stl_best:
            side_label = "OVER" if stl_best["side"] == "over" else "UNDER"
            away = stl_best["away_team"].split()[-1]
            home = stl_best["home_team"].split()[-1]
            fields.append({
                "name": "🔒 Props Pick (Steals)",
                "value": (
                    f"**{stl_best['player_name']} {side_label} {stl_best['line']}** `{_fmt_price(stl_best['price'])}`  "
                    f"({away} @ {home})  "
                    f"P(hit): {stl_best['ou_prob']:.1%}  "
                    f"Edge: **{stl_best['edge']:+.1%}**  "
                    f"Pred: {stl_best['pred_stl']:.1f} stl"
                ),
                "inline": False,
            })
        if blk_best:
            side_label = "OVER" if blk_best["side"] == "over" else "UNDER"
            away = blk_best["away_team"].split()[-1]
            home = blk_best["home_team"].split()[-1]
            fields.append({
                "name": "🛡️ Props Pick (Blocks)",
                "value": (
                    f"**{blk_best['player_name']} {side_label} {blk_best['line']}** `{_fmt_price(blk_best['price'])}`  "
                    f"({away} @ {home})  "
                    f"P(hit): {blk_best['ou_prob']:.1%}  "
                    f"Edge: **{blk_best['edge']:+.1%}**  "
                    f"Pred: {blk_best['pred_blk']:.1f} blk"
                ),
                "inline": False,
            })
        return {
            "title":       "🏀 NBA — Best Bet of the Day",
            "color":       NBA_COLOR,
            "description": (
                f"{game_count} games today · **{val_count} value play{'s' if val_count != 1 else ''}**"
                + (f" · {props_val} pts prop{'s' if props_val != 1 else ''}" if props_val else "")
                + (f" · {reb_val} reb prop{'s' if reb_val != 1 else ''}" if reb_val else "")
                + (f" · {ast_val} ast prop{'s' if ast_val != 1 else ''}" if ast_val else "")
                + (f" · {threes_val} 3PM prop{'s' if threes_val != 1 else ''}" if threes_val else "")
                + (f" · {stl_val} stl prop{'s' if stl_val != 1 else ''}" if stl_val else "")
                + (f" · {blk_val} blk prop{'s' if blk_val != 1 else ''}" if blk_val else "")
            ),
            "fields":      fields,
            "footer":      {"text": f"AXIOM Edge · {today}"},
        }
    else:
        msg = ("No NBA predictions yet — run `python odds.py && python predict.py`."
               if preds.empty else
               f"{game_count} games analysed — no strong edge found today. Skip NBA.")
        return {
            "title":       "🏀 NBA — No Bet Today",
            "color":       SKIP_COLOR,
            "description": msg,
            "footer":      {"text": f"AXIOM Edge · {today}"},
        }


def _build_mlb_embed(today: str) -> dict:
    preds = _load(MLB_DB,
                  "SELECT * FROM mlb_predictions WHERE predict_date=? ORDER BY commence_time",
                  params=(today,))
    spread_preds = _load(MLB_DB,
                         "SELECT * FROM mlb_spread_predictions WHERE predict_date=? ORDER BY commence_time",
                         params=(today,))
    totals_preds = _load(MLB_DB,
                         "SELECT * FROM mlb_totals_predictions WHERE predict_date=? ORDER BY commence_time",
                         params=(today,))
    MLB_CFG = {"tip": "⏰ Tip (ET)", "spread_short": "Run Line",
               "spread_label": "📐 Run Line Pick", "margin_unit": "r", "total_unit": "r"}
    best         = _get_best(preds, MLB_MIN_EDGE)
    rl_best      = _get_best_ats(spread_preds, MLB_MIN_EDGE)
    totals_best  = _get_best_total(totals_preds, MLB_MIN_EDGE)
    val_count = _count_value(preds) + _count_value(spread_preds) + _count_value(totals_preds)
    game_count = len(preds)

    fields, picks = _team_market_fields(best, rl_best, totals_best, MLB_CFG)

    if picks:
        # Pitcher matchup (MLB-specific) — shown whenever the ML model produced a pick
        if best:
            hp = best.get("home_pitcher"); ap = best.get("away_pitcher")
            he = best.get("home_era");     ae = best.get("away_era")
            if hp and ap:
                h_str = f"{hp} ({float(he):.2f} ERA)" if he else hp
                a_str = f"{ap} ({float(ae):.2f} ERA)" if ae else ap
                fields.append({"name": "⚾ Pitchers", "value": f"{a_str} vs {h_str}", "inline": False})

        return {
            "title":       "⚾ MLB — Best Bet of the Day",
            "color":       MLB_COLOR,
            "description": f"{game_count} games today · **{val_count} value play{'s' if val_count != 1 else ''} found**",
            "fields":      fields,
            "footer":      {"text": f"AXIOM Edge · {today}"},
        }
    else:
        msg = ("No MLB predictions yet — run `python mlb_pitchers.py && python mlb_odds.py && python mlb_predict.py`."
               if preds.empty else
               f"{game_count} games analysed — no strong edge found today. Skip MLB.")
        return {
            "title":       "⚾ MLB — No Bet Today",
            "color":       SKIP_COLOR,
            "description": msg,
            "footer":      {"text": f"AXIOM Edge · {today}"},
        }


# ── NHL ───────────────────────────────────────────────────────────────────────

def _get_best_nhl_spread(spread_preds: pd.DataFrame, min_edge: float):
    """Best puck-line bet. NHL spread tables use plain column names (home_edge,
    model_home_cover_prob, home_kelly, home_value) rather than the _ats_ prefix
    that the NBA/MLB tables use, so this can't reuse _get_best_ats."""
    if spread_preds.empty:
        return None
    candidates = []
    for _, g in spread_preds.iterrows():
        for side in ["home", "away"]:
            if not g.get(f"{side}_value"):
                continue
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"model_{side}_cover_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            if edge < min_edge or kelly < 0.005:
                continue
            candidates.append({
                "side":          side,
                "bet_team":      g["home_team"] if side == "home" else g["away_team"],
                "home_team":     g["home_team"],
                "away_team":     g["away_team"],
                "spread":        g.get(f"{side}_point"),
                "cover_prob":    prob,
                "edge":          edge,
                "kelly":         kelly,
                "price":         price,
                "commence_time": g.get("commence_time", ""),
                "bookmaker":     str(g.get("bookmaker", "")).upper(),
                "market_flag":   str(g.get("market_flag", "") or ""),
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _build_nhl_embed(today: str) -> dict:
    preds = _load(NHL_DB,
                  "SELECT * FROM nhl_predictions WHERE predict_date=? ORDER BY commence_time",
                  params=(today,))
    spread_preds = _load(NHL_DB,
                         "SELECT * FROM nhl_spread_predictions WHERE predict_date=? ORDER BY commence_time",
                         params=(today,))
    totals_preds = _load(NHL_DB,
                         "SELECT * FROM nhl_totals_predictions WHERE predict_date=? ORDER BY commence_time",
                         params=(today,))
    # NHL totals store the book number as book_line; _get_best_total reads total_line.
    if not totals_preds.empty:
        totals_preds = totals_preds.rename(columns={"book_line": "total_line"})

    NHL_CFG = {"tip": "⏰ Puck (ET)", "spread_short": "Puck Line",
               "spread_label": "📐 Puck Line Pick", "margin_unit": None, "total_unit": "goals"}
    best        = _get_best(preds, NHL_MIN_EDGE)            # ML cols already match
    pl_best     = _get_best_nhl_spread(spread_preds, NHL_MIN_EDGE)
    totals_best = _get_best_total(totals_preds, NHL_MIN_EDGE)
    val_count = _count_value(preds) + _count_value(spread_preds) + _count_value(totals_preds)
    game_count = len(preds)

    fields, picks = _team_market_fields(best, pl_best, totals_best, NHL_CFG)

    if picks:
        return {
            "title":       "🏒 NHL — Best Bet of the Day",
            "color":       NHL_COLOR,
            "description": f"{game_count} games today · **{val_count} value play{'s' if val_count != 1 else ''} found**",
            "fields":      fields,
            "footer":      {"text": f"AXIOM Edge · {today}"},
        }
    else:
        msg = ("No NHL predictions yet — run `python nhl_odds.py && python nhl_predict.py`."
               if preds.empty else
               f"{game_count} games analysed — no strong edge found today. Skip NHL.")
        return {
            "title":       "🏒 NHL — No Bet Today",
            "color":       SKIP_COLOR,
            "description": msg,
            "footer":      {"text": f"AXIOM Edge · {today}"},
        }


# ── Send ──────────────────────────────────────────────────────────────────────

def send_alert() -> bool:
    env         = _load_env()
    webhook_url = env.get("DISCORD_WEBHOOK_URL", "").strip()

    if not webhook_url or webhook_url == "YOUR_WEBHOOK_URL_HERE":
        print("  ⚠  No Discord webhook URL configured.")
        print("     Edit .env and set: DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...")
        return False

    today     = date.today().isoformat()
    date_nice = date.today().strftime("%B %d, %Y")

    payload = {
        "username":   "AXIOM Edge",
        "content":    f"**⚡ AXIOM Edge  ·  Daily Picks  ·  {date_nice}**",
        "embeds":     [_build_nba_embed(today), _build_mlb_embed(today),
                       _build_nhl_embed(today)],
    }

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        webhook_url,
        data=data,
        # A real User-Agent is required: Cloudflare blocks urllib's default
        # "Python-urllib/x.y" UA with HTTP 403 / error 1010 before it reaches Discord.
        headers={
            "Content-Type": "application/json",
            "User-Agent":   "AXIOM-Edge/1.0 (+https://github.com/Dconnors21/axiom_edge)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"  ✓ Discord alert sent (HTTP {resp.status})")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  ✗ Discord returned HTTP {e.code}: {body[:300]}")
        return False
    except Exception as e:
        print(f"  ✗ Discord alert failed: {e}")
        return False


if __name__ == "__main__":
    print("── AXIOM Edge Discord Alert ──────────────────────────────")
    send_alert()
