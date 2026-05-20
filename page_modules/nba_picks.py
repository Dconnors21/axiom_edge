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
import numpy as np

_CSS = """
<style>
.block-container{padding-top:1.5rem;padding-bottom:2rem;max-width:1100px}
[data-testid="metric-container"]{background:#13131a;border:1px solid #1e1e28;border-radius:10px;padding:1rem 1.25rem}
[data-testid="metric-container"] label{color:#6b6b78!important;font-size:12px!important;letter-spacing:.05em;text-transform:uppercase}
[data-testid="stMetricValue"]{color:#e8e8ec!important;font-size:24px!important;font-weight:700!important}
.sh{font-size:11px;font-weight:600;letter-spacing:.1em;color:#44444f;text-transform:uppercase;margin:1.5rem 0 .75rem;padding-bottom:8px;border-bottom:1px solid #1e1e28}
.game-card{background:#13131a;border:1px solid #1e1e28;border-radius:12px;padding:1.25rem 1.5rem;margin-bottom:12px}
.game-card.has-value{border-color:#1a3a1a;border-left:3px solid #22c55e}
.game-card.no-value{border-left:3px solid #333340}
.prob-row{display:flex;align-items:center;padding:8px 0;border-bottom:1px solid #1e1e28;font-size:13px}
.prob-row:last-child{border-bottom:none}
.prob-team{flex:1;color:#c0c0cc}
.prob-team.vt{color:#e8e8ec;font-weight:600}
.prob-model{width:60px;text-align:right;color:#e8e8ec;font-weight:500}
.prob-book{width:60px;text-align:right;color:#6b6b78}
.prob-edge{width:70px;text-align:right;font-weight:600}
.prob-line{width:60px;text-align:right;color:#9090a0;font-size:12px}
.ep{color:#22c55e}.en{color:#6b6b78}
.vbadge{display:inline-flex;align-items:center;gap:6px;background:#0d2a0d;color:#22c55e;border:1px solid #1a4a1a;border-radius:6px;padding:6px 12px;font-size:12px;font-weight:600;margin-top:12px;margin-right:8px}
.leanbadge{display:inline-flex;align-items:center;gap:6px;background:#0d0d2a;color:#6366f1;border:1px solid #1a1a4a;border-radius:6px;padding:6px 12px;font-size:12px;font-weight:600;margin-top:12px;margin-right:8px}
.nvbadge{display:inline-flex;align-items:center;gap:6px;color:#44444f;font-size:12px;margin-top:10px;padding:4px 0}
.bar-bg{background:#1e1e28;border-radius:3px;height:5px;flex:1;overflow:hidden}
.bar-fill{height:100%;border-radius:3px}
.best-bet-card{border-radius:14px;padding:1.75rem 2rem;margin-bottom:1.5rem;position:relative;overflow:hidden}
.best-bet-card.value{background:linear-gradient(135deg,#0d1020 0%,#111528 100%);border:1px solid #6366f1}
.best-bet-card.value::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#6366f1,#22c55e,#6366f1)}
.best-bet-card.lean{background:linear-gradient(135deg,#0d0d14 0%,#111118 100%);border:1px solid #2a2a3a}
.best-bet-card.lean::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#4a4a6a,#6366f1,#4a4a6a)}
.bb-tier-value{font-size:11px;font-weight:700;letter-spacing:.12em;color:#6366f1;text-transform:uppercase;margin-bottom:12px}
.bb-tier-lean{font-size:11px;font-weight:700;letter-spacing:.12em;color:#4a4a6a;text-transform:uppercase;margin-bottom:12px}
.bb-matchup{font-size:20px;font-weight:700;color:#e8e8ec;letter-spacing:-.3px;margin-bottom:4px}
.bb-meta{font-size:13px;color:#6b6b78;margin-bottom:1.25rem}
.bb-pick-value{display:inline-flex;align-items:center;gap:10px;background:#0d0d2a;border:1px solid #6366f1;border-radius:8px;padding:10px 18px;font-size:16px;font-weight:700;color:#6366f1;margin-bottom:1.25rem}
.bb-pick-lean{display:inline-flex;align-items:center;gap:10px;background:#0f0f18;border:1px solid #2a2a3a;border-radius:8px;padding:10px 18px;font-size:16px;font-weight:700;color:#9090a0;margin-bottom:1.25rem}
.stat-pill{display:inline-flex;flex-direction:column;align-items:center;background:#0f0f12;border:1px solid #1e1e28;border-radius:8px;padding:10px 16px;min-width:80px}
.stat-pill-val{font-size:18px;font-weight:700;color:#e8e8ec}
.stat-pill-lbl{font-size:10px;color:#44444f;letter-spacing:.06em;text-transform:uppercase;margin-top:2px}
.reasoning-row{display:flex;align-items:flex-start;gap:8px;font-size:12px;color:#6b6b78;margin-top:6px}
.reasoning-dot-value{width:5px;height:5px;border-radius:50%;background:#6366f1;margin-top:5px;flex-shrink:0}
.reasoning-dot-lean{width:5px;height:5px;border-radius:50%;background:#444460;margin-top:5px;flex-shrink:0}
.lean-disclaimer{font-size:11px;color:#44444f;background:#0f0f14;border:1px solid #1a1a24;border-radius:6px;padding:8px 12px;margin-top:12px}
</style>
"""

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
        return pd.to_datetime(commence_time, utc=True)\
                 .tz_convert("America/New_York")\
                 .strftime("%I:%M %p ET").lstrip("0")
    except Exception:
        return str(commence_time)

