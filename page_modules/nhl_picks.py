# ── page_modules/nhl_picks.py ─────────────────────────────────────────────────
# NHL Picks page — moneyline, puck line, and totals value bets.

import sqlite3
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timezone
from nhl_config import NHL_DB_PATH

# ── Helpers ───────────────────────────────────────────────────────────────────

def _conn():
    return sqlite3.connect(NHL_DB_PATH, check_same_thread=False)

def _composite(edge, prob, kelly):
    return 0.40 * edge + 0.35 * max(0.0, prob - 0.50) + 0.25 * kelly

def _fmt(price):
    try:
        p = int(float(price))
        return f"+{p}" if p > 0 else str(p)
    except Exception:
        return "N/A"

def _et(utc_str):
    try:
        from datetime import timezone, timedelta
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        et = dt.astimezone(timezone(timedelta(hours=-4)))
        return et.strftime("%-I:%M %p ET")
    except Exception:
        return utc_str or "TBD"

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def _load_ml():
    try:
        conn = _conn()
        df = pd.read_sql("""
            SELECT * FROM nhl_predictions
            WHERE predict_date = date('now','localtime')
            ORDER BY commence_time ASC
        """, conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def _load_spread():
    try:
        conn = _conn()
        df = pd.read_sql("""
            SELECT * FROM nhl_spread_predictions
            WHERE predict_date = date('now','localtime')
            ORDER BY commence_time ASC
        """, conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def _load_totals():
    try:
        conn = _conn()
        df = pd.read_sql("""
            SELECT * FROM nhl_totals_predictions
            WHERE predict_date = date('now','localtime')
            ORDER BY commence_time ASC
        """, conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

# ── Top-pick helpers ──────────────────────────────────────────────────────────

def _get_best_ml(preds, n=2):
    rows = []
    for _, r in preds.iterrows():
        for side in ["home", "away"]:
            if not r.get(f"{side}_value", 0):
                continue
            edge  = float(r.get(f"{side}_edge", 0))
            prob  = float(r.get(f"model_{side}_prob", 0))
            kelly = float(r.get(f"{side}_kelly", 0))
            score = _composite(edge, prob, kelly)
            rows.append({**r.to_dict(), "_side": side, "_score": score,
                         "_team": r[f"{side}_team"], "_edge": edge,
                         "_prob": prob, "_kelly": kelly,
                         "_price": r[f"{side}_price"]})
    return sorted(rows, key=lambda x: x["_score"], reverse=True)[:n]

def _get_best_spread(preds, n=2):
    rows = []
    for _, r in preds.iterrows():
        for side in ["home", "away"]:
            if not r.get(f"{side}_value", 0):
                continue
            edge  = float(r.get(f"{side}_edge", 0))
            prob  = float(r.get(f"model_{side}_cover_prob", 0))
            kelly = float(r.get(f"{side}_kelly", 0))
            score = _composite(edge, prob, kelly)
            pt    = r.get(f"{side}_point", -1.5 if side == "home" else 1.5)
            rows.append({**r.to_dict(), "_side": side, "_score": score,
                         "_team": r[f"{side}_team"], "_edge": edge,
                         "_prob": prob, "_kelly": kelly,
                         "_price": r[f"{side}_price"], "_point": pt})
    return sorted(rows, key=lambda x: x["_score"], reverse=True)[:n]

def _get_best_totals(preds, n=2):
    rows = []
    for _, r in preds.iterrows():
        for side in ["over", "under"]:
            if not r.get(f"{side}_value", 0):
                continue
            edge  = float(r.get(f"{side}_edge", 0))
            prob  = float(r.get(f"{side}_prob", 0))
            kelly = float(r.get(f"{side}_kelly", 0))
            score = _composite(edge, prob, kelly)
            rows.append({**r.to_dict(), "_side": side, "_score": score,
                         "_edge": edge, "_prob": prob, "_kelly": kelly,
                         "_price": r[f"{side}_price"]})
    return sorted(rows, key=lambda x: x["_score"], reverse=True)[:n]

# ── Card HTML ─────────────────────────────────────────────────────────────────

def _ml_card_html(b, rank):
    medal = ["🥇", "🥈"][rank] if rank < 2 else "🏒"
    matchup = f"{b['away_team']} @ {b['home_team']}"
    price   = _fmt(b["_price"])
    edge_pct= f"{b['_edge']:.1%}"
    prob_pct= f"{b['_prob']:.1%}"
    kelly_pct = f"{b['_kelly']:.1%}"
    game_time = _et(b.get("commence_time", ""))
    return f"""
    <div style="background:#131d2e;border:1px solid #1e2d42;border-radius:12px;
                padding:1.1rem 1.2rem;margin-bottom:.5rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.6rem;">
        <span style="font-size:.72rem;color:#7a8fa8;letter-spacing:.08em;">
          {medal} BEST PICK #{rank+1}
        </span>
        <span style="font-size:.7rem;color:#7a8fa8;">{game_time}</span>
      </div>
      <div style="font-size:1.05rem;font-weight:700;color:#f0f2f5;margin-bottom:.25rem;">
        {b['_team']}
      </div>
      <div style="font-size:.8rem;color:#8090a8;margin-bottom:.8rem;">{matchup}</div>
      <div style="display:flex;gap:.6rem;flex-wrap:wrap;">
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.25rem .55rem;font-size:.75rem;color:#60a5fa;">
          {price}
        </span>
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.25rem .55rem;font-size:.75rem;color:#22c55e;">
          Edge {edge_pct}
        </span>
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.25rem .55rem;font-size:.75rem;color:#96aec8;">
          Model {prob_pct}
        </span>
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.25rem .55rem;font-size:.75rem;color:#a78bfa;">
          Kelly {kelly_pct}
        </span>
      </div>
    </div>"""

def _spread_card_html(b, rank):
    medal   = ["🥇", "🥈"][rank] if rank < 2 else "🏒"
    matchup = f"{b['away_team']} @ {b['home_team']}"
    pt      = b.get("_point", -1.5)
    label   = f"{b['_team']} ({_fmt(pt)})"
    price   = _fmt(b["_price"])
    edge_pct= f"{b['_edge']:.1%}"
    prob_pct= f"{b['_prob']:.1%}"
    game_time = _et(b.get("commence_time", ""))
    return f"""
    <div style="background:#131d2e;border:1px solid #1e2d42;border-radius:12px;
                padding:1.1rem 1.2rem;margin-bottom:.5rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.6rem;">
        <span style="font-size:.72rem;color:#7a8fa8;letter-spacing:.08em;">
          {medal} PUCK LINE #{rank+1}
        </span>
        <span style="font-size:.7rem;color:#7a8fa8;">{game_time}</span>
      </div>
      <div style="font-size:1.05rem;font-weight:700;color:#f0f2f5;margin-bottom:.25rem;">
        {label}
      </div>
      <div style="font-size:.8rem;color:#8090a8;margin-bottom:.8rem;">{matchup}</div>
      <div style="display:flex;gap:.6rem;flex-wrap:wrap;">
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.25rem .55rem;font-size:.75rem;color:#60a5fa;">{price}</span>
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.25rem .55rem;font-size:.75rem;color:#22c55e;">Edge {edge_pct}</span>
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.25rem .55rem;font-size:.75rem;color:#96aec8;">Model {prob_pct}</span>
      </div>
    </div>"""

def _totals_card_html(b, rank):
    medal   = ["🥇", "🥈"][rank] if rank < 2 else "🏒"
    matchup = f"{b['away_team']} @ {b['home_team']}"
    line    = b.get("book_line", "?")
    pred    = b.get("pred_total", "?")
    label   = f"{b['_side'].upper()} {line}"
    price   = _fmt(b["_price"])
    edge_pct= f"{b['_edge']:.1%}"
    game_time = _et(b.get("commence_time", ""))
    try:
        pred_str = f"{float(pred):.2f}"
    except Exception:
        pred_str = str(pred)
    return f"""
    <div style="background:#131d2e;border:1px solid #1e2d42;border-radius:12px;
                padding:1.1rem 1.2rem;margin-bottom:.5rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.6rem;">
        <span style="font-size:.72rem;color:#7a8fa8;letter-spacing:.08em;">
          {medal} TOTALS #{rank+1}
        </span>
        <span style="font-size:.7rem;color:#7a8fa8;">{game_time}</span>
      </div>
      <div style="font-size:1.05rem;font-weight:700;color:#f0f2f5;margin-bottom:.25rem;">
        {label}
      </div>
      <div style="font-size:.8rem;color:#8090a8;margin-bottom:.8rem;">{matchup}</div>
      <div style="display:flex;gap:.6rem;flex-wrap:wrap;">
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.25rem .55rem;font-size:.75rem;color:#60a5fa;">{price}</span>
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.25rem .55rem;font-size:.75rem;color:#22c55e;">Edge {edge_pct}</span>
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.25rem .55rem;font-size:.75rem;color:#f59e0b;">Pred {pred_str}</span>
      </div>
    </div>"""

# ── Game row renderers ────────────────────────────────────────────────────────

def _game_row_ml(r):
    cols = st.columns([2.5, 2.5, 1.2, 1.2, 1, 1, 1])
    matchup = f"{r['away_team']} @ {r['home_team']}"
    cols[0].markdown(f"<span style='color:#f0f2f5;font-size:.85rem;'>{matchup}</span>",
                     unsafe_allow_html=True)
    cols[1].markdown(f"<span style='color:#8090a8;font-size:.8rem;'>{_et(r.get('commence_time',''))}</span>",
                     unsafe_allow_html=True)
    for i, side in enumerate(["home", "away"]):
        team  = r[f"{side}_team"]
        prob  = f"{float(r.get(f'model_{side}_prob', 0)):.1%}"
        edge  = float(r.get(f"{side}_edge", 0))
        price = _fmt(r.get(f"{side}_price"))
        val   = r.get(f"{side}_value", 0)
        color = "#22c55e" if val else "#8090a8"
        badge = "✓ VALUE" if val else ""
        cols[2 + i].markdown(
            f"<span style='color:{color};font-size:.8rem;'>{team} {badge}</span>",
            unsafe_allow_html=True)
        cols[4 + i].markdown(
            f"<span style='color:#96aec8;font-size:.8rem;'>{prob}</span>",
            unsafe_allow_html=True)
    edge_h = float(r.get("home_edge", 0))
    edge_a = float(r.get("away_edge", 0))
    best_edge = max(edge_h, edge_a)
    cols[6].markdown(
        f"<span style='color:#f59e0b;font-size:.8rem;'>{best_edge:.1%}</span>",
        unsafe_allow_html=True)

def _game_row_spread(r):
    cols = st.columns([2.5, 2.5, 1.5, 1.5, 1, 1])
    matchup = f"{r['away_team']} @ {r['home_team']}"
    cols[0].markdown(f"<span style='color:#f0f2f5;font-size:.85rem;'>{matchup}</span>",
                     unsafe_allow_html=True)
    cols[1].markdown(f"<span style='color:#8090a8;font-size:.8rem;'>{_et(r.get('commence_time',''))}</span>",
                     unsafe_allow_html=True)
    for i, side in enumerate(["home", "away"]):
        team  = r[f"{side}_team"]
        pt    = r.get(f"{side}_point", -1.5 if side == "home" else 1.5)
        price = _fmt(r.get(f"{side}_price"))
        val   = r.get(f"{side}_value", 0)
        color = "#22c55e" if val else "#8090a8"
        badge = " ✓" if val else ""
        cols[2 + i].markdown(
            f"<span style='color:{color};font-size:.8rem;'>{team} ({_fmt(pt)}) {price}{badge}</span>",
            unsafe_allow_html=True)
    edge_h = float(r.get("home_edge", 0))
    edge_a = float(r.get("away_edge", 0))
    cols[4].markdown(
        f"<span style='color:#f59e0b;font-size:.8rem;'>{max(edge_h,edge_a):.1%}</span>",
        unsafe_allow_html=True)

def _game_row_totals(r):
    cols = st.columns([2.5, 2, 1.2, 1.2, 1.2, 1.2, 1])
    matchup = f"{r['away_team']} @ {r['home_team']}"
    cols[0].markdown(f"<span style='color:#f0f2f5;font-size:.85rem;'>{matchup}</span>",
                     unsafe_allow_html=True)
    cols[1].markdown(f"<span style='color:#8090a8;font-size:.8rem;'>{_et(r.get('commence_time',''))}</span>",
                     unsafe_allow_html=True)
    line = r.get("book_line", "?")
    pred = r.get("pred_total", "?")
    try: pred_str = f"{float(pred):.2f}"
    except Exception: pred_str = str(pred)
    cols[2].markdown(f"<span style='color:#96aec8;font-size:.8rem;'>O/U {line}</span>",
                     unsafe_allow_html=True)
    cols[3].markdown(f"<span style='color:#f59e0b;font-size:.8rem;'>Pred {pred_str}</span>",
                     unsafe_allow_html=True)
    for i, side in enumerate(["over", "under"]):
        val   = r.get(f"{side}_value", 0)
        price = _fmt(r.get(f"{side}_price"))
        edge  = float(r.get(f"{side}_edge", 0))
        color = "#22c55e" if val else "#8090a8"
        cols[4 + i].markdown(
            f"<span style='color:{color};font-size:.8rem;'>{side.upper()} {price}</span>",
            unsafe_allow_html=True)
    best_edge = max(float(r.get("over_edge", 0)), float(r.get("under_edge", 0)))
    cols[6].markdown(
        f"<span style='color:#f59e0b;font-size:.8rem;'>{best_edge:.1%}</span>",
        unsafe_allow_html=True)

# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
<style>
.page-header{
  background:linear-gradient(135deg,#0c1829 0%,#0f2240 60%,#0c1829 100%);
  border:1px solid #1e2d42;border-radius:14px;padding:1.4rem 1.6rem;margin-bottom:1.4rem;
}
.ph-tag{
  display:inline-block;background:rgba(14,165,233,.15);
  color:#38bdf8;border:1px solid rgba(14,165,233,.35);
  border-radius:20px;padding:.2rem .75rem;font-size:.72rem;
  letter-spacing:.1em;text-transform:uppercase;margin-bottom:.6rem;
}
.ph-title{font-size:1.55rem;font-weight:700;color:#f0f2f5;line-height:1.2;}
.ph-sub{font-size:.85rem;color:#8090a8;margin-top:.35rem;}
.stat-strip{
  display:flex;gap:1rem;flex-wrap:wrap;
  background:#0f1828;border:1px solid #1e2d42;
  border-radius:10px;padding:.85rem 1rem;margin-bottom:1.2rem;
}
.stat-item{display:flex;flex-direction:column;gap:.15rem;min-width:90px;}
.stat-val{font-size:1.1rem;font-weight:700;color:#f0f2f5;}
.stat-lbl{font-size:.68rem;color:#7a8fa8;text-transform:uppercase;letter-spacing:.08em;}
.sec-hdr{
  font-size:.72rem;color:#7a8fa8;text-transform:uppercase;
  letter-spacing:.12em;padding:.4rem 0;margin:1rem 0 .4rem;
  border-bottom:1px solid #1e2d42;
}
.row-divider{border:none;border-top:1px solid #1e2d42;margin:.3rem 0;}
</style>
"""

# ── Main render ───────────────────────────────────────────────────────────────

def render():
    st.markdown(_CSS, unsafe_allow_html=True)

    today = datetime.now().strftime("%B %d, %Y")
    st.markdown(f"""
    <div class="page-header">
      <div class="ph-tag">🏒 Live Analysis</div>
      <div class="ph-title">NHL Picks</div>
      <div class="ph-sub">Moneyline · Puck Line · Totals — {today}</div>
    </div>""", unsafe_allow_html=True)

    ml_df     = _load_ml()
    spread_df = _load_spread()
    totals_df = _load_totals()

    # ── Stats strip ──────────────────────────────────────────────────────────
    n_games   = len(ml_df)
    n_ml_val  = int(ml_df["home_value"].fillna(0).sum() + ml_df["away_value"].fillna(0).sum()) if not ml_df.empty else 0
    n_pl_val  = int(spread_df["home_value"].fillna(0).sum() + spread_df["away_value"].fillna(0).sum()) if not spread_df.empty else 0
    n_tot_val = int(totals_df["over_value"].fillna(0).sum() + totals_df["under_value"].fillna(0).sum()) if not totals_df.empty else 0
    n_total   = n_ml_val + n_pl_val + n_tot_val

    st.markdown(f"""
    <div class="stat-strip">
      <div class="stat-item">
        <span class="stat-val">{n_games}</span>
        <span class="stat-lbl">Games Today</span>
      </div>
      <div class="stat-item">
        <span class="stat-val" style="color:#22c55e;">{n_total}</span>
        <span class="stat-lbl">Value Bets</span>
      </div>
      <div class="stat-item">
        <span class="stat-val">{n_ml_val}</span>
        <span class="stat-lbl">Moneyline</span>
      </div>
      <div class="stat-item">
        <span class="stat-val">{n_pl_val}</span>
        <span class="stat-lbl">Puck Line</span>
      </div>
      <div class="stat-item">
        <span class="stat-val">{n_tot_val}</span>
        <span class="stat-lbl">Totals</span>
      </div>
    </div>""", unsafe_allow_html=True)

    # ── Moneyline ─────────────────────────────────────────────────────────────
    st.markdown("<div class='sec-hdr'>⚡ Moneyline</div>", unsafe_allow_html=True)

    if not ml_df.empty:
        best_ml = _get_best_ml(ml_df, n=2)
        if best_ml:
            cc = st.columns(min(len(best_ml), 2))
            for i, b in enumerate(best_ml):
                cc[i].markdown(_ml_card_html(b, i), unsafe_allow_html=True)

        with st.expander(f"All moneyline games ({len(ml_df)})", expanded=False):
            for _, r in ml_df.iterrows():
                _game_row_ml(r)
                st.markdown("<hr class='row-divider'>", unsafe_allow_html=True)
    else:
        st.info("No NHL moneyline predictions yet. Run nhl_odds.py + nhl_predict.py.")

    # ── Puck Line ─────────────────────────────────────────────────────────────
    st.markdown("<div class='sec-hdr'>🏒 Puck Line (±1.5)</div>", unsafe_allow_html=True)

    if not spread_df.empty:
        best_pl = _get_best_spread(spread_df, n=2)
        if best_pl:
            cc = st.columns(min(len(best_pl), 2))
            for i, b in enumerate(best_pl):
                cc[i].markdown(_spread_card_html(b, i), unsafe_allow_html=True)

        with st.expander(f"All puck line games ({len(spread_df)})", expanded=False):
            for _, r in spread_df.iterrows():
                _game_row_spread(r)
                st.markdown("<hr class='row-divider'>", unsafe_allow_html=True)
    else:
        st.info("No NHL puck line predictions yet.")

    # ── Totals ────────────────────────────────────────────────────────────────
    st.markdown("<div class='sec-hdr'>🎯 Over / Under</div>", unsafe_allow_html=True)

    if not totals_df.empty:
        best_tot = _get_best_totals(totals_df, n=2)
        if best_tot:
            cc = st.columns(min(len(best_tot), 2))
            for i, b in enumerate(best_tot):
                cc[i].markdown(_totals_card_html(b, i), unsafe_allow_html=True)

        with st.expander(f"All totals games ({len(totals_df)})", expanded=False):
            for _, r in totals_df.iterrows():
                _game_row_totals(r)
                st.markdown("<hr class='row-divider'>", unsafe_allow_html=True)
    else:
        st.info("No NHL totals predictions yet.")
