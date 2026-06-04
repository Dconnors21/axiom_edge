import sys, os
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

import streamlit as st
import pandas as pd
import sqlite3
from datetime import date
from pathlib import Path
from config import DB_PATH, MIN_EDGE

_CSS = """
<style>
/* ── layout ──────────────────────────────────────────────────────────────── */
.block-container { padding-top: 0; padding-bottom: 3rem; max-width: 1600px; padding-left: 2rem; padding-right: 2rem }

/* ── metrics strip ───────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: #131d2e !important; border: 1px solid #1e2d42 !important;
    border-radius: 8px !important; padding: .875rem 1.25rem !important;
}
[data-testid="metric-container"] label {
    color: #8090a8 !important; font-size: 11px !important;
    letter-spacing: .05em; text-transform: uppercase;
}
[data-testid="stMetricValue"] {
    color: #f0f2f5 !important; font-size: 22px !important; font-weight: 700 !important;
}

/* ── section header ──────────────────────────────────────────────────────── */
.ax-sh {
    font-size: 11px; font-weight: 700; letter-spacing: .1em; color: #8090a8;
    text-transform: uppercase; margin: 1.25rem 0 .75rem; padding-bottom: 7px;
    border-bottom: 1px solid #1e2d42;
}

/* ── featured pick card ──────────────────────────────────────────────────── */
.pick-card {
    background: #131d2e; border: 1px solid #1e2d42; border-left: 3px solid #3b82f6;
    border-radius: 10px; padding: 1.25rem 1.5rem; margin-bottom: 12px;
}
.pick-card.lean { border-left-color: #1e2d42; }

.pc-tier {
    font-size: 10px; font-weight: 700; letter-spacing: .1em; color: #3b82f6;
    text-transform: uppercase; margin-bottom: 10px;
}
.pc-tier.lean { color: #7a8fa8; }
.pc-matchup {
    font-size: 18px; font-weight: 700; color: #f0f2f5;
    letter-spacing: -.2px; margin-bottom: 3px;
}
.pc-meta { font-size: 12px; color: #8090a8; margin-bottom: .875rem; }
.pc-pick {
    display: inline-flex; align-items: center; gap: 8px;
    background: #0e1e3a; border: 1px solid #1e3a6e; border-radius: 7px;
    padding: 8px 16px; font-size: 15px; font-weight: 700; color: #60a5fa;
    margin-bottom: .875rem;
}
.pc-pick.lean {
    background: #0f1828; border-color: #1e2d42; color: #96aec8;
}

/* ── stat pills ──────────────────────────────────────────────────────────── */
.sp-wrap { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: .25rem; }
.sp {
    display: inline-flex; flex-direction: column; align-items: center;
    background: #0f1828; border: 1px solid #1e2d42; border-radius: 7px;
    padding: 7px 12px; min-width: 64px;
}
.sp-val { font-size: 14px; font-weight: 700; color: #f0f2f5; }
.sp-lbl {
    font-size: 10px; color: #7a8fa8; letter-spacing: .05em;
    text-transform: uppercase; margin-top: 2px;
}

/* ── game rows (expander) ────────────────────────────────────────────────── */
.gr-wrap {
    background: #131d2e; border: 1px solid #1e2d42; border-radius: 10px;
    overflow: hidden; margin-bottom: 8px;
}
.gr {
    display: flex; align-items: center; justify-content: space-between;
    padding: 9px 14px; border-bottom: 1px solid #1e2d42; font-size: 13px;
}
.gr:last-child { border-bottom: none; }
.gr-tm { color: #96aec8; flex: 1; }
.gr-tm b { color: #f0f2f5; }
.gr-tip { font-size: 11px; color: #7a8fa8; width: 72px; text-align: center; }
.gr-badge { font-size: 11px; font-weight: 600; text-align: right; min-width: 130px; }

/* ── prop rows (expander) ────────────────────────────────────────────────── */
.prop-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 9px 14px; border-bottom: 1px solid #1e2d42; font-size: 13px;
}
.prop-row:last-child { border-bottom: none; }

/* ── value / lean badges ─────────────────────────────────────────────────── */
.badge-val {
    display: inline-block; background: #022c22; color: #10b981;
    border: 1px solid #065f46; border-radius: 4px;
    font-size: 10px; font-weight: 700; padding: 2px 7px; letter-spacing: .04em;
}
.badge-lean {
    display: inline-block; background: #0f1828; color: #7a8fa8;
    border: 1px solid #1e2d42; border-radius: 4px;
    font-size: 10px; font-weight: 700; padding: 2px 7px; letter-spacing: .04em;
}

/* ── props sub-header ────────────────────────────────────────────────────── */
.props-hdr {
    font-size: 12px; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; margin: 1.25rem 0 .75rem;
    padding-left: 10px; border-left: 3px solid currentColor; display: block;
}

/* ── page title ──────────────────────────────────────────────────────────── */
.picks-title { font-size: 22px; font-weight: 700; color: #f0f2f5; margin-bottom: 2px; }
.picks-date  { font-size: 13px; color: #8090a8; margin-bottom: 1.25rem; }
</style>
"""