def _get_best(preds):
    if preds.empty:
        return None
    value_candidates, lean_candidates = [], []
    for _, game in preds.iterrows():
        for side in ["home", "away"]:
            edge  = float(game.get(f"{side}_edge", 0))
            prob  = float(game.get(f"model_{side}_prob", 0))
            kelly = float(game.get(f"{side}_kelly", 0))
            price = game.get(f"{side}_price")
            val   = int(game.get(f"{side}_value", 0))
            if prob < 0.50:
                continue
            try: ladder = float(price) <= 250
            except Exception: ladder = False
            bet_team = game["home_team"] if side == "home" else game["away_team"]
            entry = {
                "game": game, "side": side, "bet_team": bet_team,
                "edge": edge, "prob": prob, "kelly": kelly,
                "price": price, "ladder": ladder,
                "home_team": game["home_team"], "away_team": game["away_team"],
                "commence_time": game.get("commence_time", ""),
                "bookmaker": game.get("bookmaker", ""),
                "fair_prob": float(game.get(f"{side}_fair_prob", 0.5)),
            }
            if val == 1 and edge >= MIN_EDGE and kelly >= 0.005:
                entry["tier"] = "VALUE BET"
                value_candidates.append(entry)
            else:
                entry["tier"] = "MODEL LEAN"
                lean_candidates.append(entry)
    if value_candidates:
        value_candidates.sort(key=lambda x: (x["ladder"], x["edge"]), reverse=True)
        return value_candidates[0]
    if lean_candidates:
        lean_candidates.sort(key=lambda x: x["prob"], reverse=True)
        return lean_candidates[0]
    return None

def _build_reasoning(best):
    reasons = []
    is_value = best["tier"] == "VALUE BET"
    if is_value:
        reasons.append(f"Model assigns {best['prob']:.1%} win probability vs book's implied {best['fair_prob']:.1%} — a {best['edge']:.1%} statistical edge")
        reasons.append(f"Kelly criterion suggests {best['kelly']*100:.1f}% of bankroll — {'high' if best['kelly']>0.05 else 'moderate'} confidence sizing")
    else:
        reasons.append(f"Model assigns {best['prob']:.1%} win probability — stronger conviction than the book's {best['fair_prob']:.1%} implied")
        reasons.append("No statistical edge detected — directional model opinion only, not a value bet")
    try:
        p = float(best["price"])
        if p < 0:
            reasons.append(f"Favorite at {_fmt(best['price'])} — higher hit rate, suitable for ladder approach")
        else:
            reasons.append(f"Underdog at {_fmt(best['price'])} — higher variance, size accordingly")
    except Exception:
        pass
    return reasons


