"""
page_modules/model_performance.py
─────────────────────────────────
Model performance & calibration page for AXIOM Edge.
Shows win rate, ROI, calibration curve, and edge-vs-outcome breakdown
across all logged strategies (NBA / MLB game-level and props).
"""
import sys, os
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sqlite3
from pathlib import Path
from config import DB_PATH
from mlb_config import MLB_DB_PATH
from nhl_config import NHL_DB_PATH

# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """
<style>
.block-container{padding-top:0;padding-bottom:2rem;max-width:1600px;padding-left:2rem;padding-right:2rem}
[data-testid="metric-container"]{background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:.875rem 1.25rem}
[data-testid="metric-container"] label{color:#8090a8!important;font-size:11px!important;letter-spacing:.06em;text-transform:uppercase}
[data-testid="stMetricValue"]{color:#f0f2f5!important;font-size:22px!important;font-weight:700!important}
.sh{font-size:11px;font-weight:700;letter-spacing:.1em;color:#8090a8;text-transform:uppercase;
    margin:1.25rem 0 .75rem;padding-bottom:6px;border-bottom:1px solid #1e2d42}
.page-header{background:linear-gradient(135deg,#0d1a2e 0%,#131d2e 60%,#0d1a0d 100%);
    border:1px solid #1e2d42;border-radius:14px;padding:1.75rem 2rem;margin-bottom:1.5rem}
.ph-tag{display:inline-flex;align-items:center;gap:6px;background:rgba(99,102,241,.12);
    border:1px solid rgba(99,102,241,.25);border-radius:20px;padding:4px 12px;
    font-size:11px;font-weight:700;letter-spacing:.08em;color:#818cf8;text-transform:uppercase;margin-bottom:.75rem}
.ph-title{font-size:26px;font-weight:800;color:#f0f2f5;letter-spacing:-.4px;margin-bottom:4px}
.ph-sub{font-size:13px;color:#8090a8}
.perf-table{width:100%;border-collapse:collapse;font-size:13px}
.perf-table th{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
    color:#8090a8;padding:6px 10px;border-bottom:1px solid #1e2d42;text-align:left}
.perf-table td{padding:9px 10px;border-bottom:1px solid #131d2e;color:#c8d0dc;vertical-align:middle}
.perf-table tr:hover td{background:#131d2e}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;vertical-align:middle}
.badge-win{background:#0f2a1a;color:#22c55e;border:1px solid #1a4a2a;border-radius:4px;
    padding:2px 8px;font-size:11px;font-weight:700}
.badge-loss{background:#2a0f0f;color:#ef4444;border:1px solid #4a1a1a;border-radius:4px;
    padding:2px 8px;font-size:11px;font-weight:700}
.badge-neutral{background:#1a1d2e;color:#8090a8;border:1px solid #2a2d42;border-radius:4px;
    padding:2px 8px;font-size:11px;font-weight:700}
.calib-note{font-size:12px;color:#8090a8;margin-top:.5rem;font-style:italic}
</style>
"""

_CHART = dict(
    paper_bgcolor="#131d2e", plot_bgcolor="#131d2e",
    margin=dict(l=0, r=0, t=24, b=0),
    xaxis=dict(showgrid=False, color="#7a8fa8", tickfont=dict(size=11)),
    yaxis=dict(gridcolor="#1a2840", color="#7a8fa8", zeroline=False, tickfont=dict(size=11)),
    legend=dict(font=dict(color="#8090a8", size=11), bgcolor="rgba(0,0,0,0)"),
    font=dict(color="#8090a8"),
)


def _layout(**overrides):
    """Merge overrides into the base _CHART theme.

    Deep-merges dict sub-keys (xaxis/yaxis/legend) so callers can add axis
    titles/ranges without colliding with the base theme. Spreading **_CHART
    directly alongside an explicit yaxis= raises 'multiple values for keyword'.
    """
    import copy
    base = copy.deepcopy(_CHART)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base

# ── Strategy registry ─────────────────────────────────────────────────────────
# Each entry drives both the summary table and the combined charts.
_STRATEGIES = [
    # NBA
    {"key": "nba_ml",    "sport": "NBA", "label": "Moneyline",     "db": DB_PATH,      "table": "bet_log",          "color": "#6366f1", "prob_col": "model_prob"},
    {"key": "nba_ats",   "sport": "NBA", "label": "Spread (ATS)",  "db": DB_PATH,      "table": "ats_bet_log",      "color": "#818cf8", "prob_col": "cover_prob"},
    {"key": "nba_tot",   "sport": "NBA", "label": "Totals (O/U)",  "db": DB_PATH,      "table": "totals_bet_log",   "color": "#a5b4fc", "prob_col": "ou_prob"},
    # MLB
    {"key": "mlb_ml",    "sport": "MLB", "label": "Moneyline",     "db": MLB_DB_PATH,  "table": "mlb_bet_log",      "color": "#22c55e", "prob_col": "model_prob"},
    {"key": "mlb_ats",   "sport": "MLB", "label": "Run Line (ATS)","db": MLB_DB_PATH,  "table": "mlb_ats_bet_log",  "color": "#4ade80", "prob_col": "cover_prob"},
    {"key": "mlb_tot",   "sport": "MLB", "label": "Totals (O/U)",  "db": MLB_DB_PATH,  "table": "mlb_totals_bet_log","color": "#86efac", "prob_col": "ou_prob"},
    # NHL (no logs yet but include so they show as 0-0)
    {"key": "nhl_ml",    "sport": "NHL", "label": "Moneyline",     "db": NHL_DB_PATH,  "table": "nhl_bet_log",      "color": "#f59e0b", "prob_col": "won"},
    {"key": "nhl_ats",   "sport": "NHL", "label": "Puck Line",     "db": NHL_DB_PATH,  "table": "nhl_ats_bet_log",  "color": "#fbbf24", "prob_col": "won"},
    {"key": "nhl_tot",   "sport": "NHL", "label": "Totals (O/U)",  "db": NHL_DB_PATH,  "table": "nhl_totals_bet_log","color": "#fcd34d", "prob_col": "won"},
]


def _load(db: str, table: str) -> pd.DataFrame:
    if not Path(db).exists():
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(db)
        df = pd.read_sql(f"SELECT * FROM {table}", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def _summarise(df: pd.DataFrame) -> dict:
    """Return stats dict for a single strategy's bet log."""
    empty = {"bets": 0, "wins": 0, "losses": 0, "win_pct": 0.0, "units": 0.0, "roi": 0.0, "avg_edge": 0.0, "avg_prob": 0.0}
    if df.empty:
        return empty

    # Normalise result column (WIN/LOSS or 1/0)
    if "result" in df.columns:
        settled = df[df["result"].isin(["WIN", "LOSS"])].copy()
        settled["_won"] = (settled["result"] == "WIN").astype(int)
    elif "won" in df.columns:
        settled = df[df["won"].notna()].copy()
        settled["_won"] = settled["won"].astype(int)
    else:
        return empty

    if settled.empty:
        return empty

    units_col = "profit_units" if "profit_units" in settled.columns else ("pnl" if "pnl" in settled.columns else None)
    units = float(settled[units_col].sum()) if units_col else 0.0

    # ROI = units / bets (flat unit = 1 unit risked)
    n = len(settled)
    roi = units / n if n > 0 else 0.0

    prob_cols = ["model_prob", "ou_prob", "cover_prob"]
    prob_col = next((c for c in prob_cols if c in settled.columns), None)
    avg_prob = float(settled[prob_col].mean()) if prob_col else 0.0

    avg_edge = float(settled["edge"].mean()) if "edge" in settled.columns else 0.0

    return {
        "bets":     n,
        "wins":     int(settled["_won"].sum()),
        "losses":   n - int(settled["_won"].sum()),
        "win_pct":  float(settled["_won"].mean()),
        "units":    units,
        "roi":      roi,
        "avg_edge": avg_edge,
        "avg_prob": avg_prob,
    }


def _build_combined(strategies) -> pd.DataFrame:
    """Combine all settled bets into one DataFrame for calibration + edge charts."""
    frames = []
    for s in strategies:
        df = _load(s["db"], s["table"])
        if df.empty:
            continue
        if "result" in df.columns:
            df = df[df["result"].isin(["WIN", "LOSS"])].copy()
            df["_won"] = (df["result"] == "WIN").astype(int)
        elif "won" in df.columns:
            df = df[df["won"].notna()].copy()
            df["_won"] = df["won"].astype(int)
        else:
            continue
        prob_col = next((c for c in ["model_prob", "ou_prob", "cover_prob"] if c in df.columns), None)
        if prob_col:
            df["_pred_prob"] = df[prob_col]
        else:
            continue
        df["_sport"]  = s["sport"]
        df["_market"] = s["label"]
        df["_color"]  = s["color"]
        if "edge" in df.columns:
            df["_edge"] = df["edge"]
        if "profit_units" in df.columns:
            df["_units"] = df["profit_units"]
        elif "pnl" in df.columns:
            df["_units"] = df["pnl"]
        frames.append(df[["predict_date", "_won", "_pred_prob", "_edge", "_units", "_sport", "_market", "_color"] if "_edge" in df.columns else ["predict_date", "_won", "_pred_prob", "_units", "_sport", "_market", "_color"]])
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _calibration_chart(df: pd.DataFrame) -> go.Figure:
    """
    Bucket predictions by 5-percentage-point bins of predicted probability,
    show actual win rate vs perfect calibration diagonal.
    """
    bins   = np.arange(0.50, 1.01, 0.05)
    labels = [f"{int(b*100)}-{int((b+0.05)*100)}%" for b in bins[:-1]]
    df     = df.dropna(subset=["_pred_prob", "_won"]).copy()
    df["_bin"] = pd.cut(df["_pred_prob"], bins=bins, labels=labels, right=False, include_lowest=True)

    grp = df.groupby("_bin", observed=True).agg(
        actual_win=("_won", "mean"),
        n=("_won", "count"),
        mid=("_pred_prob", "mean"),
    ).reset_index()
    grp = grp[grp["n"] >= 1]

    fig = go.Figure()

    # Perfect calibration diagonal
    x_diag = [0.50, 1.0]
    fig.add_trace(go.Scatter(
        x=x_diag, y=x_diag,
        mode="lines",
        line=dict(color="#2a3a50", width=1.5, dash="dash"),
        name="Perfect calibration",
        hoverinfo="skip",
    ))

    # Calibration bars
    fig.add_trace(go.Bar(
        x=grp["_bin"].astype(str),
        y=grp["actual_win"],
        text=[f"{v:.1%} (n={n})" for v, n in zip(grp["actual_win"], grp["n"])],
        textposition="outside",
        textfont=dict(size=10, color="#8090a8"),
        marker_color=[
            "#22c55e" if av >= mp - 0.05 else "#ef4444"
            for av, mp in zip(grp["actual_win"], grp["mid"])
        ],
        marker_opacity=0.7,
        name="Actual win rate",
    ))

    fig.update_layout(**_layout(
        yaxis=dict(
            range=[0, 1.1],
            tickformat=".0%",
            title=dict(text="Actual win rate", font=dict(size=11, color="#8090a8")),
        ),
        xaxis=dict(
            title=dict(text="Predicted probability bucket", font=dict(size=11, color="#8090a8")),
        ),
        showlegend=False,
        height=300,
        bargap=0.25,
    ))
    return fig


def _edge_chart(df: pd.DataFrame) -> go.Figure:
    """Bar chart: actual win rate bucketed by model edge size."""
    if "_edge" not in df.columns:
        return go.Figure()
    df = df.dropna(subset=["_edge", "_won"]).copy()

    edges = [0.05, 0.08, 0.12, 0.16, 0.20, 1.0]
    labels = ["5-8%", "8-12%", "12-16%", "16-20%", "20%+"]
    df["_edge_bin"] = pd.cut(df["_edge"], bins=edges, labels=labels, right=False, include_lowest=True)

    grp = df.groupby("_edge_bin", observed=True).agg(
        actual_win=("_won", "mean"),
        n=("_won", "count"),
        avg_edge=("_edge", "mean"),
    ).reset_index().dropna()

    if grp.empty:
        return go.Figure()

    # Expected win = avg edge + 0.5 (rough fair break-even)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=grp["_edge_bin"].astype(str),
        y=grp["actual_win"],
        text=[f"{v:.1%} (n={n})" for v, n in zip(grp["actual_win"], grp["n"])],
        textposition="outside",
        textfont=dict(size=10, color="#8090a8"),
        marker_color="#6366f1",
        marker_opacity=0.75,
        name="Actual win rate",
    ))
    # 52.4% break-even line (-110 standard vig)
    fig.add_hline(
        y=0.524, line_color="#ef4444", line_dash="dot", line_width=1.5,
        annotation_text="-110 break-even", annotation_font_size=10,
        annotation_font_color="#ef4444",
    )
    fig.update_layout(**_layout(
        yaxis=dict(range=[0, 1.1], tickformat=".0%",
                   title=dict(text="Win rate", font=dict(size=11, color="#8090a8"))),
        xaxis=dict(title=dict(text="Edge bucket", font=dict(size=11, color="#8090a8"))),
        showlegend=False, height=300, bargap=0.3,
    ))
    return fig


def _roi_by_market_chart(all_stats: list) -> go.Figure:
    """Horizontal bar chart of units P&L per strategy."""
    labels = [f"{s['sport']} {s['label']}" for s in all_stats if s["stats"]["bets"] > 0]
    units  = [s["stats"]["units"] for s in all_stats if s["stats"]["bets"] > 0]
    colors = [s["color"] for s in all_stats if s["stats"]["bets"] > 0]
    bar_colors = ["#22c55e" if u >= 0 else "#ef4444" for u in units]

    fig = go.Figure(go.Bar(
        x=units, y=labels,
        orientation="h",
        marker_color=bar_colors,
        marker_opacity=0.75,
        text=[f"{u:+.3f}u" for u in units],
        textposition="outside",
        textfont=dict(size=11, color="#8090a8"),
    ))
    fig.add_vline(x=0, line_color="#2a3a50", line_width=1)
    fig.update_layout(**_layout(
        xaxis=dict(title=dict(text="Units P&L", font=dict(size=11, color="#8090a8"))),
        yaxis=dict(showgrid=False),
        height=max(200, len(labels) * 36 + 40),
        showlegend=False,
    ))
    return fig


def _cumulative_chart(combined: pd.DataFrame) -> go.Figure:
    """Cumulative units P&L over time per sport."""
    if combined.empty or "_units" not in combined.columns:
        return go.Figure()
    combined = combined.dropna(subset=["predict_date", "_units"]).copy()
    combined["predict_date"] = pd.to_datetime(combined["predict_date"])
    combined = combined.sort_values("predict_date")

    fig = go.Figure()
    sport_colors = {"NBA": "#6366f1", "MLB": "#22c55e", "NHL": "#f59e0b"}

    for sport, grp in combined.groupby("_sport"):
        grp = grp.sort_values("predict_date")
        grp["cumsum"] = grp["_units"].cumsum()
        fig.add_trace(go.Scatter(
            x=grp["predict_date"], y=grp["cumsum"],
            mode="lines+markers",
            line=dict(color=sport_colors.get(sport, "#8090a8"), width=2),
            marker=dict(size=5),
            name=sport,
            hovertemplate="%{x|%b %d}: %{y:+.3f}u<extra>" + sport + "</extra>",
        ))

    fig.add_hline(y=0, line_color="#2a3a50", line_width=1)
    fig.update_layout(**_layout(
        yaxis=dict(title=dict(text="Cumulative units", font=dict(size=11, color="#8090a8"))),
        xaxis=dict(title=dict(text="Date", font=dict(size=11, color="#8090a8"))),
        height=280,
        legend=dict(orientation="h", x=0, y=1.08),
    ))
    return fig


# ── Main render ───────────────────────────────────────────────────────────────
def render():
    st.markdown(_CSS, unsafe_allow_html=True)

    st.markdown("""
<div class="page-header">
  <div class="ph-tag">📊 Analytics</div>
  <div class="ph-title">Model Performance</div>
  <div class="ph-sub">Calibration, edge accuracy, and ROI across all strategies</div>
</div>
""", unsafe_allow_html=True)

    # ── Load all strategies ──────────────────────────────────────────────────
    all_stats = []
    for s in _STRATEGIES:
        df   = _load(s["db"], s["table"])
        stats = _summarise(df)
        all_stats.append({**s, "stats": stats, "df": df})

    combined = _build_combined(_STRATEGIES)

    # ── Top-level metrics ────────────────────────────────────────────────────
    total_bets  = sum(s["stats"]["bets"]  for s in all_stats)
    total_wins  = sum(s["stats"]["wins"]  for s in all_stats)
    total_units = sum(s["stats"]["units"] for s in all_stats)
    overall_wr  = total_wins / total_bets if total_bets > 0 else 0.0
    avg_edge    = float(combined["_edge"].mean()) if not combined.empty and "_edge" in combined.columns else 0.0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Bets Logged", f"{total_bets:,}")
    with c2:
        wc = "normal" if overall_wr >= 0.524 else "inverse"
        st.metric("Overall Win Rate", f"{overall_wr:.1%}",
                  delta=f"{overall_wr - 0.524:+.1%} vs break-even",
                  delta_color=wc)
    with c3:
        dc = "normal" if total_units >= 0 else "inverse"
        st.metric("Total Units P&L", f"{total_units:+.3f}u", delta_color=dc)
    with c4:
        st.metric("Avg Model Edge", f"{avg_edge:.1%}" if avg_edge else "—")

    # ── Strategy breakdown table ─────────────────────────────────────────────
    st.markdown("<div class='sh'>Strategy Breakdown</div>", unsafe_allow_html=True)

    rows_html = ""
    last_sport = None
    for s in all_stats:
        st_data = s["stats"]
        if st_data["bets"] == 0:
            continue

        # Sport separator row
        if s["sport"] != last_sport:
            last_sport = s["sport"]
            emoji = {"NBA": "🏀", "MLB": "⚾", "NHL": "🏒"}.get(s["sport"], "")
            rows_html += f"""
<tr>
  <td colspan="7" style="padding:10px 10px 4px;font-size:10px;font-weight:700;
    letter-spacing:.1em;color:#44506a;text-transform:uppercase;background:#0d1320">
    {emoji} {s["sport"]}
  </td>
</tr>"""

        wr = st_data["win_pct"]
        wrc = "#22c55e" if wr >= 0.524 else ("#ef4444" if wr < 0.50 else "#f59e0b")
        uc  = "#22c55e" if st_data["units"] >= 0 else "#ef4444"
        roi_c = "#22c55e" if st_data["roi"] >= 0 else "#ef4444"
        rec = f"{st_data['wins']}W–{st_data['losses']}L"
        rows_html += f"""
<tr>
  <td><span class="dot" style="background:{s['color']}"></span>{s['label']}</td>
  <td>{st_data['bets']}</td>
  <td style="color:#8090a8">{rec}</td>
  <td style="color:{wrc};font-weight:600">{wr:.1%}</td>
  <td style="color:{uc};font-weight:600">{st_data['units']:+.3f}u</td>
  <td style="color:{roi_c};font-weight:600">{st_data['roi']:+.1%}</td>
  <td style="color:#8090a8">{st_data['avg_edge']:.1%}</td>
</tr>"""

    if rows_html:
        st.markdown(f"""
<table class="perf-table">
  <thead>
    <tr>
      <th>Strategy</th><th>Bets</th><th>Record</th>
      <th>Win %</th><th>Units P&L</th><th>ROI / bet</th><th>Avg Edge</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>
""", unsafe_allow_html=True)
    else:
        st.info("No settled bets yet. Logs populate after games finish and results are fetched.")

    # ── Charts row ───────────────────────────────────────────────────────────
    if not combined.empty:
        st.markdown("<div class='sh'>Calibration & Edge Analysis</div>", unsafe_allow_html=True)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Model Calibration** — predicted probability vs actual win rate")
            fig_cal = _calibration_chart(combined)
            st.plotly_chart(fig_cal, use_container_width=True, config={"displayModeBar": False})
            n_total = len(combined.dropna(subset=["_pred_prob","_won"]))
            st.markdown(f"<div class='calib-note'>Green bars = model on-target or over-performing · Red = underperforming · {n_total} total bets</div>", unsafe_allow_html=True)

        with col_b:
            st.markdown("**Edge → Win Rate** — do bigger edges produce more wins?")
            fig_edge = _edge_chart(combined)
            if fig_edge.data:
                st.plotly_chart(fig_edge, use_container_width=True, config={"displayModeBar": False})
                st.markdown("<div class='calib-note'>Red dashed line = 52.4% break-even at -110 vig</div>", unsafe_allow_html=True)
            else:
                st.caption("Not enough data with edge information.")

        # P&L charts
        st.markdown("<div class='sh'>P&L Breakdown</div>", unsafe_allow_html=True)

        col_c, col_d = st.columns(2)
        with col_c:
            st.markdown("**Units P&L by Market**")
            active = [s for s in all_stats if s["stats"]["bets"] > 0]
            if active:
                fig_roi = _roi_by_market_chart(active)
                st.plotly_chart(fig_roi, use_container_width=True, config={"displayModeBar": False})

        with col_d:
            st.markdown("**Cumulative P&L Over Time**")
            fig_cum = _cumulative_chart(combined)
            if fig_cum.data:
                st.plotly_chart(fig_cum, use_container_width=True, config={"displayModeBar": False})
            else:
                st.caption("Not enough dated data to plot.")

    else:
        st.info("No settled bets across any strategy yet. Charts will appear once results are logged.")

    # ── Insight callout ──────────────────────────────────────────────────────
    st.markdown("<div class='sh'>What to Look For</div>", unsafe_allow_html=True)
    st.markdown("""
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
  <div style="background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:1rem 1.25rem">
    <div style="font-size:12px;font-weight:700;color:#818cf8;margin-bottom:6px">📐 Calibration</div>
    <div style="font-size:12px;color:#8090a8;line-height:1.6">Green bars mean the model's predicted probability matches reality.
    Red bars (actual win rate below predicted) mean the model is <em>overconfident</em> — a sign to raise <code>MIN_EDGE</code> further.</div>
  </div>
  <div style="background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:1rem 1.25rem">
    <div style="font-size:12px;font-weight:700;color:#22c55e;margin-bottom:6px">📈 Edge Monotonicity</div>
    <div style="font-size:12px;color:#8090a8;line-height:1.6">Win rate should increase as edge bucket grows.
    If it's flat or declining, the model is generating false edges — usually a sigma calibration or feature leakage issue.</div>
  </div>
  <div style="background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:1rem 1.25rem">
    <div style="font-size:12px;font-weight:700;color:#f59e0b;margin-bottom:6px">💰 Sample Size</div>
    <div style="font-size:12px;color:#8090a8;line-height:1.6">Stats are only meaningful with 50+ bets per market.
    A 60% win rate on 10 bets means nothing. Focus on MLB (largest log) until other sports accumulate volume.</div>
  </div>
</div>
""", unsafe_allow_html=True)