# ── helpers ───────────────────────────────────────────────────────────────────

def _load(query, params=None):
    if not Path(DB_PATH).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
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
        return (pd.to_datetime(commence_time, utc=True)
                  .tz_convert("America/New_York")
                  .strftime("%I:%M %p ET").lstrip("0"))
    except Exception:
        return str(commence_time)

def _composite(edge, prob, kelly):
    """Composite score: 40% edge + 35% prob-above-50 + 25% kelly."""
    return 0.40 * edge + 0.35 * max(0.0, prob - 0.5) + 0.25 * kelly


# ── PROP_CONFIGS ──────────────────────────────────────────────────────────────

PROP_CONFIGS = {
    "pts": {
        "table":      "props_predictions",
        "pred_col":   "pred_pts",
        "actual_col": "actual_pts",
        "label":      "Points",
        "unit":       "pts",
        "color":      "#3b82f6",
        "icon":       "🎲",
        "min_edge":   0.08,
    },
    "reb": {
        "table":      "props_reb_predictions",
        "pred_col":   "pred_reb",
        "actual_col": "actual_reb",
        "label":      "Rebounds",
        "unit":       "reb",
        "color":      "#8b5cf6",
        "icon":       "🏀",
        "min_edge":   0.12,
    },
    "ast": {
        "table":      "props_ast_predictions",
        "pred_col":   "pred_ast",
        "actual_col": "actual_ast",
        "label":      "Assists",
        "unit":       "ast",
        "color":      "#f97316",
        "icon":       "🎯",
        "min_edge":   0.12,
    },
    "threes": {
        "table":      "props_threes_predictions",
        "pred_col":   "pred_threes",
        "actual_col": "actual_threes",
        "label":      "3-Pointers",
        "unit":       "3PM",
        "color":      "#06b6d4",
        "icon":       "3️⃣",
        "min_edge":   0.12,
    },
    "stl": {
        "table":      "props_stl_predictions",
        "pred_col":   "pred_stl",
        "actual_col": "actual_stl",
        "label":      "Steals",
        "unit":       "stl",
        "color":      "#10b981",
        "icon":       "🔒",
        "min_edge":   0.12,
    },
    "blk": {
        "table":      "props_blk_predictions",
        "pred_col":   "pred_blk",
        "actual_col": "actual_blk",
        "label":      "Blocks",
        "unit":       "blk",
        "color":      "#eab308",
        "icon":       "🛡️",
        "min_edge":   0.12,
    },
}


# ── moneyline ─────────────────────────────────────────────────────────────────

def _get_top_ml_picks(preds, n=2):
    """Return top-N ML picks by composite score (value bets preferred, fills with leans)."""
    value_cands, lean_cands = [], []
    for _, game in preds.iterrows():
        for side in ["home", "away"]:
            edge  = float(game.get(f"{side}_edge", 0))
            prob  = float(game.get(f"model_{side}_prob", 0))
            kelly = float(game.get(f"{side}_kelly", 0))
            price = game.get(f"{side}_price")
            val   = int(game.get(f"{side}_value", 0))
            if prob < 0.50:
                continue
            score    = _composite(edge, prob, kelly)
            bet_team = game["home_team"] if side == "home" else game["away_team"]
            entry = {
                "game":         game,
                "side":         side,
                "bet_team":     bet_team,
                "score":        score,
                "edge":         edge,
                "prob":         prob,
                "kelly":        kelly,
                "price":        price,
                "home_team":    game["home_team"],
                "away_team":    game["away_team"],
                "commence_time":game.get("commence_time", ""),
                "bookmaker":    game.get("bookmaker", ""),
                "fair_prob":    float(game.get(f"{side}_fair_prob", 0.5)),
            }
            if val == 1 and edge >= MIN_EDGE and kelly >= 0.005:
                entry["tier"] = "VALUE BET"
                value_cands.append(entry)
            else:
                entry["tier"] = "MODEL LEAN"
                lean_cands.append(entry)
    value_cands.sort(key=lambda x: x["score"], reverse=True)
    lean_cands.sort(key=lambda x: x["score"], reverse=True)
    result = value_cands[:n]
    if len(result) < n:
        result += lean_cands[:n - len(result)]
    return result[:n]