def render():
    st.markdown(_CSS, unsafe_allow_html=True)

    today = date.today().isoformat()
    preds = _load("SELECT * FROM predictions WHERE predict_date=? ORDER BY commence_time", params=(today,))

    st.markdown(f"<div class='sh'>🏀 NBA Picks &nbsp;·&nbsp; {date.today().strftime('%B %d, %Y')}</div>",
                unsafe_allow_html=True)

    if preds.empty:
        st.info("No predictions yet. Run `python odds.py` then `python predict.py`.")
        return

    val_games = preds[(preds["home_value"] == 1) | (preds["away_value"] == 1)]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Games", len(preds))
    c2.metric("Value bets", len(val_games))
    best_edge = max(preds["home_edge"].max(), preds["away_edge"].max())
    c3.metric("Best edge", f"{best_edge:.1%}")
    c4.metric("Results in", f"{preds['actual_home_win'].notna().sum()} / {len(preds)}")

    best = _get_best(preds)
    if best:
        is_value = best["tier"] == "VALUE BET"
        card_cls = "best-bet-card value" if is_value else "best-bet-card lean"
        tier_cls = "bb-tier-value" if is_value else "bb-tier-lean"
        pick_cls = "bb-pick-value" if is_value else "bb-pick-lean"
        dot_cls  = "reasoning-dot-value" if is_value else "reasoning-dot-lean"
        tier_icon = "⭐" if is_value else "🔵"

        tip = _tip_et(best["commence_time"])
        game = best["game"]
        result_html = ""
        if pd.notna(game.get("actual_home_win")):
            actual = int(game["actual_home_win"])
            won = (best["side"] == "home" and actual == 1) or (best["side"] == "away" and actual == 0)
            color = "#22c55e" if won else "#ef4444"
            result_html = f'<span style="font-size:16px;font-weight:700;color:{color}">{"✓ WIN" if won else "✗ LOSS"}</span>'

        ladder_html = ""
        if is_value and best["ladder"]:
            ladder_html = '<span style="display:inline-flex;align-items:center;gap:6px;background:#0d0d2a;border:1px solid #6366f1;border-radius:6px;padding:4px 10px;font-size:11px;font-weight:600;color:#6366f1;margin-top:8px">🪜 Ladder eligible</span>'

        reasons     = _build_reasoning(best)
        reason_html = "".join([f'<div class="reasoning-row"><div class="{dot_cls}"></div><span>{r}</span></div>' for r in reasons])
        disclaimer  = '<div class="lean-disclaimer">⚠️ Model lean only — no statistical edge detected. Reduce position size vs a true value bet.</div>' if not is_value else ""
        edge_display = f"{best['edge']:+.1%}" if is_value else f"{best['prob']:.1%} model prob"
        edge_label   = "Edge" if is_value else "Confidence"

        st.markdown(f"""
<div class="{card_cls}">
  <div class="{tier_cls}">{tier_icon} {best['tier']} &nbsp; {result_html}</div>
  <div class="bb-matchup">{best['away_team']} @ {best['home_team']}</div>
  <div class="bb-meta">Tip: {tip} · {str(best['bookmaker']).upper()}</div>
  <div class="{pick_cls}">🎯 {best['bet_team']} &nbsp;{_fmt(best['price'])}</div>
  {ladder_html}
  <div style="display:flex;gap:12px;margin:1.25rem 0;flex-wrap:wrap">
    <div class="stat-pill"><div class="stat-pill-val">{best['prob']:.1%}</div><div class="stat-pill-lbl">Model prob</div></div>
    <div class="stat-pill"><div class="stat-pill-val" style="color:{'#6366f1' if is_value else '#44444f'}">{edge_display}</div><div class="stat-pill-lbl">{edge_label}</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{best['fair_prob']:.1%}</div><div class="stat-pill-lbl">Book implied</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{best['kelly']*100:.1f}%</div><div class="stat-pill-lbl">Kelly stake</div></div>
  </div>
  <div style="border-top:1px solid #1e1e28;padding-top:1rem">
    <div style="font-size:11px;color:#44444f;letter-spacing:.06em;text-transform:uppercase;margin-bottom:8px">Why this pick</div>
    {reason_html}
  </div>
  {disclaimer}
</div>
""", unsafe_allow_html=True)

    st.markdown("<div class='sh'>All games</div>", unsafe_allow_html=True)

    for _, game in preds.iterrows():
        home = game["home_team"]; away = game["away_team"]
        hv = int(game.get("home_value", 0)) == 1
        av = int(game.get("away_value", 0)) == 1
        has_val = hv or av
        hprob = float(game.get("model_home_prob", 0.5))
        aprob = float(game.get("model_away_prob", 0.5))
        h_is_lean = not hv and hprob > aprob and not has_val
        a_is_lean = not av and aprob > hprob and not has_val

        tip = _tip_et(game["commence_time"])
        hf = float(game.get("home_fair_prob", 0.5)); af = float(game.get("away_fair_prob", 0.5))
        he = float(game.get("home_edge", 0));        ae = float(game.get("away_edge", 0))
        hpr = game.get("home_price");                apr = game.get("away_price")
        hk = float(game.get("home_kelly", 0));       ak = float(game.get("away_kelly", 0))

        rh = ""
        if pd.notna(game.get("actual_home_win")):
            actual = int(game["actual_home_win"])
            if hv:
                c = "#22c55e" if actual == 1 else "#ef4444"
                rh = f'<span style="color:{c};font-weight:600;font-size:13px">{"✓ W" if actual==1 else "✗ L"}</span>'
            elif av:
                c = "#22c55e" if actual == 0 else "#ef4444"
                rh = f'<span style="color:{c};font-weight:600;font-size:13px">{"✓ W" if actual==0 else "✗ L"}</span>'

        bdg = ""
        if hv:      bdg += f'<span class="vbadge">VALUE {home} | {he:+.1%} edge | Kelly {hk*100:.1f}% | {_fmt(hpr)}</span>'
        elif h_is_lean: bdg += f'<span class="leanbadge">MODEL LEAN {home} | {hprob:.1%} prob | {_fmt(hpr)}</span>'
        if av:      bdg += f'<span class="vbadge">VALUE {away} | {ae:+.1%} edge | Kelly {ak*100:.1f}% | {_fmt(apr)}</span>'
        elif a_is_lean: bdg += f'<span class="leanbadge">MODEL LEAN {away} | {aprob:.1%} prob | {_fmt(apr)}</span>'
        if not bdg: bdg = '<span class="nvbadge">No edge — skip</span>'

        hb = int(hprob * 100); ab = int(aprob * 100)
        cc = "game-card has-value" if has_val else "game-card no-value"
        hc = "vt" if hv else ""; ac = "vt" if av else ""
        hec = "ep" if he > MIN_EDGE else "en"; aec = "ep" if ae > MIN_EDGE else "en"

        is_best = best and (
            (best["side"] == "home" and best["home_team"] == home) or
            (best["side"] == "away" and best["away_team"] == away)
        )
        tier_marker = ""
        if is_best:
            mc = "#6366f1" if best["tier"] == "VALUE BET" else "#44444f"
            mi = "⭐" if best["tier"] == "VALUE BET" else "🔵"
            tier_marker = f'<span style="font-size:11px;color:{mc};font-weight:600;margin-left:8px">{mi} {best["tier"]}</span>'

        st.markdown(f"""
<div class="{cc}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <p style="font-size:16px;font-weight:600;color:#e8e8ec;margin:0 0 4px">
        {away} <span style="color:#44444f;font-weight:400">@</span> {home}{tier_marker}
      </p>
      <p style="font-size:12px;color:#6b6b78;margin:0 0 1rem">Tip: {tip} · {str(game.get('bookmaker','')).upper()}</p>
    </div><div>{rh}</div>
  </div>
  <div style="display:flex;padding:6px 0 4px;border-bottom:1px solid #1e1e28;font-size:11px;color:#44444f;letter-spacing:.04em;text-transform:uppercase">
    <div style="flex:1">Team</div>
    <div style="width:60px;text-align:right">Model</div>
    <div style="width:60px;text-align:right">Book</div>
    <div style="width:70px;text-align:right">Edge</div>
    <div style="width:60px;text-align:right">Line</div>
  </div>
  <div class="prob-row"><div class="prob-team {hc}">{home}</div><div class="prob-model">{hprob:.1%}</div><div class="prob-book">{hf:.1%}</div><div class="prob-edge {hec}">{he:+.1%}</div><div class="prob-line">{_fmt(hpr)}</div></div>
  <div class="prob-row" style="margin-bottom:4px"><div class="prob-team {ac}">{away}</div><div class="prob-model">{aprob:.1%}</div><div class="prob-book">{af:.1%}</div><div class="prob-edge {aec}">{ae:+.1%}</div><div class="prob-line">{_fmt(apr)}</div></div>
  <div style="display:flex;gap:8px;align-items:center;margin:10px 0 6px">
    <div style="font-size:11px;color:#44444f;width:32px">{away[:3].upper()}</div>
    <div class="bar-bg"><div class="bar-fill" style="width:{ab}%;background:#6366f1"></div></div>
    <div style="font-size:11px;color:#44444f;text-align:center;width:44px">{ab}%/{hb}%</div>
    <div class="bar-bg"><div class="bar-fill" style="width:{hb}%;background:#22c55e"></div></div>
    <div style="font-size:11px;color:#44444f;width:32px;text-align:right">{home[:3].upper()}</div>
  </div>
  {bdg}
</div>""", unsafe_allow_html=True)

    # ── Spread section ──────────────────────────────────────────────────────────
    _render_spread_section(today)

    # ── Totals section ──────────────────────────────────────────────────────────
    _render_totals_section(today)

    # ── Props section ───────────────────────────────────────────────────────────
    _render_props_section(today)


