import sys, os
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sqlite3
from pathlib import Path
from config import DB_PATH

_CSS = """
<style>
.block-container{padding-top:0;padding-bottom:2rem;max-width:1400px}
[data-testid="metric-container"]{background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:.7rem 1rem}
[data-testid="metric-container"] label{color:#6b7a90!important;font-size:11px!important;letter-spacing:.06em;text-transform:uppercase}
[data-testid="stMetricValue"]{color:#f0f2f5!important;font-size:20px!important;font-weight:700!important}
.sh{font-size:11px;font-weight:700;letter-spacing:.1em;color:#8090a8;text-transform:uppercase;margin:1.25rem 0 .75rem;padding-bottom:6px;border-bottom:1px solid #1e2d42}
.roi-header{background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:1rem 1.5rem;margin-bottom:1.25rem;display:flex;align-items:center;justify-content:space-between}
.roi-title{font-size:20px;font-weight:700;color:#f0f2f5;letter-spacing:-.3px}
.roi-subtitle{font-size:12px;color:#5a7090;margin-top:3px}
.roi-badge{background:#0f1a2e;color:#3b82f6;border:1px solid #1e3a5f;border-radius:6px;font-size:11px;font-weight:700;padding:4px 12px;letter-spacing:.04em}
.strat-hdr{display:flex;align-items:center;gap:10px;margin-bottom:.875rem}
.strat-dot{width:9px;height:9px;border-radius:50%;flex-shrink:0;display:inline-block}
.strat-name{font-size:13px;font-weight:700;color:#c8d0dc;letter-spacing:.01em}
.strat-rec{font-size:11px;color:#5a7090;margin-left:auto}
</style>
"""

_CHART = dict(
    paper_bgcolor="#131d2e", plot_bgcolor="#131d2e",
    margin=dict(l=0, r=0, t=10, b=0),
    xaxis=dict(showgrid=False, color="#506070"),
    yaxis=dict(gridcolor="#1a2840", color="#506070", zeroline=False),
    legend=dict(font=dict(color="#6b7a90"), bgcolor="rgba(0,0,0,0)"),
    font=dict(color="#6b7a90"),
)

# Strategy config — drives combined chart + individual sections
ROI_CONFIGS = [
    {"key": "ml",     "table": "bet_log",              "label": "Moneyline",       "color": "#3b82f6", "log_type": "ml",     "pred_col": None,          "pred_label": None},
    {"key": "ats",    "table": "ats_bet_log",           "label": "ATS",             "color": "#22c55e", "log_type": "spread", "pred_col": None,          "pred_label": None},
    {"key": "totals", "table": "totals_bet_log",        "label": "Totals (O/U)",    "color": "#f59e0b", "log_type": "totals", "pred_col": "pred_total",  "pred_label": "Pred"},
    {"key": "pts",    "table": "props_bet_log",         "label": "Props — Points",  "color": "#ec4899", "log_type": "props",  "pred_col": "pred_pts",    "pred_label": "Pred pts"},
    {"key": "reb",    "table": "props_reb_bet_log",     "label": "Props — Reb",     "color": "#8b5cf6", "log_type": "props",  "pred_col": "pred_reb",    "pred_label": "Pred reb"},
    {"key": "ast",    "table": "props_ast_bet_log",     "label": "Props — Ast",     "color": "#f97316", "log_type": "props",  "pred_col": "pred_ast",    "pred_label": "Pred ast"},
    {"key": "threes", "table": "props_threes_bet_log",  "label": "Props — 3PM",     "color": "#06b6d4", "log_type": "props",  "pred_col": "pred_threes", "pred_label": "Pred 3PM"},
    {"key": "stl",    "table": "props_stl_bet_log",     "label": "Props — Stl",     "color": "#10b981", "log_type": "props",  "pred_col": "pred_stl",    "pred_label": "Pred STL"},
    {"key": "blk",    "table": "props_blk_bet_log",     "label": "Props — Blk",     "color": "#eab308", "log_type": "props",  "pred_col": "pred_blk",    "pred_label": "Pred BLK"},
]


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


def _summary_metrics(bets, color):
    if bets.empty:
        return
    wins     = (bets["result"] == "WIN").sum()
    total    = len(bets)
    units    = bets["profit_units"].sum()
    win_pct  = wins / total if total else 0
    avg_edge = bets["edge"].mean() if "edge" in bets.columns else 0
    clv_vals = bets["clv"].dropna() if "clv" in bets.columns else pd.Series([], dtype=float)
    avg_clv  = clv_vals.mean() if not clv_vals.empty else None

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Bets",       total)
    c2.metric("Win rate",   f"{win_pct:.1%}")
    c3.metric("Record",     f"{wins}W–{total-wins}L")
    c4.metric("Units P&L",  f"{units:+.3f}", delta_color="normal" if units >= 0 else "inverse")
    c5.metric("Avg edge",   f"{avg_edge:+.1%}")
    c6.metric("Avg CLV",    f"{avg_clv:+.1%}" if avg_clv is not None else "—")


