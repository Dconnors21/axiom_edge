# ── page_modules/mlb_props.py ─────────────────────────────────────────────────
# MLB Player Props picks page — pitcher K's, batter hits, batter total bases.

import sqlite3
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timezone
from mlb_config import MLB_DB_PATH

_MARKET_CONFIGS = [
    {"market": "pitcher_strikeouts", "table": "mlb_props_predictions_k",
     "label": "⚾ Pitcher Strikeouts", "pred_col": "pred_ks",
     "pred_label": "Pred K's", "color": "#3b82f6", "icon": "🎯"},
    {"market": "batter_hits",        "table": "mlb_props_predictions_hits",
     "label": "🏏 Batter Hits",        "pred_col": "pred_hits",
     "pred_label": "Pred hits", "color": "#22c55e", "icon": "✅"},
    {"market": "batter_total_bases", "table": "mlb_props_predictions_tb",
     "label": "💥 Total Bases",        "pred_col": "pred_tb",
     "pred_label": "Pred TB",  "color": "#f59e0b", "icon": "💥"},
]


def _conn():
    return sqlite3.connect(MLB_DB_PATH, check_same_thread=False)


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
        from datetime import timedelta
        dt = datetime.fromisoformat(str(utc_str).replace("Z", "+00:00"))
        et = dt.astimezone(timezone(datetime.now(timezone.utc).utcoffset() or
                                    __import__("datetime").timezone.utc))
        from zoneinfo import ZoneInfo
        et = dt.astimezone(ZoneInfo("America/New_York"))
        return et.strftime("%-I:%M %p ET")
    except Exception:
        return ""