def _render_spread_section(today: str):
    spread_preds = _load(
        "SELECT * FROM spread_predictions WHERE predict_date=? ORDER BY commence_time",
        params=(today,)
    )

    st.markdown("<div class='sh'>📐 ATS — Against the Spread</div>", unsafe_allow_html=True)

    if spread_preds.empty:
        st.info("No spread predictions yet. Run `python spread_predict.py` to generate them.")
        return

    # Best ATS pick
    best_ats = _get_best_ats(spread_preds)

    if best_ats:
        b = best_ats
        is_home = b["side"] == "home"
        spread_str = f"{b['spread']:+.1f}" if b["spread"] is not None else "N/A"
        color = "#6366f1"
        st.markdown(f"""
<div class="best-bet-card value" style="border-color:{color}">
  <div class="bb-tier-value">📐 ATS VALUE BET</div>
  <div class="bb-matchup">{b['away_team']} @ {b['home_team']}</div>
  <div class="bb-meta">Tip: {_tip_et(b['commence_time'])} · {str(b['bookmaker']).upper()}</div>
  <div class="bb-pick-value">🎯 {b['bet_team']} &nbsp;{spread_str} &nbsp;({_fmt(b['price'])})</div>
  <div style="display:flex;gap:12px;margin:1.25rem 0;flex-wrap:wrap">
    <div class="stat-pill"><div class="stat-pill-val">{b['cover_prob']:.1%}</div><div class="stat-pill-lbl">P(cover)</div></div>
    <div class="stat-pill"><div class="stat-pill-val" style="color:{color}">{b['edge']:+.1%}</div><div class="stat-pill-lbl">ATS edge</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{b['fair_prob']:.1%}</div><div class="stat-pill-lbl">Book implied</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{b['pred_margin']:+.1f}</div><div class="stat-pill-lbl">Pred margin</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{b['kelly']*100:.1f}%</div><div class="stat-pill-lbl">Kelly stake</div></div>
  </div>
  <div style="border-top:1px solid #1e1e28;padding-top:.8rem;font-size:12px;color:#6b6b78">
    Model predicts {b['home_team']} wins by <b style="color:#e8e8ec">{b['pred_home_margin']:+.1f}</b> pts &nbsp;·&nbsp;
    Spread: {b['home_team']} {f"{b['home_point']:+.1f}" if b['home_point'] is not None else "N/A"}
  </div>
</div>""", unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='color:#6b6b78;font-size:13px;padding:1rem 0'>"
            "No ATS value found today — all lines appear fairly priced.</div>",
            unsafe_allow_html=True
        )

    # All games ATS table
    rows_html = ""
    for _, g in spread_preds.iterrows():
        home = g["home_team"]; away = g["away_team"]
        home_pt  = g.get("home_point")
        away_pt  = g.get("away_point")
        pred_m   = float(g.get("pred_home_margin", 0))
        hcp      = float(g.get("home_cover_prob", 0.5))
        acp      = float(g.get("away_cover_prob", 0.5))
        he       = float(g.get("home_ats_edge", 0))
        ae       = float(g.get("away_ats_edge", 0))
        hv       = int(g.get("home_ats_value", 0))
        av       = int(g.get("away_ats_value", 0))

        home_spr = f"{home_pt:+.1f}" if home_pt is not None else "—"
        away_spr = f"{away_pt:+.1f}" if away_pt is not None else "—"

        h_ec = "ep" if he > MIN_EDGE else "en"
        a_ec = "ep" if ae > MIN_EDGE else "en"

        badge = ""
        if hv:  badge = f'<span class="vbadge">VALUE {home} {home_spr} | {he:+.1%}</span>'
        elif av: badge = f'<span class="vbadge">VALUE {away} {away_spr} | {ae:+.1%}</span>'

        rows_html += f"""
<div class="game-card {'has-value' if (hv or av) else 'no-value'}" style="padding:1rem 1.25rem">
  <div style="font-size:14px;font-weight:600;color:#e8e8ec;margin-bottom:4px">{away} @ {home}</div>
  <div style="font-size:11px;color:#6b6b78;margin-bottom:.75rem">
    Pred margin: <b style="color:#e8e8ec">{pred_m:+.1f}</b> &nbsp;·&nbsp;
    {home} {home_spr} / {away} {away_spr}
  </div>
  <div style="display:flex;padding:4px 0;font-size:11px;color:#44444f;letter-spacing:.04em;text-transform:uppercase;border-bottom:1px solid #1e1e28">
    <div style="flex:1">Team</div><div style="width:55px;text-align:right">Spread</div>
    <div style="width:65px;text-align:right">P(cover)</div><div style="width:65px;text-align:right">ATS edge</div>
  </div>
  <div class="prob-row"><div class="prob-team {'vt' if hv else ''}">{home}</div>
    <div class="prob-book">{home_spr}</div>
    <div class="prob-model">{hcp:.1%}</div>
    <div class="prob-edge {h_ec}">{he:+.1%}</div>
  </div>
  <div class="prob-row"><div class="prob-team {'vt' if av else ''}">{away}</div>
    <div class="prob-book">{away_spr}</div>
    <div class="prob-model">{acp:.1%}</div>
    <div class="prob-edge {a_ec}">{ae:+.1%}</div>
  </div>
  {badge}
</div>"""

    if rows_html:
        st.markdown(rows_html, unsafe_allow_html=True)