def _render_ml_pick_card(pick):
    is_value  = pick["tier"] == "VALUE BET"
    card_cls  = "pick-card"        if is_value else "pick-card lean"
    tier_cls  = "pc-tier"          if is_value else "pc-tier lean"
    pick_cls  = "pc-pick"          if is_value else "pc-pick lean"
    tier_icon = "⭐"               if is_value else "◆"

    result_html = ""
    game = pick["game"]
    if pd.notna(game.get("actual_home_win")):
        actual = int(game["actual_home_win"])
        won = (pick["side"] == "home" and actual == 1) or (pick["side"] == "away" and actual == 0)
        c = "#10b981" if won else "#ef4444"
        result_html = f' &nbsp;<span style="font-size:13px;font-weight:700;color:{c}">{"✓ WIN" if won else "✗ LOSS"}</span>'

    edge_c = "#10b981" if (is_value and pick["edge"] > 0) else "#7a8fa8"
    tip    = _tip_et(pick["commence_time"])

    st.markdown(f"""
<div class="{card_cls}">
  <div class="{tier_cls}">{tier_icon} {pick['tier']}{result_html}</div>
  <div class="pc-matchup">{pick['away_team']} @ {pick['home_team']}</div>
  <div class="pc-meta">Tip {tip} &nbsp;·&nbsp; {str(pick['bookmaker']).upper()}</div>
  <div class="{pick_cls}">🎯 {pick['bet_team']} &nbsp;{_fmt(pick['price'])}</div>
  <div class="sp-wrap">
    <div class="sp"><div class="sp-val">{pick['prob']:.1%}</div><div class="sp-lbl">Model</div></div>
    <div class="sp"><div class="sp-val" style="color:{edge_c}">{pick['edge']:+.1%}</div><div class="sp-lbl">Edge</div></div>
    <div class="sp"><div class="sp-val">{pick['fair_prob']:.1%}</div><div class="sp-lbl">Book</div></div>
    <div class="sp"><div class="sp-val">{pick['kelly']*100:.1f}%</div><div class="sp-lbl">Kelly</div></div>
  </div>
</div>""", unsafe_allow_html=True)


