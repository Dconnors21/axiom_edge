import sys, os
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

import streamlit as st
import pandas as pd
import sqlite3
from datetime import date
from pathlib import Path
from mlb_config import MLB_DB_PATH, MIN_EDGE

_CSS = """
<style>
.block-container{padding-top:0;padding-bottom:2rem;max-width:1600px;padding-left:2rem;padding-right:2rem}
[data-testid="metric-container"]{background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:.875rem 1.25rem}
[data-testid="metric-container"] label{color:#8090a8!important;font-size:11px!important;letter-spacing:.06em;text-transform:uppercase}
[data-testid="stMetricValue"]{color:#f0f2f5!important;font-size:22px!important;font-weight:700!important}
.sh{font-size:11px;font-weight:700;letter-spacing:.1em;color:#8090a8;text-transform:uppercase;margin:1.25rem 0 .75rem;padding-bottom:7px;border-bottom:1px solid #1e2d42}
.game-card{background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:1.25rem 1.5rem;margin-bottom:12px}
.game-card.has-value{border-color:#1a3a1a;border-left:3px solid #22c55e}
.game-card.no-value{border-left:3px solid #1e2d42}
.prob-row{display:flex;align-items:center;padding:8px 0;border-bottom:1px solid #1e2d42;font-size:13px}
.prob-row:last-child{border-bottom:none}
.prob-team{flex:1;color:#c8d0dc}
.prob-team.vt{color:#f0f2f5;font-weight:600}
.prob-model{width:60px;text-align:right;color:#f0f2f5;font-weight:500}
.prob-book{width:60px;text-align:right;color:#8090a8}
.prob-edge{width:70px;text-align:right;font-weight:600}
.prob-line{width:60px;text-align:right;color:#96aec8;font-size:12px}
.ep{color:#22c55e}.en{color:#8090a8}
.vbadge{display:inline-flex;align-items:center;gap:6px;background:#0d2a0d;color:#22c55e;border:1px solid #1a4a1a;border-radius:6px;padding:6px 12px;font-size:12px;font-weight:600;margin-top:12px;margin-right:8px}
.nvbadge{display:inline-flex;align-items:center;gap:6px;color:#7a8fa8;font-size:12px;margin-top:10px;padding:4px 0}
.bar-bg{background:#1e2d42;border-radius:3px;height:5px;flex:1;overflow:hidden}
.bar-fill{height:100%;border-radius:3px}
.best-bet-card{background:linear-gradient(135deg,#0d1f0d 0%,#111a11 100%);border:1px solid #22c55e;border-radius:12px;padding:1.75rem 2rem;margin-bottom:1rem;position:relative;overflow:hidden}
.best-bet-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#22c55e,#4ade80,#22c55e)}
.bb-label{font-size:11px;font-weight:700;letter-spacing:.12em;color:#22c55e;text-transform:uppercase;margin-bottom:12px}
.bb-matchup{font-size:20px;font-weight:700;color:#f0f2f5;letter-spacing:-.3px;margin-bottom:4px}
.bb-meta{font-size:13px;color:#8090a8;margin-bottom:1.25rem}
.bb-pick{display:inline-flex;align-items:center;gap:10px;background:#0a2a0a;border:1px solid #22c55e;border-radius:8px;padding:10px 18px;font-size:16px;font-weight:700;color:#22c55e;margin-bottom:1.25rem}
.stat-pill{display:inline-flex;flex-direction:column;align-items:center;background:#0f1828;border:1px solid #1e2d42;border-radius:8px;padding:10px 16px;min-width:76px}
.stat-pill-val{font-size:17px;font-weight:700;color:#f0f2f5}
.stat-pill-lbl{font-size:10px;color:#7a8fa8;letter-spacing:.06em;text-transform:uppercase;margin-top:2px}
.reasoning-row{display:flex;align-items:flex-start;gap:8px;font-size:12px;color:#8090a8;margin-top:6px}
.reasoning-dot{width:5px;height:5px;border-radius:50%;background:#22c55e;margin-top:5px;flex-shrink:0}
.pitcher-row{display:flex;gap:16px;font-size:12px;color:#8090a8;margin-bottom:12px;flex-wrap:wrap}
.pitcher-pill{background:#0f1828;border:1px solid #1e2d42;border-radius:6px;padding:4px 10px;font-size:12px}
.era-good{color:#22c55e;font-weight:600}
.era-bad{color:#ef4444;font-weight:600}
.era-mid{color:#f59e0b;font-weight:600}
.page-header{background:linear-gradient(135deg,#0d1a2e 0%,#131d2e 60%,#0a1e0a 100%);border:1px solid #1e2d42;border-radius:14px;padding:1.75rem 2rem;margin-bottom:1.5rem}
.ph-tag{display:inline-flex;align-items:center;gap:6px;background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.25);border-radius:20px;padding:4px 12px;font-size:11px;font-weight:700;letter-spacing:.08em;color:#22c55e;text-transform:uppercase;margin-bottom:.875rem}
.ph-title{font-size:28px;font-weight:800;color:#f0f2f5;letter-spacing:-.5px;margin-bottom:4px}
.ph-sub{font-size:14px;color:#8090a8}
.section-header{background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:1rem 1.5rem;margin-bottom:1rem;display:flex;align-items:center;justify-content:space-between}
.sec-title{font-size:15px;font-weight:700;color:#f0f2f5}
.sec-badge{font-size:11px;font-weight:600;letter-spacing:.06em;color:#8090a8;background:#0f1828;border:1px solid #1e2d42;border-radius:6px;padding:3px 10px}
</style>
"""