def _get_best_ats(spread_preds: pd.DataFrame):
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
            if val != 1 or edge < MIN_EDGE or kelly < 0.005:
                continue
            opp_side = "away" if side == "home" else "home"
            candidates.append({
                "side":            side,
                "bet_team":        g["home_team"] if side == "home" else g["away_team"],
                "home_team":       g["home_team"],
                "away_team":       g["away_team"],
                "commence_time":   g.get("commence_time", ""),
                "bookmaker":       g.get("bookmaker", ""),
                "spread":          g.get(f"{side}_point"),
                "home_point":      g.get("home_point"),
                "pred_margin":     float(g.get("pred_home_margin", 0)),
                "pred_home_margin":float(g.get("pred_home_margin", 0)),
                "cover_prob":      prob,
                "fair_prob":       float(g.get(f"{side}_cover_fair", 0.5)),
                "edge":            edge,
                "kelly":           kelly,
                "price":           price,
            })
    if not candidates:
        return None
    candidates.sort(key=lambda x: x["edge"], reverse=True)
    return candidates[0]


def _render_totals_section(today: str):
    totals_preds = _load(
        "SELECT * FROM totals_predictions WHERE predict_date=? ORDER BY commence_time",
        params=(today,)
    )

    st.markdown("<div class='sh'>🎯 Totals — Over/Under</div>", unsafe_allow_html=True)

    if totals_preds.empty:
        st.info("No totals predictions yet. Run `python totals_predict.py` to generate them.")
        return

    best = _get_best_total(totals_preds)

    if best:
        b = best
        color = "#f59e0b"
        side_label = "OVER" if b["side"] == "over" else "UNDER"
        line_str   = f"{b['total_line']:.1f}" if b["total_line"] is not None else "N/A"
        st.markdown(f"""
<div class="best-bet-card value" style="border-color:{color}">
  <div class="bb-tier-value" style="color:{color}">🎯 TOTALS VALUE BET</div>
  <div class="bb-matchup">{b['away_team']} @ {b['home_team']}</div>
  <div class="bb-meta">Tip: {_tip_et(b['commence_time'])} · {str(b['bookmaker']).upper()}</div>
  <div class="bb-pick-value" style="color:{color}">{side_label} {line_str} &nbsp;({_fmt(b['price'])})</div>
  <div style="display:flex;gap:12px;margin:1.25rem 0;flex-wrap:wrap">
    <div class="stat-pill"><div class="stat-pill-val">{b['ou_prob']:.1%}</div><div class="stat-pill-lbl">P({side_label.lower()})</div></div>
    <div class="stat-pill"><div class="stat-pill-val" style="color:{color}">{b['edge']:+.1%}</div><div class="stat-pill-lbl">Edge</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{b['fair_prob']:.1%}</div><div class="stat-pill-lbl">Book implied</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{b['pred_total']:.1f}</div><div class="stat-pill-lbl">Pred total</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{b['kelly']*100:.1f}%</div><div class="stat-pill-lbl">Kelly stake</div></div>
  </div>
  <div style="border-top:1px solid #1e1e28;padding-top:.8rem;font-size:12px;color:#6b6b78">
    Model predicts <b style="color:#e8e8ec">{b['pred_total']:.1f}</b> total pts &nbsp;·&nbsp;
    Line: <b style="color:#e8e8ec">{line_str}</b>
  </div>
</div>""", unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='color:#6b6b78;font-size:13px;padding:1rem 0'>"
            "No totals value found today — all lines appear fairly priced.</div>",
            unsafe_allow_html=True
        )

    # All games totals table
    rows_html = ""
    for _, g in totals_preds.iterrows():
        home = g["home_team"]; away = g["away_team"]
        line      = g.get("total_line")
        pred_t    = float(g.get("pred_total", 0))
        over_p    = float(g.get("over_prob", 0.5))
        under_p   = float(g.get("under_prob", 0.5))
        over_e    = float(g.get("over_edge", 0))
        under_e   = float(g.get("under_edge", 0))
        ov        = int(g.get("over_value", 0))
        uv        = int(g.get("under_value", 0))

        line_str  = f"{line:.1f}" if line is not None else "—"
        over_ec   = "ep" if over_e  > MIN_EDGE else "en"
        under_ec  = "ep" if under_e > MIN_EDGE else "en"

        badge = ""
        if ov:   badge = f'<span class="vbadge" style="background:#f59e0b20;color:#f59e0b">OVER {line_str} | {over_e:+.1%}</span>'
        elif uv: badge = f'<span class="vbadge" style="background:#f59e0b20;color:#f59e0b">UNDER {line_str} | {under_e:+.1%}</span>'

        rows_html += f"""
<div class="game-card {'has-value' if (ov or uv) else 'no-value'}" style="padding:1rem 1.25rem">
  <div style="font-size:14px;font-weight:600;color:#e8e8ec;margin-bottom:4px">{away} @ {home}</div>
  <div style="font-size:11px;color:#6b6b78;margin-bottom:.75rem">
    Pred total: <b style="color:#e8e8ec">{pred_t:.1f}</b> &nbsp;·&nbsp; Line: <b style="color:#e8e8ec">{line_str}</b>
  </div>
  <div style="display:flex;padding:4px 0;font-size:11px;color:#44444f;letter-spacing:.04em;text-transform:uppercase;border-bottom:1px solid #1e1e28">
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


def _render_props_section(today: str):
    PROPS_MIN_EDGE = 0.08
    props_preds = _load(
        "SELECT * FROM props_predictions WHERE predict_date=? ORDER BY over_edge DESC",
        params=(today,)
    )

    st.markdown("<div class='sh'>🎲 Player Props — Points</div>", unsafe_allow_html=True)

    if props_preds.empty:
        st.info("No props predictions yet. Run `python props_odds.py` then `python props_predict.py`.")
        return

    best = _get_best_prop(props_preds, PROPS_MIN_EDGE)

    if best:
        b = best
        color = "#ec4899"
        side_label = "OVER" if b["side"] == "over" else "UNDER"
        home = b["home_team"].split()[-1]
        away = b["away_team"].split()[-1]
        st.markdown(f"""
