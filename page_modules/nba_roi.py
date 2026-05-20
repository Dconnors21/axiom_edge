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
.block-container{padding-top:1.5rem;padding-bottom:2rem;max-width:1100px}
[data-testid="metric-container"]{background:#13131a;border:1px solid #1e1e28;border-radius:10px;padding:1rem 1.25rem}
[data-testid="metric-container"] label{color:#6b6b78!important;font-size:12px!important;letter-spacing:.05em;text-transform:uppercase}
[data-testid="stMetricValue"]{color:#e8e8ec!important;font-size:24px!important;font-weight:700!important}
.sh{font-size:11px;font-weight:600;letter-spacing:.1em;color:#44444f;text-transform:uppercase;margin:1.5rem 0 .75rem;padding-bottom:8px;border-bottom:1px solid #1e1e28}
.roi-section{background:#13131a;border:1px solid #1e1e28;border-radius:12px;padding:1.25rem 1.5rem;margin-bottom:1rem}
</style>
"""

_CHART = dict(
    paper_bgcolor="#13131a", plot_bgcolor="#13131a",
    margin=dict(l=0, r=0, t=10, b=0),
    xaxis=dict(showgrid=False, color="#44444f"),
    yaxis=dict(gridcolor="#1e1e28", color="#44444f", zeroline=False),
    legend=dict(font=dict(color="#9090a0"), bgcolor="rgba(0,0,0,0)"),
    font=dict(color="#9090a0"),
)


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

def _summary_metrics(bets, label, color):
    if bets.empty:
        st.caption(f"No {label} bets resolved yet.")
        return
    wins    = (bets["result"] == "WIN").sum()
    total   = len(bets)
    units   = bets["profit_units"].sum()
    win_pct = wins / total
    avg_edge = bets["edge"].mean() if "edge" in bets.columns else 0
    clv_vals = bets["clv"].dropna() if "clv" in bets.columns else pd.Series([], dtype=float)
    avg_clv  = clv_vals.mean() if not clv_vals.empty else None

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Bets",     total)
    c2.metric("Win rate", f"{win_pct:.1%}")
    c3.metric("Record",   f"{wins}W–{total-wins}L")
    uc = "normal" if units >= 0 else "inverse"
    c4.metric("Units P&L", f"{units:+.3f}", delta_color=uc)
    c5.metric("Avg edge",  f"{avg_edge:+.1%}")
    c6.metric("Avg CLV",   f"{avg_clv:+.1%}" if avg_clv is not None else "—")

def _cumulative_chart(bets, color):
    if bets.empty:
        return
    bets = bets.copy()
    bets["predict_date"] = pd.to_datetime(bets["predict_date"])
    bets["cumulative"]   = bets["profit_units"].cumsum()
    units = bets["profit_units"].sum()
    cl    = color if units >= 0 else "#ef4444"
    if cl == "#22c55e":   rgb = "34,197,94"
    elif cl == "#6366f1": rgb = "99,102,241"
    elif cl == "#f59e0b": rgb = "245,158,11"
    elif cl == "#ec4899": rgb = "236,72,153"
    else:                 rgb = "239,68,68"

    fig = go.Figure()
    fig.add_scatter(x=bets["predict_date"], y=bets["cumulative"],
                    mode="lines", line=dict(color=cl, width=2),
                    fill="tozeroy", fillcolor=f"rgba({rgb},0.08)")
    fig.add_hline(y=0, line_color="#333340", line_width=1)
    fig.update_layout(height=220, **_CHART)
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
            wins=("result", lambda x: (x=="WIN").sum()),
            units=("profit_units","sum")
        ).reset_index()
        colors = ["#22c55e" if u > 0 else "#ef4444" for u in mo["units"]]
        f2 = go.Figure(go.Bar(x=mo["month"], y=mo["units"],
                              marker_color=colors, marker_line_width=0))
        f2.add_hline(y=0, line_color="#333340", line_width=1)
        f2.update_layout(height=200, **_CHART)
        st.plotly_chart(f2, use_container_width=True)

    with cr2:
        st.markdown("<div class='sh'>Edge distribution</div>", unsafe_allow_html=True)
        f3 = go.Figure()
        for result, color in [("WIN","#22c55e"),("LOSS","#ef4444")]:
            sub = bets[bets["result"]==result]
            if not sub.empty and "edge" in sub.columns:
                f3.add_histogram(x=sub["edge"], name=result,
                                 marker_color=color, opacity=0.7,
                                 xbins=dict(size=0.01))
        f3.update_layout(barmode="overlay", height=200, **_CHART)
        st.plotly_chart(f3, use_container_width=True)

def _bet_log(bets, spread=False):
    if bets.empty:
        return
    st.markdown("<div class='sh'>Bet log</div>", unsafe_allow_html=True)
    if spread:
        cols_map = {
            "predict_date": "Date", "bet_team": "Team",
            "spread": "Spread", "pred_margin": "Pred margin",
            "edge": "Edge", "line": "Line",
            "kelly_stake": "Kelly", "result": "Result", "profit_units": "Units"
        }
    else:
        cols_map = {
            "predict_date": "Date", "bet_team": "Team",
            "edge": "Edge", "line": "Line",
            "kelly_stake": "Kelly", "result": "Result", "profit_units": "Units"
        }

    avail = {k: v for k, v in cols_map.items() if k in bets.columns}
    log   = bets[list(avail.keys())].copy().rename(columns=avail)
    log   = log.sort_values("Date", ascending=False)

    if "Edge" in log.columns:
        log["Edge"] = log["Edge"].map(lambda x: f"{x:+.1%}" if pd.notna(x) else "—")
    if "Kelly" in log.columns:
        log["Kelly"] = log["Kelly"].map(lambda x: f"{x:.1%}" if pd.notna(x) else "—")
    if "Units" in log.columns:
        log["Units"] = log["Units"].map(lambda x: f"{x:+.3f}" if pd.notna(x) else "—")
    if "Line" in log.columns:
        log["Line"] = log["Line"].map(_fmt)
    if "Spread" in log.columns:
        log["Spread"] = log["Spread"].map(lambda x: f"{x:+.1f}" if pd.notna(x) else "—")
    if "Pred margin" in log.columns:
        log["Pred margin"] = log["Pred margin"].map(lambda x: f"{x:+.1f}" if pd.notna(x) else "—")

    st.dataframe(log, use_container_width=True, height=360, hide_index=True)


def _bet_log_props(bets):
    if bets.empty:
        return
    st.markdown("<div class='sh'>Bet log</div>", unsafe_allow_html=True)
    cols_map = {
        "predict_date": "Date", "player_name": "Player",
        "bet_side": "Side", "line": "Line", "pred_pts": "Pred pts",
        "edge": "Edge", "price": "Odds",
        "kelly_stake": "Kelly", "result": "Result", "profit_units": "Units"
    }
    avail = {k: v for k, v in cols_map.items() if k in bets.columns}
    log   = bets[list(avail.keys())].copy().rename(columns=avail)
    log   = log.sort_values("Date", ascending=False)

    if "Side" in log.columns:
        log["Side"] = log["Side"].str.upper()
    if "Edge" in log.columns:
        log["Edge"] = log["Edge"].map(lambda x: f"{x:+.1%}" if pd.notna(x) else "—")
    if "Kelly" in log.columns:
        log["Kelly"] = log["Kelly"].map(lambda x: f"{x:.1%}" if pd.notna(x) else "—")
    if "Units" in log.columns:
        log["Units"] = log["Units"].map(lambda x: f"{x:+.3f}" if pd.notna(x) else "—")
    if "Odds" in log.columns:
        log["Odds"] = log["Odds"].map(_fmt)
    if "Pred pts" in log.columns:
        log["Pred pts"] = log["Pred pts"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "—")

    st.dataframe(log, use_container_width=True, height=360, hide_index=True)


def _bet_log_totals(bets):
    if bets.empty:
        return
    st.markdown("<div class='sh'>Bet log</div>", unsafe_allow_html=True)
    cols_map = {
        "predict_date": "Date", "home_team": "Home", "away_team": "Away",
        "bet_side": "Side", "total_line": "Line", "pred_total": "Pred total",
        "edge": "Edge", "line": "Odds",
        "kelly_stake": "Kelly", "result": "Result", "profit_units": "Units"
    }
    avail = {k: v for k, v in cols_map.items() if k in bets.columns}
    log   = bets[list(avail.keys())].copy().rename(columns=avail)
    log   = log.sort_values("Date", ascending=False)

    if "Side" in log.columns:
        log["Side"] = log["Side"].str.upper()
    if "Edge" in log.columns:
        log["Edge"] = log["Edge"].map(lambda x: f"{x:+.1%}" if pd.notna(x) else "—")
    if "Kelly" in log.columns:
        log["Kelly"] = log["Kelly"].map(lambda x: f"{x:.1%}" if pd.notna(x) else "—")
    if "Units" in log.columns:
        log["Units"] = log["Units"].map(lambda x: f"{x:+.3f}" if pd.notna(x) else "—")
    if "Odds" in log.columns:
        log["Odds"] = log["Odds"].map(_fmt)
    if "Pred total" in log.columns:
        log["Pred total"] = log["Pred total"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "—")

    st.dataframe(log, use_container_width=True, height=360, hide_index=True)


def render():
    st.markdown(_CSS, unsafe_allow_html=True)

    ml_bets     = _load("SELECT * FROM bet_log WHERE result IN ('WIN','LOSS') ORDER BY predict_date ASC")
    ats_bets    = _load("SELECT * FROM ats_bet_log WHERE result IN ('WIN','LOSS') ORDER BY predict_date ASC")
    totals_bets = _load("SELECT * FROM totals_bet_log WHERE result IN ('WIN','LOSS') ORDER BY predict_date ASC")
    props_bets  = _load("SELECT * FROM props_bet_log WHERE result IN ('WIN','LOSS') ORDER BY predict_date ASC")

    # ── Combined header ────────────────────────────────────────────────────────
    st.markdown("<div class='sh'>🏀 NBA ROI Tracker</div>", unsafe_allow_html=True)

    all_units = (
        (ml_bets["profit_units"].sum() if not ml_bets.empty else 0) +
        (ats_bets["profit_units"].sum() if not ats_bets.empty else 0) +
        (totals_bets["profit_units"].sum() if not totals_bets.empty else 0) +
        (props_bets["profit_units"].sum() if not props_bets.empty else 0)
    )
    all_bets  = len(ml_bets) + len(ats_bets) + len(totals_bets) + len(props_bets)
    all_wins  = (
        ((ml_bets["result"]=="WIN").sum() if not ml_bets.empty else 0) +
        ((ats_bets["result"]=="WIN").sum() if not ats_bets.empty else 0) +
        ((totals_bets["result"]=="WIN").sum() if not totals_bets.empty else 0) +
        ((props_bets["result"]=="WIN").sum() if not props_bets.empty else 0)
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total bets (all types)", all_bets)
    c2.metric("Combined win rate", f"{all_wins/all_bets:.1%}" if all_bets > 0 else "—")
    c3.metric("Combined units P&L", f"{all_units:+.3f}")
    c4.metric("Strategies live", "4  (ML + ATS + Totals + Props)")

    # Combined cumulative chart
    if not ml_bets.empty or not ats_bets.empty or not totals_bets.empty:
        st.markdown("<div class='sh'>Combined P&L curve</div>", unsafe_allow_html=True)
        fig = go.Figure()
        for df, label, color in [
            (ml_bets,     "Moneyline", "#6366f1"),
            (ats_bets,    "ATS",       "#22c55e"),
            (totals_bets, "Totals",    "#f59e0b"),
            (props_bets,  "Props",     "#ec4899"),
        ]:
            if df.empty:
                continue
            d = df.copy()
            d["predict_date"] = pd.to_datetime(d["predict_date"])
            d["cumulative"]   = d["profit_units"].cumsum()
            fig.add_scatter(x=d["predict_date"], y=d["cumulative"],
                            mode="lines", name=label,
                            line=dict(color=color, width=2))
        fig.add_hline(y=0, line_color="#333340", line_width=1)
        fig.update_layout(height=260, **_CHART)
        st.plotly_chart(fig, use_container_width=True)

    # ── Moneyline section ──────────────────────────────────────────────────────
    st.markdown("<div class='sh'>Moneyline performance</div>", unsafe_allow_html=True)
    if ml_bets.empty:
        st.info("No resolved moneyline bets yet. Results populate automatically after games finish.")
    else:
        _summary_metrics(ml_bets, "moneyline", "#6366f1")
        _cumulative_chart(ml_bets, "#6366f1")
        _monthly_and_edge(ml_bets)
        _bet_log(ml_bets, spread=False)

    # ── ATS section ────────────────────────────────────────────────────────────
    st.markdown("<div class='sh'>ATS (Against the Spread) performance</div>", unsafe_allow_html=True)
    if ats_bets.empty:
        st.info("No resolved ATS bets yet. Results populate automatically after games finish.")
    else:
        _summary_metrics(ats_bets, "ATS", "#22c55e")
        _cumulative_chart(ats_bets, "#22c55e")
        _monthly_and_edge(ats_bets)
        _bet_log(ats_bets, spread=True)

    # ── Totals section ─────────────────────────────────────────────────────────
    st.markdown("<div class='sh'>Totals (Over/Under) performance</div>", unsafe_allow_html=True)
    if totals_bets.empty:
        st.info("No resolved totals bets yet. Results populate automatically after games finish.")
    else:
        _summary_metrics(totals_bets, "totals", "#f59e0b")
        _cumulative_chart(totals_bets, "#f59e0b")
        _monthly_and_edge(totals_bets)
        _bet_log_totals(totals_bets)

    # ── Props section ───────────────────────────────────────────────────────────
    st.markdown("<div class='sh'>Player Props (Points) performance</div>", unsafe_allow_html=True)
    if props_bets.empty:
        st.info("No resolved props bets yet. Results populate automatically after games finish.")
    else:
        _summary_metrics(props_bets, "props", "#ec4899")
        _cumulative_chart(props_bets, "#ec4899")
        _monthly_and_edge(props_bets)
        _bet_log_props(props_bets)