def _cumulative_chart(bets, color):
    if bets.empty:
        return
    bets = bets.copy()
    bets["predict_date"] = pd.to_datetime(bets["predict_date"])
    bets["cumulative"]   = bets["profit_units"].cumsum()
    units = bets["profit_units"].sum()
    cl = color if units >= 0 else "#ef4444"
    _RGB = {
        "#3b82f6": "59,130,246",
        "#22c55e": "34,197,94",
        "#f59e0b": "245,158,11",
        "#ec4899": "236,72,153",
        "#8b5cf6": "139,92,246",
        "#f97316": "249,115,22",
        "#06b6d4": "6,182,212",
        "#10b981": "16,185,129",
        "#eab308": "234,179,8",
        "#ef4444": "239,68,68",
    }
    rgb = _RGB.get(cl, "239,68,68")
    fig = go.Figure()
    fig.add_scatter(x=bets["predict_date"], y=bets["cumulative"],
                    mode="lines", line=dict(color=cl, width=2),
                    fill="tozeroy", fillcolor=f"rgba({rgb},0.08)")
    fig.add_hline(y=0, line_color="#131a26", line_width=1)
    fig.update_layout(height=200, **_CHART)
    st.plotly_chart(fig, use_container_width=True)


def _monthly_and_edge(bets):
    if bets.empty:
        return
    bets = bets.copy()
    bets["predict_date"] = pd.to_datetime(bets["predict_date"])

    cl2, cr2 = st.columns(2)
    with cl2:
        st.markdown("<div class='sh'>Monthly P&L</div>", unsafe_allow_html=True)
        bets["month"] = bets["predict_date"].dt.to_period("M").astype(str)
        mo = bets.groupby("month").agg(
            bets=("result", "count"),
            wins=("result", lambda x: (x == "WIN").sum()),
            units=("profit_units", "sum")
        ).reset_index()
        colors = ["#22c55e" if u > 0 else "#ef4444" for u in mo["units"]]
        f2 = go.Figure(go.Bar(x=mo["month"], y=mo["units"],
                              marker_color=colors, marker_line_width=0))
        f2.add_hline(y=0, line_color="#131a26", line_width=1)
        f2.update_layout(height=190, **_CHART)
        st.plotly_chart(f2, use_container_width=True)

    with cr2:
        st.markdown("<div class='sh'>Edge distribution</div>", unsafe_allow_html=True)
        f3 = go.Figure()
        for result, color in [("WIN", "#22c55e"), ("LOSS", "#ef4444")]:
            sub = bets[bets["result"] == result]
            if not sub.empty and "edge" in sub.columns:
                f3.add_histogram(x=sub["edge"], name=result,
                                 marker_color=color, opacity=0.7,
                                 xbins=dict(size=0.01))
        f3.update_layout(barmode="overlay", height=190, **_CHART)
        st.plotly_chart(f3, use_container_width=True)


def _bet_log_strategy(bets, log_type, pred_col=None, pred_label=None):
    """Generic bet log — handles ml / spread / totals / props with one function."""
    if bets.empty:
        return
    st.markdown("<div class='sh'>Bet log</div>", unsafe_allow_html=True)

    if log_type == "ml":
        cols_map = {
            "predict_date": "Date", "bet_team": "Team",
            "edge": "Edge", "line": "Line",
            "kelly_stake": "Kelly", "result": "Result", "profit_units": "Units",
        }
    elif log_type == "spread":
        cols_map = {
            "predict_date": "Date", "bet_team": "Team",
            "spread": "Spread", "pred_margin": "Pred margin",
            "edge": "Edge", "line": "Line",
            "kelly_stake": "Kelly", "result": "Result", "profit_units": "Units",
        }
    elif log_type == "totals":
        cols_map = {
            "predict_date": "Date", "home_team": "Home", "away_team": "Away",
            "bet_side": "Side", "total_line": "Line", "pred_total": pred_label or "Pred",
            "edge": "Edge", "line": "Odds",
            "kelly_stake": "Kelly", "result": "Result", "profit_units": "Units",
        }
    else:  # props
        base = {
            "predict_date": "Date", "player_name": "Player",
            "bet_side": "Side", "line": "Line",
            "edge": "Edge", "price": "Odds",
            "kelly_stake": "Kelly", "result": "Result", "profit_units": "Units",
        }
        if pred_col:
            base[pred_col] = pred_label or "Pred"
        cols_map = base

    avail = {k: v for k, v in cols_map.items() if k in bets.columns}
    log   = bets[list(avail.keys())].copy().rename(columns=avail)
    log   = log.sort_values("Date", ascending=False)

    # Format columns
    for col, fmt in [
        ("Edge",        lambda x: f"{x:+.1%}" if pd.notna(x) else "—"),
        ("Kelly",       lambda x: f"{x:.1%}"  if pd.notna(x) else "—"),
        ("Units",       lambda x: f"{x:+.3f}" if pd.notna(x) else "—"),
        ("Line",        _fmt),
        ("Odds",        _fmt),
        ("Spread",      lambda x: f"{x:+.1f}" if pd.notna(x) else "—"),
        ("Pred margin", lambda x: f"{x:+.1f}" if pd.notna(x) else "—"),
    ]:
        if col in log.columns:
            log[col] = log[col].map(fmt)

    # Pred column (varies by market)
    pred_display = pred_label or "Pred"
    if pred_display in log.columns:
        log[pred_display] = log[pred_display].map(lambda x: f"{x:.1f}" if pd.notna(x) else "—")

    if "Side" in log.columns:
        log["Side"] = log["Side"].str.upper()

    st.dataframe(log, use_container_width=True, height=340, hide_index=True)