<div class="best-bet-card value" style="border-color:{color}">
  <div class="bb-tier-value" style="color:{color}">🎲 PROPS VALUE BET</div>
  <div class="bb-matchup">{b['player_name']}</div>
  <div class="bb-meta">{away} @ {home} &nbsp;·&nbsp; Points &nbsp;·&nbsp; {str(b['bookmaker']).upper()}</div>
  <div class="bb-pick-value" style="color:{color}">{side_label} {b['line']} pts &nbsp;({_fmt(b['price'])})</div>
  <div style="display:flex;gap:12px;margin:1.25rem 0;flex-wrap:wrap">
    <div class="stat-pill"><div class="stat-pill-val">{b['ou_prob']:.1%}</div><div class="stat-pill-lbl">P({side_label.lower()})</div></div>
    <div class="stat-pill"><div class="stat-pill-val" style="color:{color}">{b['edge']:+.1%}</div><div class="stat-pill-lbl">Edge</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{b['fair_prob']:.1%}</div><div class="stat-pill-lbl">Book implied</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{b['pred_pts']:.1f}</div><div class="stat-pill-lbl">Pred pts</div></div>
    <div class="stat-pill"><div class="stat-pill-val">{b['kelly']*100:.1f}%</div><div class="stat-pill-lbl">Kelly stake</div></div>
  </div>
  <div style="border-top:1px solid #1e1e28;padding-top:.8rem;font-size:12px;color:#6b6b78">
    Model predicts <b style="color:#e8e8ec">{b['pred_pts']:.1f}</b> pts &nbsp;·&nbsp;
    Line: <b style="color:#e8e8ec">{b['line']}</b>
  </div>