def _render_ml_section(today: str):
    preds = _load(
        "SELECT * FROM predictions WHERE predict_date=? ORDER BY commence_time",
        params=(today,)
    )
    st.markdown("<div class='ax-sh'>Moneyline</div>", unsafe_allow_html=True)

    if preds.empty:
        st.info("No predictions yet. Run `python odds.py` then `python predict.py`.")
        return

    top = _get_top_ml_picks(preds, n=2)

    if top:
        if len(top) == 2:
            c1, c2 = st.columns(2)
            with c1: _render_ml_pick_card(top[0])
            with c2: _render_ml_pick_card(top[1])
        else:
            _render_ml_pick_card(top[0])
    else:
        st.markdown(
            "<div style='color:#7a8fa8;font-size:13px;padding:.75rem 0'>No picks today.</div>",
            unsafe_allow_html=True
        )

    with st.expander(f"All {len(preds)} games today"):
        rows_html = "<div class='gr-wrap'>"
        for _, g in preds.iterrows():
            home = g["home_team"]; away = g["away_team"]
            hv   = int(g.get("home_value", 0))
            av   = int(g.get("away_value", 0))
            he   = float(g.get("home_edge", 0))
            ae   = float(g.get("away_edge", 0))
            hp   = float(g.get("model_home_prob", 0.5))
            ap   = float(g.get("model_away_prob", 0.5))
            hpr  = g.get("home_price")
            apr  = g.get("away_price")
            tip  = _tip_et(g["commence_time"])

            result_html = ""
            if pd.notna(g.get("actual_home_win")):
                actual = int(g["actual_home_win"])
                if hv:
                    c = "#10b981" if actual == 1 else "#ef4444"
                    result_html = f' <span style="color:{c};font-weight:700">{"✓" if actual==1 else "✗"}</span>'
                elif av:
                    c = "#10b981" if actual == 0 else "#ef4444"
                    result_html = f' <span style="color:{c};font-weight:700">{"✓" if actual==0 else "✗"}</span>'

            if hv:
                badge = f'<span class="badge-val">VALUE · {home} · {he:+.1%} · {_fmt(hpr)}</span>'
            elif av:
                badge = f'<span class="badge-val">VALUE · {away} · {ae:+.1%} · {_fmt(apr)}</span>'
            elif hp > ap:
                badge = f'<span class="badge-lean">LEAN {home} · {hp:.0%}</span>'
            elif ap > hp:
                badge = f'<span class="badge-lean">LEAN {away} · {ap:.0%}</span>'
            else:
                badge = '<span style="color:#3d5270;font-size:11px">—</span>'

            rows_html += f"""
<div class="gr">
  <div class="gr-tm"><b>{away}</b><span style="color:#7a8fa8;font-weight:400"> @ </span><b>{home}</b></div>
  <div class="gr-tip">{tip}</div>
  <div class="gr-badge">{badge}{result_html}</div>
</div>"""
        rows_html += "</div>"
        st.markdown(rows_html, unsafe_allow_html=True)


# ── spread ────────────────────────────────────────────────────────────────────

def _get_top_ats_picks(spread_preds, n=2):
    candidates = []
    for _, g in spread_preds.iterrows():
        for side in ["home", "away"]:
            edge  = float(g.get(f"{side}_ats_edge", 0))
            prob  = float(g.get(f"{side}_cover_prob", 0))
            kelly = float(g.get(f"{side}_ats_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_ats_value", 0))
            if val != 1 or edge < MIN_EDGE or kelly < 0.005:
                continue
            score = _composite(edge, prob, kelly)
            candidates.append({
                "side":             side,
                "score":            score,
                "bet_team":         g["home_team"] if side == "home" else g["away_team"],
                "home_team":        g["home_team"],
                "away_team":        g["away_team"],
                "commence_time":    g.get("commence_time", ""),
                "bookmaker":        g.get("bookmaker", ""),
                "spread":           g.get(f"{side}_point"),
                "home_point":       g.get("home_point"),
                "pred_home_margin": float(g.get("pred_home_margin", 0)),
                "cover_prob":       prob,
                "fair_prob":        float(g.get(f"{side}_cover_fair", 0.5)),
                "edge":             edge,
                "kelly":            kelly,
                "price":            price,
            })
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:n]


