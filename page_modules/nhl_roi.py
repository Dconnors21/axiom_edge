# ── page_modules/nhl_roi.py ───────────────────────────────────────────────────
# NHL ROI Tracker — cumulative P&L, monthly breakdown, bet log per strategy.

import sqlite3
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
from nhl_config import NHL_DB_PATH

# ── Strategy configs ──────────────────────────────────────────────────────────

NHL_ROI_CONFIGS = [
    {
        "key":       "ml",
        "table":     "nhl_bet_log",
        "label":     "Moneyline",
        "color":     "#38bdf8",
        "log_type":  "ml",
        "pred_col":  None,
        "pred_label": None,
    },
    {
        "key":       "pl",
        "table":     "nhl_ats_bet_log",
        "label":     "Puck Line (ATS)",
        "color":     "#22c55e",
        "log_type":  "spread",
        "pred_col":  None,
        "pred_label": None,
    },
    {
        "key":       "totals",
        "table":     "nhl_totals_bet_log",
        "label":     "Totals (O/U)",
        "color":     "#f59e0b",
        "log_type":  "totals",
        "pred_col":  "pred_total",
        "pred_label": "Pred total",
    },
]

_CHART = dict(
    paper_bgcolor="#131d2e",
    plot_bgcolor="#131d2e",
    font_color="#96aec8",
    xaxis=dict(gridcolor="#1a2840", color="#7a8fa8", showgrid=False),
    yaxis=dict(gridcolor="#1a2840", color="#7a8fa8", zeroline=True,
               zerolinecolor="#1e2d42"),
    margin=dict(l=30, r=20, t=30, b=30),
)

# ── Data helpers ──────────────────────────────────────────────────────────────

def _rgba(color: str, alpha: float = 0.08) -> str:
    """Convert a hex (#RRGGBB) or rgb(...) color to an rgba() string.
    Plotly's fillcolor rejects 8-digit hex (#RRGGBBAA), so build rgba() instead."""
    c = str(color).strip()
    if c.startswith("#") and len(c) >= 7:
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        return f"rgba({r},{g},{b},{alpha})"
    if c.startswith("rgb("):
        return c.replace("rgb(", "rgba(").replace(")", f",{alpha})")
    return c

def _conn():
    return sqlite3.connect(NHL_DB_PATH, check_same_thread=False)

@st.cache_data(ttl=300)
def _load(table: str) -> pd.DataFrame:
    try:
        conn = _conn()
        df   = pd.read_sql(f"SELECT * FROM {table} ORDER BY game_date ASC", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

def _summary_metrics(bets: pd.DataFrame):
    res = bets.dropna(subset=["won"])
    if res.empty:
        return 0, 0, 0.0, 0.0
    wins  = int(res["won"].sum())
    total = len(res)
    units = float(res["pnl"].sum())
    roi   = units / total * 100 if total > 0 else 0.0
    return wins, total, units, roi

def _cumulative_chart(bets: pd.DataFrame, color: str):
    res = bets.dropna(subset=["won"]).copy()
    if res.empty:
        return None
    res = res.sort_values("game_date")
    res["cum_pnl"] = res["pnl"].cumsum()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=res["game_date"], y=res["cum_pnl"],
        mode="lines", line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=_rgba(color, 0.08),
        name="Cumulative P&L",
        hovertemplate="%{x}<br>%{y:+.2f}u<extra></extra>",
    ))
    fig.update_layout(**_CHART, height=200, showlegend=False)
    return fig

def _monthly_chart(bets: pd.DataFrame, color: str):
    res = bets.dropna(subset=["won"]).copy()
    if res.empty:
        return None
    res["month"] = pd.to_datetime(res["game_date"]).dt.to_period("M").astype(str)
    monthly = res.groupby("month")["pnl"].sum().reset_index()
    colors  = [color if v >= 0 else "#ef4444" for v in monthly["pnl"]]
    fig = go.Figure(go.Bar(
        x=monthly["month"], y=monthly["pnl"],
        marker_color=colors,
        hovertemplate="%{x}<br>%{y:+.2f}u<extra></extra>",
    ))
    fig.update_layout(**_CHART, height=200, showlegend=False)
    return fig

def _edge_dist_chart(bets: pd.DataFrame, color: str):
    res = bets.dropna(subset=["won", "edge"]).copy()
    if res.empty or "edge" not in res.columns:
        return None
    bins  = pd.cut(res["edge"], bins=8)
    edges = res.groupby(bins, observed=True).agg(
        win_rate=("won", "mean"), count=("won", "count")
    ).reset_index()
    edges["bin_label"] = edges["edge"].astype(str)
    fig = go.Figure(go.Bar(
        x=edges["bin_label"], y=edges["win_rate"] * 100,
        marker_color=color,
        hovertemplate="%{x}<br>Win rate %{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(**{**_CHART, "height": 200, "showlegend": False,
                         "yaxis": {**_CHART["yaxis"], "ticksuffix": "%"}})
    return fig