def _load(query, params=None):
    if not Path(MLB_DB_PATH).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(MLB_DB_PATH)
    try:
        df = pd.read_sql(query, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def _fmt(price):
    try:
        p = int(price)
        return f"+{p}" if p > 0 else str(p)
    except Exception:
        return "N/A"


def _tip_et(commence_time):
    try:
        return pd.to_datetime(commence_time, utc=True)\
                 .tz_convert("America/New_York")\
                 .strftime("%I:%M %p ET").lstrip("0")
    except Exception:
        return str(commence_time)


def _era_class(era):
    try:
        e = float(era)
        if e < 3.00: return "era-good"
        if e < 4.50: return "era-mid"
        return "era-bad"
    except Exception:
        return "era-mid"


def _composite(edge, prob, kelly):
    """Composite score: 40% edge weight + 35% probability conviction + 25% Kelly sizing."""
    return 0.40 * edge + 0.35 * max(0.0, prob - 0.50) + 0.25 * kelly


# ─── Candidate pickers ────────────────────────────────────────────────────────

def _get_best(preds, n=2):
    candidates = []
    for _, game in preds.iterrows():
        for side in ["home", "away"]:
            if not game.get(f"{side}_value"):
                continue
            edge  = float(game.get(f"{side}_edge", 0))
            prob  = float(game.get(f"model_{side}_prob", 0))
            kelly = float(game.get(f"{side}_kelly", 0))
            price = game.get(f"{side}_price")
            if edge < MIN_EDGE or prob < 0.50 or kelly < 0.005:
                continue
            try:   ladder = float(price) <= 250
            except Exception: ladder = False
            score    = _composite(edge, prob, kelly)
            bet_team = game["home_team"] if side == "home" else game["away_team"]
            candidates.append({
                "game": game, "side": side, "bet_team": bet_team,
                "score": score, "edge": edge, "prob": prob, "kelly": kelly,
                "price": price, "ladder": ladder,
                "home_team": game["home_team"], "away_team": game["away_team"],
                "commence_time": game.get("commence_time", ""),
                "bookmaker":     game.get("bookmaker", ""),
                "fair_prob":     float(game.get(f"{side}_fair_prob", 0.5)),
                "home_pitcher":  game.get("home_pitcher", "TBD"),
                "away_pitcher":  game.get("away_pitcher", "TBD"),
                "home_era":      game.get("home_era", 4.20),
                "away_era":      game.get("away_era", 4.20),
            })
    if not candidates:
        return []
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:n]


def _get_best_rl(spread_preds, n=2):
    candidates = []
    for _, g in spread_preds.iterrows():
        for side in ["home", "away"]:
            edge    = float(g.get(f"{side}_ats_edge", 0))
            prob    = float(g.get(f"{side}_cover_prob", 0))
            kelly_v = float(g.get(f"{side}_ats_kelly", 0))
            price   = g.get(f"{side}_price")
            val     = int(g.get(f"{side}_ats_value", 0))
            if val != 1 or edge < MIN_EDGE or kelly_v < 0.005:
                continue
            score = _composite(edge, prob, kelly_v)
            candidates.append({
                "side":          side,
                "bet_team":      g["home_team"] if side == "home" else g["away_team"],
                "home_team":     g["home_team"],
                "away_team":     g["away_team"],
                "commence_time": g.get("commence_time", ""),
                "bookmaker":     g.get("bookmaker", ""),
                "spread":        g.get(f"{side}_point"),
                "home_point":    g.get("home_point"),
                "pred_margin":   float(g.get("pred_home_margin", 0)),
                "cover_prob":    prob,
                "fair_prob":     float(g.get(f"{side}_cover_fair", 0.5)),
                "edge":          edge,
                "kelly":         kelly_v,
                "price":         price,
                "score":         score,
            })
    if not candidates:
        return []
    return sorted(candidates, key=lambda x: x["score"], reverse=True)[:n]