def _render_spread_section(today: str):
    spread_preds = _load(
        "SELECT * FROM spread_predictions WHERE predict_date=? ORDER BY commence_time",
        params=(today,)
    )
    st.markdown("<div class='ax-sh'>Against the Spread (ATS)</div>", unsafe_allow_html=True)

    if spread_preds.empty:
        st.info("No spread predictions yet. Run `python spread_predict.py`.")
        return

    top = _get_top_ats_picks(spread_preds, n=2)

    if top:
        if len(top) == 2:
            c1, c2 = st.columns(2)
            cols = [c1, c2]
        else:
            cols = None
        for i, pick in enumerate(top):
            spread_str = f"{pick['spread']:+.1f}" if pick["spread"] is not None else "N/A"
            card_html = f"""
<div class="pick-card">
  <div class="pc-tier">📐 ATS VALUE BET</div>
  <div class="pc-matchup">{pick['away_team']} @ {pick['home_team']}</div>
  <div class="pc-meta">Tip {_tip_et(pick['commence_time'])} &nbsp;·&nbsp; {str(pick['bookmaker']).upper()}</div>
  <div class="pc-pick">🎯 {pick['bet_team']} &nbsp;{spread_str} &nbsp;({_fmt(pick['price'])})</div>
  <div class="sp-wrap">
    <div class="sp"><div class="sp-val">{pick['cover_prob']:.1%}</div><div class="sp-lbl">P(cover)</div></div>
    <div class="sp"><div class="sp-val" style="color:#10b981">{pick['edge']:+.1%}</div><div class="sp-lbl">Edge</div></div>
    <div class="sp"><div class="sp-val">{pick['fair_prob']:.1%}</div><div class="sp-lbl">Book</div></div>
    <div class="sp"><div class="sp-val">{pick['pred_home_margin']:+.1f}</div><div class="sp-lbl">Pred margin</div></div>
    <div class="sp"><div class="sp-val">{pick['kelly']*100:.1f}%</div><div class="sp-lbl">Kelly</div></div>
  </div>
</div>"""
            if cols:
                with cols[i]:
                    st.markdown(card_html, unsafe_allow_html=True)
            else:
                st.markdown(card_html, unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='color:#7a8fa8;font-size:13px;padding:.75rem 0'>No ATS value today.</div>",
            unsafe_allow_html=True
        )

    with st.expander(f"All {len(spread_preds)} ATS lines"):
        rows_html = "<div class='gr-wrap'>"
        for _, g in spread_preds.iterrows():
            home = g["home_team"]; away = g["away_team"]
            home_pt  = g.get("home_point")
            away_pt  = g.get("away_point")
            pred_m   = float(g.get("pred_home_margin", 0))
            hv       = int(g.get("home_ats_value", 0))
            av       = int(g.get("away_ats_value", 0))
            he       = float(g.get("home_ats_edge", 0))
            ae       = float(g.get("away_ats_edge", 0))
            home_spr = f"{home_pt:+.1f}" if home_pt is not None else "—"
            away_spr = f"{away_pt:+.1f}" if away_pt is not None else "—"
            if hv:
                badge = f'<span class="badge-val">VALUE · {home} {home_spr} · {he:+.1%}</span>'
            elif av:
                badge = f'<span class="badge-val">VALUE · {away} {away_spr} · {ae:+.1%}</span>'
            else:
                badge = '<span style="color:#3d5270;font-size:11px">No edge</span>'
            rows_html += f"""
<div class="gr">
  <div class="gr-tm"><b>{away}</b><span style="color:#7a8fa8;font-weight:400"> @ </span><b>{home}</b></div>
  <div style="font-size:11px;color:#7a8fa8;text-align:center;width:120px">{home} {home_spr} &nbsp;·&nbsp; {pred_m:+.1f}</div>
  <div class="gr-badge">{badge}</div>
</div>"""
        rows_html += "</div>"
        st.markdown(rows_html, unsafe_allow_html=True)


# ── totals ────────────────────────────────────────────────────────────────────

def _get_top_totals_picks(totals_preds, n=2):
    candidates = []
    for _, g in totals_preds.iterrows():
        for side in ["over", "under"]:
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < MIN_EDGE or kelly < 0.005:
                continue
            score = _composite(edge, prob, kelly)
            candidates.append({
                "side":         side,
                "score":        score,
                "home_team":    g["home_team"],
                "away_team":    g["away_team"],
                "commence_time":g.get("commence_time", ""),
                "bookmaker":    g.get("bookmaker", ""),
                "total_line":   g.get("total_line"),
                "pred_total":   float(g.get("pred_total", 0)),
                "ou_prob":      prob,
                "fair_prob":    float(g.get(f"{side}_fair", 0.5)),
                "edge":         edge,
                "kelly":        kelly,
                "price":        price,
            })
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:n]