def _render_strategy_section(cfg, bets):
    """Render one strategy inside its expander."""
    color    = cfg["color"]
    log_type = cfg["log_type"]

    if bets.empty:
        st.info(f"No resolved {cfg['label']} bets yet. Results populate automatically after games finish.")
        return

    wins  = (bets["result"] == "WIN").sum()
    total = len(bets)
    units = bets["profit_units"].sum()
    rec   = f"{wins}W–{total-wins}L · {units:+.2f}u"

    st.markdown(
        f"<div class='strat-hdr'>"
        f"<span class='strat-dot' style='background:{color}'></span>"
        f"<span class='strat-name'>{cfg['label']}</span>"
        f"<span class='strat-rec'>{rec}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    _summary_metrics(bets, color)
    _cumulative_chart(bets, color)
    _monthly_and_edge(bets)
    _bet_log_strategy(bets, log_type=log_type,
                      pred_col=cfg.get("pred_col"), pred_label=cfg.get("pred_label"))


def render():
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── Load all bet logs ──────────────────────────────────────────────────────
    data = {}
    for cfg in ROI_CONFIGS:
        data[cfg["key"]] = _load(
            f"SELECT * FROM {cfg['table']} WHERE result IN ('WIN','LOSS') ORDER BY predict_date ASC"
        )

    # ── Combined summary strip ─────────────────────────────────────────────────
    all_bets  = sum(len(data[c["key"]]) for c in ROI_CONFIGS)
    all_units = sum(
        data[c["key"]]["profit_units"].sum() if not data[c["key"]].empty else 0
        for c in ROI_CONFIGS
    )
    all_wins  = sum(
        (data[c["key"]]["result"] == "WIN").sum() if not data[c["key"]].empty else 0
        for c in ROI_CONFIGS
    )

    st.markdown(
        f"<div class='roi-header'>"
        f"<div><div class='roi-title'>🏀 NBA ROI Tracker</div>"
        f"<div class='roi-subtitle'>Resolved bets across all 9 active strategies</div></div>"
        f"<div class='roi-badge'>{len(ROI_CONFIGS)} strategies live</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total bets",      all_bets)
    c2.metric("Combined win rate", f"{all_wins/all_bets:.1%}" if all_bets > 0 else "—")
    c3.metric("Combined units P&L", f"{all_units:+.3f}")
    c4.metric("Active strategies", len(ROI_CONFIGS))

    # ── Combined P&L chart ─────────────────────────────────────────────────────
    has_any = any(not data[c["key"]].empty for c in ROI_CONFIGS)
    if has_any:
        st.markdown("<div class='sh'>Combined P&L curve</div>", unsafe_allow_html=True)
        fig = go.Figure()
        for cfg in ROI_CONFIGS:
            df = data[cfg["key"]]
            if df.empty:
                continue
            d = df.copy()
            d["predict_date"] = pd.to_datetime(d["predict_date"])
            d["cumulative"]   = d["profit_units"].cumsum()
            fig.add_scatter(x=d["predict_date"], y=d["cumulative"],
                            mode="lines", name=cfg["label"],
                            line=dict(color=cfg["color"], width=2))
        fig.add_hline(y=0, line_color="#131a26", line_width=1)
        fig.update_layout(height=250, **_CHART)
        st.plotly_chart(fig, use_container_width=True)

    # ── Individual strategy sections ───────────────────────────────────────────
    st.markdown("<div class='sh'>Strategy breakdown</div>", unsafe_allow_html=True)

    for i, cfg in enumerate(ROI_CONFIGS):
        bets      = data[cfg["key"]]
        n         = len(bets)
        units_sum = bets["profit_units"].sum() if not bets.empty else 0
        wins_n    = (bets["result"] == "WIN").sum() if not bets.empty else 0
        label_exp = (
            f"{cfg['label']}  ·  "
            f"{wins_n}W–{n-wins_n}L  ·  {units_sum:+.2f}u"
            if n > 0 else f"{cfg['label']}  ·  no data"
        )
        with st.expander(label_exp, expanded=(i == 0)):
            _render_strategy_section(cfg, bets)