def _get_best_mlb_total(totals_preds, n=2):
    candidates = []
    for _, g in totals_preds.iterrows():
        for side in ["over", "under"]:
            edge    = float(g.get(f"{side}_edge", 0))
            prob    = float(g.get(f"{side}_prob", 0))
            kelly_v = float(g.get(f"{side}_kelly", 0))
            price   = g.get(f"{side}_price")
            val     = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < MIN_EDGE or kelly_v < 0.005:
                continue
            score = _composite(edge, prob, kelly_v)
            candidates.append({
                "side":          side,
                "home_team":     g["home_team"],
                "away_team":     g["away_team"],
                "commence_time": g.get("commence_time", ""),
                "bookmaker":     g.get("bookmaker", ""),
                "total_line":    g.get("total_line"),
                "pred_total":    float(g.get("pred_total", 0)),
                "ou_prob":       prob,
                "fair_prob":     float(g.get(f"{side}_fair", 0.5)),
                "edge":          edge,
                "kelly":         kelly_v,
                "price":         price,
                "score":         score,
            })
    if not candidates:
        return []
    return sorted(candidates, key=lambda x: x["score"], reverse=True)[:n]


# ─── Featured card builders ───────────────────────────────────────────────────

def _ml_card_html(best, rank):
    tip  = _tip_et(best["commence_time"])
    game = best["game"]

    result_html = ""
    if pd.notna(game.get("actual_home_win")):
        actual = int(game["actual_home_win"])
        won    = (best["side"] == "home" and actual == 1) or (best["side"] == "away" and actual == 0)
        rc     = "#22c55e" if won else "#ef4444"
        result_html = f'<span style="font-size:13px;font-weight:700;color:{rc}">{"✓ WIN" if won else "✗ LOSS"}</span>'

    label = "⭐ Best Bet" if rank == 0 else "⭐ 2nd Pick"

    ladder_html = ""
    if best["ladder"]:
        ladder_html = '<span style="display:inline-flex;align-items:center;gap:6px;background:#0d2a0d;border:1px solid #22c55e;border-radius:6px;padding:4px 10px;font-size:11px;font-weight:600;color:#22c55e;margin-top:8px">🪜 Ladder eligible</span>'

    hp  = best.get("home_pitcher", "TBD"); ap  = best.get("away_pitcher", "TBD")
    he  = float(best.get("home_era") or 4.20); ae = float(best.get("away_era") or 4.20)
    hec = _era_class(he); aec = _era_class(ae)

    reasons = [
        f"Model assigns {best['prob']:.1%} win prob vs book's implied {best['fair_prob']:.1%} — {best['edge']:.1%} edge",
        f"Kelly criterion suggests {best['kelly']*100:.1f}% of bankroll — "
        f"{'high' if best['kelly'] > 0.05 else 'moderate' if best['kelly'] > 0.02 else 'small'} confidence sizing",
    ]
    try:
        p = float(best["price"])
        if   p < 0:   reasons.append(f"Favorite at {_fmt(best['price'])} — higher hit rate, ideal for ladder compounding")
        elif p <= 150: reasons.append(f"Slight underdog at {_fmt(best['price'])} — good value with strong model conviction")
        else:          reasons.append(f"Underdog at {_fmt(best['price'])} — model sees significant mispricing")
    except Exception:
        pass

    reason_html = "".join([
        f'<div class="reasoning-row"><div class="reasoning-dot"></div><span>{r}</span></div>'
        for r in reasons
    ])

    return f"""
<div class="best-bet-card">
  <div class="bb-label">{label} &nbsp; {result_html}</div>
  <div class="bb-matchup">{best['away_team']} @ {best['home_team']}</div>
  <div class="bb-meta">Tip: {tip} · {str(best['bookmaker']).upper()}</div>
  <div class="pitcher-row">
    <span class="pitcher-pill">{ap} <span class="{aec}">{ae:.2f} ERA</span></span>
    <span style="color:#7a8fa8;align-self:center">vs</span>
    <span class="pitcher-pill">{hp} <span class="{hec}">{he:.2f} ERA</span></span>
  </div>
  <div class="bb-pick">🎯 {best['bet_team']} &nbsp;{_fmt(best['price'])}</div>
  {ladder_html}
  <div style="display:flex;gap:10px;margin:1.25rem 0;flex-wrap:wrap">
    <div class="stat-pill"><div class="stat-pill-val">{best['prob']:.1%}</div><div class="stat-pill-lbl">Model prob</div></div>
    <div class="stat-pill"><div class="stat-pill-val" style="color:#22c55e">{best['edge']:+.1%}</div><div class="stat-pill-lbl">Edge</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{best['fair_prob']:.1%}</div><div class="stat-pill-lbl">Book implied</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{best['kelly']*100:.1f}%</div><div class="stat-pill-lbl">Kelly stake</div></div>
  </div>
  <div style="border-top:1px solid #1e2d42;padding-top:1rem">
    <div style="font-size:11px;color:#7a8fa8;letter-spacing:.06em;text-transform:uppercase;margin-bottom:8px">Why this pick</div>
    {reason_html}
  </div>
</div>"""