def _render_totals_section(today: str):
    totals_preds = _load(
        "SELECT * FROM totals_predictions WHERE predict_date=? ORDER BY commence_time",
        params=(today,)
    )
    st.markdown("<div class='ax-sh'>Over / Under (Totals)</div>", unsafe_allow_html=True)

    if totals_preds.empty:
        st.info("No totals predictions yet. Run `python totals_predict.py`.")
        return

    top = _get_top_totals_picks(totals_preds, n=2)

    if top:
        if len(top) == 2:
            c1, c2 = st.columns(2)
            cols = [c1, c2]
        else:
            cols = None
        for i, pick in enumerate(top):
            side_label = "OVER" if pick["side"] == "over" else "UNDER"
            line_str   = f"{pick['total_line']:.1f}" if pick["total_line"] is not None else "N/A"
            card_html  = f"""
<div class="pick-card" style="border-left-color:#f59e0b">
  <div class="pc-tier" style="color:#f59e0b">🏹 TOTALS VALUE BET</div>
  <div class="pc-matchup">{pick['away_team']} @ {pick['home_team']}</div>
  <div class="pc-meta">Tip {_tip_et(pick['commence_time'])} &nbsp;·&nbsp; {str(pick['bookmaker']).upper()}</div>
  <div class="pc-pick" style="background:#78350f18;border-color:#b4530640;color:#fbbf24">{side_label} {line_str} &nbsp;{_fmt(pick['price'])}</div>
  <div class="sp-wrap">
    <div class="sp"><div class="sp-val">{pick['ou_prob']:.1%}</div><div class="sp-lbl">P({side_label.lower()})</div></div>
    <div class="sp"><div class="sp-val" style="color:#10b981">{pick['edge']:+.1%}</div><div class="sp-lbl">Edge</div></div>
    <div class="sp"><div class="sp-val">{pick['fair_prob']:.1%}</div><div class="sp-lbl">Book</div></div>
    <div class="sp"><div class="sp-val">{pick['pred_total']:.1f}</div><div class="sp-lbl">Pred total</div></div>
    <div class="sp"><div class="sp-val">{pick['kelly']*100:.1f}%</div><div class="sp-lbl">Kelly</div></div>
  </div>
</div>"""
            if cols:
                with cols[i]:
                    st.markdown(card_html, unsafe_allow_html=True)
            else:
                st.markdown(card_html, unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='color:#7a8fa8;font-size:13px;padding:.75rem 0'>No totals value today.</div>",
            unsafe_allow_html=True
        )

    with st.expander(f"All {len(totals_preds)} totals"):
        rows_html = "<div class='gr-wrap'>"
        for _, g in totals_preds.iterrows():
            home = g["home_team"]; away = g["away_team"]
            line   = g.get("total_line")
            pred_t = float(g.get("pred_total", 0))
            ov     = int(g.get("over_value", 0))
            uv     = int(g.get("under_value", 0))
            oe     = float(g.get("over_edge", 0))
            ue     = float(g.get("under_edge", 0))
            line_str = f"{line:.1f}" if line is not None else "—"
            if ov:
                badge = f'<span class="badge-val">OVER {line_str} · {oe:+.1%}</span>'
            elif uv:
                badge = f'<span class="badge-val">UNDER {line_str} · {ue:+.1%}</span>'
            else:
                badge = '<span style="color:#3d5270;font-size:11px">No edge</span>'
            rows_html += f"""
<div class="gr">
  <div class="gr-tm"><b>{away}</b><span style="color:#7a8fa8;font-weight:400"> @ </span><b>{home}</b></div>
  <div style="font-size:11px;color:#7a8fa8;text-align:center;width:110px">Line {line_str} · {pred_t:.1f}</div>
  <div class="gr-badge">{badge}</div>
</div>"""
        rows_html += "</div>"
        st.markdown(rows_html, unsafe_allow_html=True)


# ── props (generic) ───────────────────────────────────────────────────────────

def _get_top_prop_picks(preds, cfg, n=2):
    """Return top-N prop picks by composite score for the given market config."""
    min_edge = cfg["min_edge"]
    pred_col = cfg["pred_col"]
    candidates = []
    for _, g in preds.iterrows():
        for side in ["over", "under"]:
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005:
                continue
            score = _composite(edge, prob, kelly)
            candidates.append({
                "side":        side,
                "score":       score,
                "player_name": g["player_name"],
                "home_team":   g["home_team"],
                "away_team":   g["away_team"],
                "bookmaker":   g.get("bookmaker", ""),
                "line":        g.get("line"),
                "pred_val":    float(g.get(pred_col, 0)),
                "ou_prob":     prob,
                "fair_prob":   float(g.get(f"{side}_fair", 0.5)),
                "edge":        edge,
                "kelly":       kelly,
                "price":       price,
            })
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:n]