</div>""", unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='color:#6b6b78;font-size:13px;padding:1rem 0'>"
            "No props value found today — all lines appear fairly priced.</div>",
            unsafe_allow_html=True
        )

    # All value props table
    value_props = props_preds[
        (props_preds["over_value"] == 1) | (props_preds["under_value"] == 1)
    ]
    if not value_props.empty:
        rows_html = ""
        for _, g in value_props.iterrows():
            home = g["home_team"].split()[-1]
            away = g["away_team"].split()[-1]
            over_e  = float(g.get("over_edge", 0))
            under_e = float(g.get("under_edge", 0))
            ov = int(g.get("over_value", 0))
            uv = int(g.get("under_value", 0))
            side_str = f"OVER {g['line']}" if ov else f"UNDER {g['line']}"
            edge_val = over_e if ov else under_e
            price    = g.get("over_price") if ov else g.get("under_price")
            prob     = float(g.get("over_prob", 0)) if ov else float(g.get("under_prob", 0))
            actual_html = ""
            if pd.notna(g.get("actual_pts")):
                actual = float(g["actual_pts"])
                won = (ov and actual > float(g["line"])) or (uv and actual <= float(g["line"]))
                c = "#22c55e" if won else "#ef4444"
                actual_html = f'<span style="color:{c};font-size:11px;font-weight:600">{"✓" if won else "✗"} {actual:.0f} pts</span>'
            rows_html += f"""