def _rl_card_html(best, rank):
    tip        = _tip_et(best["commence_time"])
    spread_str = f"{best['spread']:+.1f}" if best["spread"] is not None else "N/A"
    label      = "⭐ Best Run Line" if rank == 0 else "⭐ 2nd Run Line"
    color      = "#22c55e"

    return f"""
<div class="best-bet-card">
  <div class="bb-label" style="color:{color}">{label}</div>
  <div class="bb-matchup">{best['away_team']} @ {best['home_team']}</div>
  <div class="bb-meta">Tip: {tip} · {str(best['bookmaker']).upper()}</div>
  <div class="bb-pick" style="color:{color}">🎯 {best['bet_team']} &nbsp;{spread_str} &nbsp;({_fmt(best['price'])})</div>
  <div style="display:flex;gap:10px;margin:1.25rem 0;flex-wrap:wrap">
    <div class="stat-pill"><div class="stat-pill-val">{best['cover_prob']:.1%}</div><div class="stat-pill-lbl">P(cover)</div></div>
    <div class="stat-pill"><div class="stat-pill-val" style="color:{color}">{best['edge']:+.1%}</div><div class="stat-pill-lbl">RL edge</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{best['fair_prob']:.1%}</div><div class="stat-pill-lbl">Book implied</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{best['pred_margin']:+.1f}r</div><div class="stat-pill-lbl">Pred margin</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{best['kelly']*100:.1f}%</div><div class="stat-pill-lbl">Kelly stake</div></div>
  </div>
  <div style="border-top:1px solid #1e2d42;padding-top:.8rem;font-size:12px;color:#8090a8">
    Model predicts {best['home_team']} wins by <b style="color:#f0f2f5">{best['pred_margin']:+.1f}</b> runs &nbsp;·&nbsp;
    Run line: {best['home_team']} {f"{best['home_point']:+.1f}" if best['home_point'] is not None else "N/A"}
  </div>
</div>"""


def _totals_card_html(best, rank):
    tip        = _tip_et(best["commence_time"])
    color      = "#f59e0b"
    side_label = "OVER" if best["side"] == "over" else "UNDER"
    line_str   = f"{best['total_line']:.1f}" if best["total_line"] is not None else "N/A"
    label      = "⭐ Best Total" if rank == 0 else "⭐ 2nd Total"

    return f"""
<div class="best-bet-card" style="background:linear-gradient(135deg,#1f1200 0%,#1a1108 100%);border-color:{color}">
  <div class="bb-label" style="color:{color}">{label}</div>
  <div class="bb-matchup">{best['away_team']} @ {best['home_team']}</div>
  <div class="bb-meta">Tip: {tip} · {str(best['bookmaker']).upper()}</div>
  <div class="bb-pick" style="color:{color};background:#1a0e00;border-color:{color}">{side_label} {line_str} &nbsp;({_fmt(best['price'])})</div>
  <div style="display:flex;gap:10px;margin:1.25rem 0;flex-wrap:wrap">
    <div class="stat-pill"><div class="stat-pill-val">{best['ou_prob']:.1%}</div><div class="stat-pill-lbl">P({side_label.lower()})</div></div>
    <div class="stat-pill"><div class="stat-pill-val" style="color:{color}">{best['edge']:+.1%}</div><div class="stat-pill-lbl">Edge</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{best['fair_prob']:.1%}</div><div class="stat-pill-lbl">Book implied</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{best['pred_total']:.1f}r</div><div class="stat-pill-lbl">Pred total</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{best['kelly']*100:.1f}%</div><div class="stat-pill-lbl">Kelly stake</div></div>
  </div>
  <div style="border-top:1px solid #1e2d42;padding-top:.8rem;font-size:12px;color:#8090a8">
    Model predicts <b style="color:#f0f2f5">{best['pred_total']:.1f}</b> total runs &nbsp;·&nbsp;
    Line: <b style="color:#f0f2f5">{line_str}</b>
  </div>
</div>"""