def _render_prop_section(cfg, today: str):
    preds = _load(
        f"SELECT * FROM {cfg['table']} WHERE predict_date=? ORDER BY over_edge DESC",
        params=(today,)
    )
    color      = cfg["color"]
    label      = cfg["label"]
    unit       = cfg["unit"]
    icon       = cfg["icon"]
    pred_col   = cfg["pred_col"]
    actual_col = cfg["actual_col"]

    st.markdown(
        f"<div class='props-hdr' style='color:{color}'>{icon} {label}</div>",
        unsafe_allow_html=True
    )

    if preds.empty:
        st.markdown(
            f"<div style='color:#7a8fa8;font-size:13px;padding:.25rem 0 .75rem'>"
            f"No {label.lower()} predictions today.</div>",
            unsafe_allow_html=True
        )
        return

    top_picks = _get_top_prop_picks(preds, cfg, n=2)

    # Featured top-2 cards
    if top_picks:
        if len(top_picks) == 2:
            c1, c2 = st.columns(2)
            cols = [c1, c2]
        else:
            cols = None
        for i, pick in enumerate(top_picks):
            side_label = "OVER" if pick["side"] == "over" else "UNDER"
            home       = pick["home_team"].split()[-1]
            away       = pick["away_team"].split()[-1]
            edge_c     = color if pick["edge"] > 0 else "#ef4444"
            card_html  = f"""
<div class="pick-card" style="border-left-color:{color}">
  <div class="pc-tier" style="color:{color}">{icon} {label.upper()} PROP · VALUE</div>
  <div class="pc-matchup">{pick['player_name']}</div>
  <div class="pc-meta">{away} @ {home} &nbsp;·&nbsp; {label} &nbsp;·&nbsp; {str(pick['bookmaker']).upper()}</div>
  <div class="pc-pick" style="background:{color}18;border-color:{color}50;color:{color}">{side_label} {pick['line']} {unit} &nbsp;{_fmt(pick['price'])}</div>
  <div class="sp-wrap">
    <div class="sp"><div class="sp-val">{pick['ou_prob']:.1%}</div><div class="sp-lbl">P({side_label.lower()})</div></div>
    <div class="sp"><div class="sp-val" style="color:{edge_c}">{pick['edge']:+.1%}</div><div class="sp-lbl">Edge</div></div>
    <div class="sp"><div class="sp-val">{pick['fair_prob']:.1%}</div><div class="sp-lbl">Book</div></div>
    <div class="sp"><div class="sp-val">{pick['pred_val']:.1f}</div><div class="sp-lbl">Pred {unit}</div></div>
    <div class="sp"><div class="sp-val">{pick['kelly']*100:.1f}%</div><div class="sp-lbl">Kelly</div></div>
  </div>
</div>"""
            if cols:
                with cols[i]:
                    st.markdown(card_html, unsafe_allow_html=True)
            else:
                st.markdown(card_html, unsafe_allow_html=True)
    else:
        st.markdown(
            f"<div style='color:#7a8fa8;font-size:13px;padding:.25rem 0 .75rem'>"
            f"No {label.lower()} value today.</div>",
            unsafe_allow_html=True
        )

    # Remaining value picks in expander
    top_ids   = {(p["player_name"], p["side"]) for p in top_picks}
    remaining = []
    for _, g in preds.iterrows():
        for side in ["over", "under"]:
            if int(g.get(f"{side}_value", 0)) == 1 and (g["player_name"], side) not in top_ids:
                remaining.append((g, side))

    if remaining:
        n_more = len(remaining)
        with st.expander(f"{n_more} more {label.lower()} pick{'s' if n_more != 1 else ''}"):
            rows_html = "<div class='gr-wrap'>"
            for g, side in remaining:
                ov        = side == "over"
                side_lbl  = "OVER" if ov else "UNDER"
                edge_val  = float(g.get(f"{side}_edge", 0))
                prob_val  = float(g.get(f"{side}_prob", 0))
                price_val = g.get(f"{side}_price")
                pred_val  = float(g.get(pred_col, 0))
                home      = g["home_team"].split()[-1]
                away      = g["away_team"].split()[-1]
                actual_html = ""
                if pd.notna(g.get(actual_col)):
                    actual = float(g[actual_col])
                    line   = float(g.get("line", 0))
                    won    = (actual > line) if ov else (actual <= line)
                    c      = "#10b981" if won else "#ef4444"
                    actual_html = (
                        f' &nbsp;<span style="color:{c};font-size:11px;font-weight:700">'
                        f'{"✓" if won else "✗"} {actual:.0f} {unit}</span>'
                    )
                rows_html += f"""
<div class="prop-row">
  <div>
    <div style="font-size:13px;font-weight:600;color:#f0f2f5">{g['player_name']}</div>
    <div style="font-size:11px;color:#8090a8">{away} @ {home} &nbsp;·&nbsp; Pred: {pred_val:.1f} {unit}</div>
  </div>
  <div style="text-align:right">
    <div style="color:{color};font-weight:700;font-size:13px">{side_lbl} {g['line']} &nbsp;{_fmt(price_val)}</div>
    <div style="font-size:11px;color:#8090a8">{prob_val:.0%} prob &nbsp;·&nbsp; {edge_val:+.1%} edge{actual_html}</div>
  </div>
</div>"""
            rows_html += "</div>"
            st.markdown(rows_html, unsafe_allow_html=True)