<div class="game-card has-value" style="padding:.875rem 1.25rem">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <div style="font-size:14px;font-weight:600;color:#e8e8ec">{g['player_name']}</div>
      <div style="font-size:11px;color:#6b6b78">{away} @ {home} &nbsp;·&nbsp; Pred: {float(g.get('pred_pts',0)):.1f} pts</div>
    </div>
    <div style="text-align:right">
      <div style="color:#ec4899;font-weight:700;font-size:13px">{side_str} &nbsp;{_fmt(price)}</div>
      <div style="font-size:11px;color:#6b6b78">P: {prob:.1%} &nbsp;·&nbsp; Edge: <span style="color:#ec4899">{edge_val:+.1%}</span></div>
    </div>
    {actual_html}
  </div>
</div>"""
        st.markdown(rows_html, unsafe_allow_html=True)


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
            if val != 1 or edge < min_edge or kelly < 0.005:
                continue
            candidates.append({
                "side":         side,
                "player_name":  g["player_name"],
                "home_team":    g["home_team"],
                "away_team":    g["away_team"],
                "bookmaker":    g.get("bookmaker", ""),
                "line":         g.get("line"),
                "pred_pts":     float(g.get("pred_pts", 0)),
                "ou_prob":      prob,
                "fair_prob":    float(g.get(f"{side}_fair", 0.5)),
                "edge":         edge,
                "kelly":        kelly,
                "price":        price,
            })
    if not candidates:
        return None
    candidates.sort(key=lambda x: x["edge"], reverse=True)
    return candidates[0]


def _get_best_total(totals_preds: pd.DataFrame):
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
            if val != 1 or edge < MIN_EDGE or kelly < 0.005:
                continue
            candidates.append({
                "side":         side,
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
    if not candidates:
        return None
    candidates.sort(key=lambda x: x["edge"], reverse=True)
    return candidates[0]