# ─── Game-row renderers ───────────────────────────────────────────────────────

def _game_rows_ml(preds):
    for _, game in preds.iterrows():
        home = game["home_team"]; away = game["away_team"]
        hv   = int(game.get("home_value", 0)) == 1
        av   = int(game.get("away_value", 0)) == 1
        has_val = hv or av

        tip = _tip_et(game["commence_time"])
        hp  = game.get("home_pitcher", "TBD"); ap  = game.get("away_pitcher", "TBD")
        he  = float(game.get("home_era") or 4.20); ae = float(game.get("away_era") or 4.20)
        hec = _era_class(he); aec = _era_class(ae)
        hm  = float(game.get("model_home_prob", 0.5)); am = float(game.get("model_away_prob", 0.5))
        hf  = float(game.get("home_fair_prob", 0.5));  af = float(game.get("away_fair_prob", 0.5))
        he_ = float(game.get("home_edge", 0));         ae_ = float(game.get("away_edge", 0))
        hpr = game.get("home_price");                  apr = game.get("away_price")
        hk  = float(game.get("home_kelly", 0));        ak  = float(game.get("away_kelly", 0))

        rh = ""
        if pd.notna(game.get("actual_home_win")):
            actual = int(game["actual_home_win"])
            if hv:
                c  = "#22c55e" if actual == 1 else "#ef4444"
                rh = f'<span style="color:{c};font-weight:600;font-size:13px">{"✓ W" if actual==1 else "✗ L"}</span>'
            elif av:
                c  = "#22c55e" if actual == 0 else "#ef4444"
                rh = f'<span style="color:{c};font-weight:600;font-size:13px">{"✓ W" if actual==0 else "✗ L"}</span>'

        bdg = ""
        if hv:      bdg += f'<span class="vbadge">VALUE {home} | {he_:+.1%} edge | Kelly {hk*100:.1f}% | {_fmt(hpr)}</span>'
        if av:      bdg += f'<span class="vbadge">VALUE {away} | {ae_:+.1%} edge | Kelly {ak*100:.1f}% | {_fmt(apr)}</span>'
        if not has_val: bdg = '<span class="nvbadge">No edge — skip</span>'

        hb  = int(hm * 100); ab = int(am * 100)
        cc  = "game-card has-value" if has_val else "game-card no-value"
        hc  = "vt" if hv else ""; ac = "vt" if av else ""
        hec_ = "ep" if he_ > MIN_EDGE else "en"; aec_ = "ep" if ae_ > MIN_EDGE else "en"

        st.markdown(f"""
<div class="{cc}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <p style="font-size:16px;font-weight:600;color:#f0f2f5;margin:0 0 2px">{away} <span style="color:#7a8fa8;font-weight:400">@</span> {home}</p>
      <p style="font-size:12px;color:#8090a8;margin:0 0 4px">Tip: {tip} · {str(game.get('bookmaker','')).upper()}</p>
      <p style="font-size:12px;color:#7a8fa8;margin:0 0 1rem">
        <span class="{aec}">{ap} ({ae:.2f})</span>
        <span style="color:#1e2d42"> vs </span>
        <span class="{hec}">{hp} ({he:.2f})</span>
      </p>
    </div><div>{rh}</div>
  </div>
  <div style="display:flex;padding:6px 0 4px;border-bottom:1px solid #1e2d42;font-size:11px;color:#7a8fa8;letter-spacing:.04em;text-transform:uppercase">
    <div style="flex:1">Team</div>
    <div style="width:60px;text-align:right">Model</div>
    <div style="width:60px;text-align:right">Book</div>
    <div style="width:70px;text-align:right">Edge</div>
    <div style="width:60px;text-align:right">Line</div>
  </div>
  <div class="prob-row"><div class="prob-team {hc}">{home}</div><div class="prob-model">{hm:.1%}</div><div class="prob-book">{hf:.1%}</div><div class="prob-edge {hec_}">{he_:+.1%}</div><div class="prob-line">{_fmt(hpr)}</div></div>
  <div class="prob-row" style="margin-bottom:4px"><div class="prob-team {ac}">{away}</div><div class="prob-model">{am:.1%}</div><div class="prob-book">{af:.1%}</div><div class="prob-edge {aec_}">{ae_:+.1%}</div><div class="prob-line">{_fmt(apr)}</div></div>
  <div style="display:flex;gap:8px;align-items:center;margin:10px 0 6px">
    <div style="font-size:11px;color:#7a8fa8;width:32px">{away[:3].upper()}</div>
    <div class="bar-bg"><div class="bar-fill" style="width:{ab}%;background:#4f8ef7"></div></div>
    <div style="font-size:11px;color:#7a8fa8;text-align:center;width:44px">{ab}%/{hb}%</div>
    <div class="bar-bg"><div class="bar-fill" style="width:{hb}%;background:#22c55e"></div></div>
    <div style="font-size:11px;color:#7a8fa8;width:32px;text-align:right">{home[:3].upper()}</div>
  </div>
  {bdg}
</div>""", unsafe_allow_html=True)