def _bet_log_table(bets: pd.DataFrame, log_type: str, pred_col, pred_label):
    res = bets.dropna(subset=["won"]).copy().sort_values("game_date", ascending=False)
    if res.empty:
        st.info("No resolved bets yet.")
        return

    res["Result"] = res["won"].map({1: "✅ Win", 0: "❌ Loss"})
    res["P&L"]    = res["pnl"].map(lambda x: f"{x:+.3f}u")
    res["Edge"]   = res["edge"].map(lambda x: f"{float(x):.1%}" if pd.notna(x) else "—")
    res["Kelly"]  = res["kelly"].map(lambda x: f"{float(x):.1%}" if pd.notna(x) else "—")

    # Build display columns based on log type
    if log_type == "ml":
        res["Matchup"] = res["away_team"] + " @ " + res["home_team"]
        res["Bet"]     = res["bet_team"] + " " + res["bet_side"]
        display_cols   = ["game_date", "Matchup", "Bet", "odds", "Edge", "Kelly", "units", "Result", "P&L"]
    elif log_type == "spread":
        res["Matchup"] = res["away_team"] + " @ " + res["home_team"]
        spread_col = "spread" if "spread" in res.columns else "home_point"
        res["Bet"] = res["bet_team"] + " " + res.get(spread_col, "").astype(str)
        display_cols = ["game_date", "Matchup", "Bet", "odds", "Edge", "Kelly", "units", "Result", "P&L"]
    else:  # totals
        res["Matchup"] = res["away_team"] + " @ " + res["home_team"]
        res["Bet"]     = res["bet_side"].str.upper() + " " + res["line"].astype(str)
        if pred_col and pred_col in res.columns:
            res[pred_label] = res[pred_col].map(
                lambda x: f"{float(x):.2f}" if pd.notna(x) else "—"
            )
            display_cols = ["game_date", "Matchup", "Bet", pred_label, "odds", "Edge", "Kelly", "units", "Result", "P&L"]
        else:
            display_cols = ["game_date", "Matchup", "Bet", "odds", "Edge", "Kelly", "units", "Result", "P&L"]

    display_cols = [c for c in display_cols if c in res.columns]
    res_display = res[display_cols].rename(columns={"game_date": "Date", "units": "Units", "odds": "Odds"})
    st.dataframe(res_display, use_container_width=True, hide_index=True)


def _render_strategy_section(cfg: dict, bets: pd.DataFrame, i: int):
    wins, total, units, roi = _summary_metrics(bets)
    label_exp = (
        f"{cfg['label']} — {wins}-{total-wins} record · "
        f"{units:+.2f}u · ROI {roi:+.1f}%"
        if total > 0 else f"{cfg['label']} — no resolved bets yet"
    )

    with st.expander(label_exp, expanded=(i == 0)):
        if bets.empty:
            st.info(f"No {cfg['label']} bets logged yet. Run the pipeline to generate picks.")
            return

        # Metrics row
        clv_vals = bets["clv"].dropna() if "clv" in bets.columns else pd.Series([], dtype=float)
        avg_clv  = clv_vals.mean() if not clv_vals.empty else None
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Record",   f"{wins}-{total-wins}")
        c2.metric("Win Rate", f"{wins/total:.1%}" if total > 0 else "—")
        c3.metric("Units",    f"{units:+.2f}u")
        c4.metric("ROI",      f"{roi:+.1f}%")
        c5.metric("Avg CLV",  f"{avg_clv:+.1%}" if avg_clv is not None else "—")

        # Charts
        ch1, ch2 = st.columns(2)
        with ch1:
            fig = _cumulative_chart(bets, cfg["color"])
            if fig:
                st.markdown("**Cumulative P&L**")
                st.plotly_chart(fig, use_container_width=True)
        with ch2:
            fig2 = _monthly_chart(bets, cfg["color"])
            if fig2:
                st.markdown("**Monthly P&L**")
                st.plotly_chart(fig2, use_container_width=True)

        # Bet log
        st.markdown("**Bet Log**")
        _bet_log_table(bets, cfg["log_type"], cfg["pred_col"], cfg["pred_label"])


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
.ph-badge{
  display:inline-block;margin-left:.75rem;
  background:rgba(34,197,94,.12);color:#22c55e;
  border:1px solid rgba(34,197,94,.3);border-radius:20px;
  padding:.15rem .6rem;font-size:.7rem;vertical-align:middle;
}
</style>
"""

# ── Main render ───────────────────────────────────────────────────────────────

def render():
    st.markdown(_CSS, unsafe_allow_html=True)

    today = datetime.now().strftime("%B %d, %Y")
    st.markdown(f"""
    <div class="page-header">
      <div class="ph-tag">🏒 Performance</div>
      <div class="ph-title">
        NHL ROI Tracker
        <span class="ph-badge">3 strategies live</span>
      </div>
      <div class="ph-sub">Season-to-date performance across all NHL markets — {today}</div>
    </div>""", unsafe_allow_html=True)

    for i, cfg in enumerate(NHL_ROI_CONFIGS):
        bets = _load(cfg["table"])
        _render_strategy_section(cfg, bets, i)