# ── legacy helpers (kept for backward compatibility) ──────────────────────────

def _get_best(preds):
    """Legacy: return single top ML pick (value preferred, else lean)."""
    results = _get_top_ml_picks(preds, n=1)
    return results[0] if results else None


def _get_best_ats(spread_preds):
    """Legacy: return single top ATS pick."""
    results = _get_top_ats_picks(spread_preds, n=1)
    return results[0] if results else None


def _get_best_total(totals_preds):
    """Legacy: return single top totals pick."""
    results = _get_top_totals_picks(totals_preds, n=1)
    return results[0] if results else None


def _build_reasoning(best):
    """Legacy reasoning bullet builder."""
    reasons = []
    is_value = best.get("tier") == "VALUE BET"
    fair     = best.get("fair_prob", 0.5)
    if is_value:
        reasons.append(
            f"Model assigns {best['prob']:.1%} win prob vs book's {fair:.1%} "
            f"— {best['edge']:.1%} statistical edge"
        )
        reasons.append(
            f"Kelly criterion suggests {best['kelly']*100:.1f}% of bankroll "
            f"— {'high' if best['kelly'] > 0.05 else 'moderate'} confidence"
        )
    else:
        reasons.append(
            f"Model assigns {best['prob']:.1%} win prob vs book's {fair:.1%}"
        )
        reasons.append("No statistical edge — directional model opinion only")
    try:
        p = float(best["price"])
        if p < 0:
            reasons.append(f"Favorite at {_fmt(best['price'])} — higher hit rate")
        else:
            reasons.append(f"Underdog at {_fmt(best['price'])} — higher variance, size accordingly")
    except Exception:
        pass
    return reasons


# ── main render ───────────────────────────────────────────────────────────────

def render():
    st.markdown(_CSS, unsafe_allow_html=True)

    today = date.today().isoformat()

    # Page title
    try:
        day_str = date.today().strftime("%-d")
    except ValueError:
        day_str = date.today().strftime("%d").lstrip("0") or "0"
    date_label = date.today().strftime(f"%B {day_str}, %Y")

    st.markdown(
        f"<div class='picks-title'>🏀 NBA Picks</div>"
        f"<div class='picks-date'>{date_label}</div>",
        unsafe_allow_html=True
    )

    # Stats strip — load moneyline preds for summary counts
    preds = _load(
        "SELECT * FROM predictions WHERE predict_date=? ORDER BY commence_time",
        params=(today,)
    )
    if not preds.empty:
        val_ml = int(((preds["home_value"] == 1) | (preds["away_value"] == 1)).sum())
        try:
            best_edge     = max(float(preds["home_edge"].max()), float(preds["away_edge"].max()))
            best_edge_str = f"{best_edge:.1%}"
        except Exception:
            best_edge_str = "—"
        results_in = int(preds["actual_home_win"].notna().sum())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Games Today",   len(preds))
        c2.metric("ML Value Bets", val_ml)
        c3.metric("Best ML Edge",  best_edge_str)
        c4.metric("Results In",    f"{results_in} / {len(preds)}")

    # ── main sections ─────────────────────────────────────────────────────────
    _render_ml_section(today)
    _render_spread_section(today)
    _render_totals_section(today)

    # ── player props ──────────────────────────────────────────────────────────
    st.markdown(
        "<div class='ax-sh' style='margin-top:2.5rem'>Player Props</div>",
        unsafe_allow_html=True
    )
    for cfg in PROP_CONFIGS.values():
        _render_prop_section(cfg, today)