def _game_rows_rl(spread_preds):
    rows_html = ""
    for _, g in spread_preds.iterrows():
        home    = g["home_team"]; away = g["away_team"]
        home_pt = g.get("home_point"); away_pt = g.get("away_point")
        pred_m  = float(g.get("pred_home_margin", 0))
        hcp     = float(g.get("home_cover_prob", 0.5))
        acp     = float(g.get("away_cover_prob", 0.5))
        he      = float(g.get("home_ats_edge", 0))
        ae      = float(g.get("away_ats_edge", 0))
        hv      = int(g.get("home_ats_value", 0))
        av      = int(g.get("away_ats_value", 0))

        home_spr = f"{home_pt:+.1f}" if home_pt is not None else "—"
        away_spr = f"{away_pt:+.1f}" if away_pt is not None else "—"
        h_ec = "ep" if he > MIN_EDGE else "en"
        a_ec = "ep" if ae > MIN_EDGE else "en"

        badge = ""
        if hv:  badge = f'<span class="vbadge">VALUE {home} {home_spr} | {he:+.1%}</span>'
        elif av: badge = f'<span class="vbadge">VALUE {away} {away_spr} | {ae:+.1%}</span>'

        rows_html += f"""
<div class="game-card {'has-value' if (hv or av) else 'no-value'}" style="padding:1rem 1.25rem">
  <div style="font-size:14px;font-weight:600;color:#f0f2f5;margin-bottom:4px">{away} @ {home}</div>
  <div style="font-size:11px;color:#8090a8;margin-bottom:.75rem">
    Pred margin: <b style="color:#f0f2f5">{pred_m:+.1f}r</b> &nbsp;·&nbsp;
    {home} {home_spr} / {away} {away_spr}
  </div>
  <div style="display:flex;padding:4px 0;font-size:11px;color:#7a8fa8;letter-spacing:.04em;text-transform:uppercase;border-bottom:1px solid #1e2d42">
    <div style="flex:1">Team</div><div style="width:55px;text-align:right">Line</div>
    <div style="width:65px;text-align:right">P(cover)</div><div style="width:65px;text-align:right">Edge</div>
  </div>
  <div class="prob-row"><div class="prob-team {'vt' if hv else ''}">{home}</div>
    <div class="prob-book">{home_spr}</div><div class="prob-model">{hcp:.1%}</div>
    <div class="prob-edge {h_ec}">{he:+.1%}</div></div>
  <div class="prob-row"><div class="prob-team {'vt' if av else ''}">{away}</div>
    <div class="prob-book">{away_spr}</div><div class="prob-model">{acp:.1%}</div>
    <div class="prob-edge {a_ec}">{ae:+.1%}</div></div>
  {badge}
</div>"""

    if rows_html:
        st.markdown(rows_html, unsafe_allow_html=True)