@st.cache_data(ttl=300)
def _load_market(table: str) -> pd.DataFrame:
    try:
        conn = _conn()
        df   = pd.read_sql(f"""
            SELECT * FROM {table}
            WHERE predict_date = date('now','localtime')
            ORDER BY commence_time ASC
        """, conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def _get_best(df: pd.DataFrame, n=2) -> list:
    rows = []
    for _, r in df.iterrows():
        for side in ["over", "under"]:
            if not r.get(f"{side}_value", 0):
                continue
            edge  = float(r.get(f"{side}_edge", 0))
            prob  = float(r.get(f"{side}_prob", 0))
            kelly = float(r.get(f"{side}_kelly", 0))
            score = _composite(edge, prob, kelly)
            rows.append({**r.to_dict(), "_side": side, "_score": score,
                         "_edge": edge, "_prob": prob, "_kelly": kelly,
                         "_price": r.get(f"{side}_price")})
    return sorted(rows, key=lambda x: x["_score"], reverse=True)[:n]


def _feat_card(b, rank, cfg):
    medal   = ["🥇", "🥈"][rank] if rank < 2 else cfg["icon"]
    matchup = f"{b['away_team']} @ {b['home_team']}"
    side    = b["_side"].upper()
    line    = b.get("line", "?")
    pred    = b.get(cfg["pred_col"], "?")
    try:    pred_str = f"{float(pred):.1f}"
    except: pred_str = str(pred)
    price   = _fmt(b["_price"])
    edge_pct = f"{b['_edge']:.1%}"
    game_time = _et(b.get("commence_time", ""))

    return f"""
    <div style="background:#131d2e;border:1px solid #1e2d42;border-radius:12px;
                padding:1.1rem 1.2rem;margin-bottom:.5rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem;">
        <span style="font-size:.72rem;color:#7a8fa8;letter-spacing:.08em;">
          {medal} BEST PICK #{rank+1}
        </span>
        <span style="font-size:.7rem;color:#7a8fa8;">{game_time}</span>
      </div>
      <div style="font-size:1rem;font-weight:700;color:#f0f2f5;margin-bottom:.15rem;">
        {b['player_name']}
      </div>
      <div style="font-size:.82rem;color:#8090a8;margin-bottom:.7rem;">
        {side} {line} · {matchup}
      </div>
      <div style="display:flex;gap:.5rem;flex-wrap:wrap;">
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.2rem .5rem;font-size:.74rem;color:{cfg['color']};">
          {price}
        </span>
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.2rem .5rem;font-size:.74rem;color:#22c55e;">
          Edge {edge_pct}
        </span>
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.2rem .5rem;font-size:.74rem;color:#96aec8;">
          {cfg['pred_label']}: {pred_str}
        </span>
        <span style="background:#0f1828;border:1px solid #1e2d42;border-radius:6px;
                     padding:.2rem .5rem;font-size:.74rem;color:#a78bfa;">
          Kelly {b['_kelly']:.1%}
        </span>
      </div>
    </div>"""


def _game_row(r, cfg):
    cols = st.columns([2, 2, 1, 1, 1.2, 1.2, 1])
    matchup = f"{r['away_team']} @ {r['home_team']}"
    pred    = r.get(cfg["pred_col"], "?")
    try:    pred_str = f"{float(pred):.1f}"
    except: pred_str = str(pred)

    cols[0].markdown(
        f"<span style='color:#f0f2f5;font-size:.85rem;font-weight:600'>{r['player_name']}</span>",
        unsafe_allow_html=True)
    cols[1].markdown(
        f"<span style='color:#8090a8;font-size:.8rem;'>{matchup}</span>",
        unsafe_allow_html=True)
    cols[2].markdown(
        f"<span style='color:#96aec8;font-size:.8rem;'>O/U {r.get('line','?')}</span>",
        unsafe_allow_html=True)
    cols[3].markdown(
        f"<span style='color:#f59e0b;font-size:.8rem;'>{cfg['pred_label']}: {pred_str}</span>",
        unsafe_allow_html=True)

    for i, side in enumerate(["over", "under"]):
        val   = r.get(f"{side}_value", 0)
        price = _fmt(r.get(f"{side}_price"))
        edge  = float(r.get(f"{side}_edge", 0))
        color = "#22c55e" if val else "#8090a8"
        label = f"{side.upper()} {price}" + (" ✓" if val else "")
        cols[4 + i].markdown(
            f"<span style='color:{color};font-size:.8rem;'>{label}</span>",
            unsafe_allow_html=True)

    best_edge = max(float(r.get("over_edge", 0)), float(r.get("under_edge", 0)))
    cols[6].markdown(
        f"<span style='color:#f59e0b;font-size:.8rem;'>{best_edge:.1%}</span>",
        unsafe_allow_html=True)


_CSS = """
<style>
.page-header{
  background:linear-gradient(135deg,#0c1829 0%,#0f2040 60%,#0c1829 100%);
  border:1px solid #1e2d42;border-radius:14px;padding:1.4rem 1.6rem;margin-bottom:1.4rem;
}
.ph-tag{
  display:inline-block;background:rgba(34,197,94,.12);
  color:#22c55e;border:1px solid rgba(34,197,94,.3);
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
.row-div{border:none;border-top:1px solid #1e2d42;margin:.3rem 0;}
</style>
"""


def render():
    st.markdown(_CSS, unsafe_allow_html=True)

    today = datetime.now().strftime("%B %d, %Y")
    st.markdown(f"""
    <div class="page-header">
      <div class="ph-tag">⚾ Props Analysis</div>
      <div class="ph-title">MLB Player Props</div>
      <div class="ph-sub">Pitcher Strikeouts · Batter Hits · Total Bases — {today}</div>
    </div>""", unsafe_allow_html=True)

    # Load all markets
    market_dfs = {cfg["market"]: _load_market(cfg["table"]) for cfg in _MARKET_CONFIGS}

    # Stats strip
    n_k   = int(market_dfs["pitcher_strikeouts"]["over_value"].fillna(0).sum() +
                market_dfs["pitcher_strikeouts"]["under_value"].fillna(0).sum()) \
            if not market_dfs["pitcher_strikeouts"].empty else 0
    n_h   = int(market_dfs["batter_hits"]["over_value"].fillna(0).sum() +
                market_dfs["batter_hits"]["under_value"].fillna(0).sum()) \
            if not market_dfs["batter_hits"].empty else 0
    n_tb  = int(market_dfs["batter_total_bases"]["over_value"].fillna(0).sum() +
                market_dfs["batter_total_bases"]["under_value"].fillna(0).sum()) \
            if not market_dfs["batter_total_bases"].empty else 0
    total_val = n_k + n_h + n_tb

    n_players = sum(len(df) for df in market_dfs.values())

    st.markdown(f"""
    <div class="stat-strip">
      <div class="stat-item"><span class="stat-val">{n_players}</span><span class="stat-lbl">Players Analyzed</span></div>
      <div class="stat-item"><span class="stat-val" style="color:#22c55e;">{total_val}</span><span class="stat-lbl">Value Bets</span></div>
      <div class="stat-item"><span class="stat-val">{n_k}</span><span class="stat-lbl">K Strikeout Picks</span></div>
      <div class="stat-item"><span class="stat-val">{n_h}</span><span class="stat-lbl">Hit Picks</span></div>
      <div class="stat-item"><span class="stat-val">{n_tb}</span><span class="stat-lbl">Total Base Picks</span></div>
    </div>""", unsafe_allow_html=True)

    # Render each market
    for cfg in _MARKET_CONFIGS:
        df = market_dfs[cfg["market"]]
        st.markdown(f"<div class='sec-hdr'>{cfg['label']}</div>", unsafe_allow_html=True)

        if df.empty:
            st.info(f"No {cfg['label']} predictions today. Run mlb_props_odds.py + mlb_props_predict.py.")
            continue

        # Featured cards
        best = _get_best(df, n=2)
        if best:
            cc = st.columns(min(len(best), 2))
            for i, b in enumerate(best):
                cc[i].markdown(_feat_card(b, i, cfg), unsafe_allow_html=True)

        # Full table in expander
        n_val = int(df["over_value"].fillna(0).sum() + df["under_value"].fillna(0).sum())
        with st.expander(f"All {cfg['label'].split()[-1].lower()} players ({len(df)}) · {n_val} value bets", expanded=False):
            # Column headers
            st.markdown("""
<div style="display:flex;gap:.5rem;padding:4px 0 6px;border-bottom:1px solid #1e2d42;
     font-size:10px;color:#7a8fa8;letter-spacing:.06em;text-transform:uppercase">
  <div style="flex:2">Player</div><div style="flex:2">Matchup</div>
  <div style="flex:1">Line</div><div style="flex:1">Prediction</div>
  <div style="flex:1.2">Over</div><div style="flex:1.2">Under</div>
  <div style="flex:1">Max Edge</div>
</div>""", unsafe_allow_html=True)
            for _, r in df.iterrows():
                _game_row(r, cfg)
                st.markdown("<hr class='row-div'>", unsafe_allow_html=True)