def _game_rows_totals(totals_preds):
    rows_html = ""
    for _, g in totals_preds.iterrows():
        home    = g["home_team"]; away = g["away_team"]
        line    = g.get("total_line")
        pred_t  = float(g.get("pred_total", 0))
        over_p  = float(g.get("over_prob", 0.5))
        under_p = float(g.get("under_prob", 0.5))
        over_e  = float(g.get("over_edge", 0))
        under_e = float(g.get("under_edge", 0))
        ov      = int(g.get("over_value", 0))
        uv      = int(g.get("under_value", 0))

        line_str = f"{line:.1f}" if line is not None else "—"
        over_ec  = "ep" if over_e  > MIN_EDGE else "en"
        under_ec = "ep" if under_e > MIN_EDGE else "en"

        badge = ""
        if ov:   badge = f'<span class="vbadge" style="background:#f59e0b20;color:#f59e0b;border-color:#f59e0b50">OVER {line_str} | {over_e:+.1%}</span>'
        elif uv: badge = f'<span class="vbadge" style="background:#f59e0b20;color:#f59e0b;border-color:#f59e0b50">UNDER {line_str} | {under_e:+.1%}</span>'

        rows_html += f"""
<div class="game-card {'has-value' if (ov or uv) else 'no-value'}" style="padding:1rem 1.25rem">
  <div style="font-size:14px;font-weight:600;color:#f0f2f5;margin-bottom:4px">{away} @ {home}</div>
  <div style="font-size:11px;color:#8090a8;margin-bottom:.75rem">
    Pred total: <b style="color:#f0f2f5">{pred_t:.1f}r</b> &nbsp;·&nbsp; Line: <b style="color:#f0f2f5">{line_str}</b>
  </div>
  <div style="display:flex;padding:4px 0;font-size:11px;color:#7a8fa8;letter-spacing:.04em;text-transform:uppercase;border-bottom:1px solid #1e2d42">
    <div style="flex:1">Side</div>
    <div style="width:65px;text-align:right">P(hit)</div>
    <div style="width:65px;text-align:right">Edge</div>
  </div>
  <div class="prob-row"><div class="prob-team {'vt' if ov else ''}">OVER {line_str}</div>
    <div class="prob-model">{over_p:.1%}</div>
    <div class="prob-edge {over_ec}">{over_e:+.1%}</div>
  </div>
  <div class="prob-row"><div class="prob-team {'vt' if uv else ''}">UNDER {line_str}</div>
    <div class="prob-model">{under_p:.1%}</div>
    <div class="prob-edge {under_ec}">{under_e:+.1%}</div>
  </div>
  {badge}
</div>"""

    if rows_html:
        st.markdown(rows_html, unsafe_allow_html=True)


# ─── Section renderers ────────────────────────────────────────────────────────

def _render_run_line_section(today: str):
    spread_preds = _load(
        "SELECT * FROM mlb_spread_predictions WHERE predict_date=? ORDER BY commence_time",
        params=(today,)
    )
    st.markdown("<div class='sh'>📐 Run Line (ATS)</div>", unsafe_allow_html=True)

    if spread_preds.empty:
        st.info("No run line predictions yet. Run `python mlb_spread_predict.py` to generate them.")
        return

    # Stats strip
    rl_val = spread_preds[
        (spread_preds.get("home_ats_value", pd.Series(dtype=int)) == 1) |
        (spread_preds.get("away_ats_value", pd.Series(dtype=int)) == 1)
    ] if not spread_preds.empty else pd.DataFrame()
    try:
        best_rl_edge = max(spread_preds["home_ats_edge"].max(), spread_preds["away_ats_edge"].max())
    except Exception:
        best_rl_edge = 0.0
    c1, c2, c3 = st.columns(3)
    c1.metric("RL games", len(spread_preds))
    c2.metric("RL value bets", len(rl_val))
    c3.metric("Best RL edge", f"{best_rl_edge:.1%}")

    top_picks = _get_best_rl(spread_preds, n=2)

    if top_picks:
        if len(top_picks) == 2:
            col1, col2 = st.columns(2)
            with col1: st.markdown(_rl_card_html(top_picks[0], 0), unsafe_allow_html=True)
            with col2: st.markdown(_rl_card_html(top_picks[1], 1), unsafe_allow_html=True)
        else:
            st.markdown(_rl_card_html(top_picks[0], 0), unsafe_allow_html=True)
    else:
        st.markdown(
            '<div style="color:#96aec8;font-size:13px;font-style:italic;padding:.75rem 0">'
            'No run line value today — all lines appear fairly priced.</div>',
            unsafe_allow_html=True
        )

    n_rest = len(spread_preds)
    with st.expander(f"All run line games ({n_rest})"):
        _game_rows_rl(spread_preds)


def _render_totals_section(today: str):
    totals_preds = _load(
        "SELECT * FROM mlb_totals_predictions WHERE predict_date=? ORDER BY commence_time",
        params=(today,)
    )
    st.markdown("<div class='sh'>🎯 Totals — Over/Under</div>", unsafe_allow_html=True)

    if totals_preds.empty:
        st.info("No totals predictions yet. Run `python mlb_totals_predict.py` to generate them.")
        return

    # Stats strip
    tot_val = totals_preds[
        (totals_preds.get("over_value", pd.Series(dtype=int)) == 1) |
        (totals_preds.get("under_value", pd.Series(dtype=int)) == 1)
    ] if not totals_preds.empty else pd.DataFrame()
    try:
        best_tot_edge = max(totals_preds["over_edge"].max(), totals_preds["under_edge"].max())
    except Exception:
        best_tot_edge = 0.0
    c1, c2, c3 = st.columns(3)
    c1.metric("Totals games", len(totals_preds))
    c2.metric("Totals value bets", len(tot_val))
    c3.metric("Best totals edge", f"{best_tot_edge:.1%}")

    top_picks = _get_best_mlb_total(totals_preds, n=2)

    if top_picks:
        if len(top_picks) == 2:
            col1, col2 = st.columns(2)
            with col1: st.markdown(_totals_card_html(top_picks[0], 0), unsafe_allow_html=True)
            with col2: st.markdown(_totals_card_html(top_picks[1], 1), unsafe_allow_html=True)
        else:
            st.markdown(_totals_card_html(top_picks[0], 0), unsafe_allow_html=True)
    else:
        st.markdown(
            '<div style="color:#96aec8;font-size:13px;font-style:italic;padding:.75rem 0">'
            'No totals value today — all lines appear fairly priced.</div>',
            unsafe_allow_html=True
        )

    n_rest = len(totals_preds)
    with st.expander(f"All totals games ({n_rest})"):
        _game_rows_totals(totals_preds)


# ─── Main render ──────────────────────────────────────────────────────────────

def render():
    st.markdown(_CSS, unsafe_allow_html=True)

    today = date.today().isoformat()
    preds = _load(
        "SELECT * FROM mlb_predictions WHERE predict_date=? ORDER BY commence_time",
        params=(today,)
    )

    # Page header
    today_display = date.today().strftime("%A, %B %d, %Y")
    st.markdown(f"""
<div class="page-header">
  <div class="ph-tag">⚾ Live Analysis</div>
  <div class="ph-title">MLB Picks</div>
  <div class="ph-sub">{today_display} · Model-driven value bets across moneyline, run line &amp; totals</div>
</div>
""", unsafe_allow_html=True)

    if preds.empty:
        st.info("No MLB predictions yet. Run `python mlb_pitchers.py && python mlb_odds.py && python mlb_predict.py`")
        _render_run_line_section(today)
        _render_totals_section(today)
        return

    # Stats strip
    val_games  = preds[(preds["home_value"] == 1) | (preds["away_value"] == 1)]
    best_edge  = max(preds["home_edge"].max(), preds["away_edge"].max())
    results_in = preds["actual_home_win"].notna().sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Games today",    len(preds))
    c2.metric("Value bets",     len(val_games))
    c3.metric("Best edge",      f"{best_edge:.1%}")
    c4.metric("Results in",     f"{results_in} / {len(preds)}")

    # ── Moneyline section ──────────────────────────────────────────────────────
    st.markdown("<div class='sh'>⚾ Moneyline — Best Bets</div>", unsafe_allow_html=True)

    top_picks = _get_best(preds, n=2)

    if top_picks:
        if len(top_picks) == 2:
            col1, col2 = st.columns(2)
            with col1: st.markdown(_ml_card_html(top_picks[0], 0), unsafe_allow_html=True)
            with col2: st.markdown(_ml_card_html(top_picks[1], 1), unsafe_allow_html=True)
        else:
            st.markdown(_ml_card_html(top_picks[0], 0), unsafe_allow_html=True)
    else:
        st.markdown(
            '<div style="color:#96aec8;font-size:13px;font-style:italic;padding:.75rem 0">'
            'No ML edge today — all moneylines appear fairly priced.</div>',
            unsafe_allow_html=True
        )

    with st.expander(f"All moneyline games ({len(preds)})"):
        _game_rows_ml(preds)

    _render_run_line_section(today)
    _render_totals_section(today)
