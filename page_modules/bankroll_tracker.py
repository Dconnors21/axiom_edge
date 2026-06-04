import sys, os
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sqlite3
from pathlib import Path
from datetime import date, timedelta
from config import DB_PATH
from mlb_config import MLB_DB_PATH
from nhl_config import NHL_DB_PATH

# DB for custom parlay logs (shared across sports)
BANKROLL_DB = os.path.join(_parent, "bankroll.db")

# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """
<style>
.block-container{padding-top:0;padding-bottom:2rem;max-width:1600px;padding-left:2rem;padding-right:2rem}
[data-testid="metric-container"]{background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:.875rem 1.25rem}
[data-testid="metric-container"] label{color:#8090a8!important;font-size:11px!important;letter-spacing:.06em;text-transform:uppercase}
[data-testid="stMetricValue"]{color:#f0f2f5!important;font-size:22px!important;font-weight:700!important}
.sh{font-size:11px;font-weight:700;letter-spacing:.1em;color:#8090a8;text-transform:uppercase;margin:1.25rem 0 .75rem;padding-bottom:7px;border-bottom:1px solid #1e2d42}
.page-header{background:linear-gradient(135deg,#0d1a2e 0%,#131d2e 60%,#0d1a1a 100%);border:1px solid #1e2d42;border-radius:14px;padding:1.75rem 2rem;margin-bottom:1.5rem}
.ph-tag{display:inline-flex;align-items:center;gap:6px;background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.25);border-radius:20px;padding:4px 12px;font-size:11px;font-weight:700;letter-spacing:.08em;color:#10b981;text-transform:uppercase;margin-bottom:.875rem}
.ph-title{font-size:28px;font-weight:800;color:#f0f2f5;letter-spacing:-.5px;margin-bottom:4px}
.ph-sub{font-size:14px;color:#8090a8}
.settings-card{background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:1.25rem 1.5rem;margin-bottom:1.25rem}
/* Strategy table rows */
.strat-row{display:flex;align-items:center;padding:9px 0;border-bottom:1px solid #1a2840;font-size:13px}
.strat-row:last-child{border-bottom:none}
.strat-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-right:10px}
.strat-name{flex:1;color:#c8d0dc;font-weight:500}
.strat-bets{width:48px;text-align:right;color:#8090a8}
.strat-rec{width:72px;text-align:right;color:#8090a8}
.strat-winpct{width:56px;text-align:right;color:#8090a8}
.strat-units{width:72px;text-align:right;font-weight:600}
.strat-roi{width:60px;text-align:right;font-weight:600}
/* Bet log rows */
.log-row{display:flex;align-items:center;padding:8px 0;border-bottom:1px solid #1a2840;font-size:13px}
.log-row:last-child{border-bottom:none}
.log-date{width:68px;color:#7a8fa8;font-size:12px}
.log-sport{width:36px;font-size:10px;font-weight:700;letter-spacing:.05em;color:#8090a8}
.log-desc{flex:1;color:#c8d0dc}
.log-edge{width:60px;text-align:right;font-size:12px;font-weight:600}
.log-units{width:60px;text-align:right;font-weight:600}
.log-result{width:44px;text-align:right;font-size:12px;font-weight:700}
/* Parlay rows */
.prl-row{display:flex;align-items:flex-start;padding:10px 0;border-bottom:1px solid #1a2840;gap:.5rem}
.prl-row:last-child{border-bottom:none}
.prl-date{width:68px;color:#7a8fa8;font-size:12px;padding-top:1px}
.prl-label{flex:1;color:#f0f2f5;font-weight:600;font-size:13px}
.prl-legs{color:#8090a8;font-size:11px;margin-top:2px}
.prl-odds{width:60px;text-align:right;color:#60a5fa;font-size:13px;font-weight:600}
.prl-units{width:56px;text-align:right;color:#96aec8;font-size:12px}
.prl-pnl{width:64px;text-align:right;font-weight:700;font-size:13px}
.prl-status{width:70px;text-align:right;font-size:12px;font-weight:700}
.prl-form-card{background:#0f1828;border:1px solid #1e2d42;border-radius:10px;padding:1.25rem 1.5rem}
.prl-stat-strip{display:flex;gap:1rem;flex-wrap:wrap;background:#0f1828;border:1px solid #1e2d42;border-radius:10px;padding:.85rem 1.2rem;margin-bottom:1.2rem}
.prl-stat-item{display:flex;flex-direction:column;gap:.15rem;min-width:90px}
.prl-stat-val{font-size:1.15rem;font-weight:700;color:#f0f2f5}
.prl-stat-lbl{font-size:.68rem;color:#7a8fa8;text-transform:uppercase;letter-spacing:.08em}
</style>
"""

_CHART = dict(
    paper_bgcolor="#131d2e", plot_bgcolor="#131d2e",
    margin=dict(l=0, r=0, t=10, b=0),
    xaxis=dict(showgrid=False, color="#7a8fa8"),
    yaxis=dict(gridcolor="#1a2840", color="#7a8fa8", zeroline=False),
    legend=dict(font=dict(color="#8090a8", size=11), bgcolor="rgba(0,0,0,0)"),
    font=dict(color="#8090a8"),
)

_RGB = {
    "#3b82f6": "59,130,246",   "#22c55e": "34,197,94",    "#f59e0b": "245,158,11",
    "#ec4899": "236,72,153",   "#8b5cf6": "139,92,246",   "#f97316": "249,115,22",
    "#06b6d4": "6,182,212",    "#10b981": "16,185,129",   "#eab308": "234,179,8",
    "#60a5fa": "96,165,250",   "#4ade80": "74,222,128",   "#fbbf24": "251,191,36",
    "#ef4444": "239,68,68",    "#38bdf8": "56,189,248",   "#34d399": "52,211,153",
}

ALL_STRATEGIES = [
    {"key": "nba_ml",  "sport": "NBA", "label": "Moneyline",  "db": DB_PATH,     "table": "bet_log",             "color": "#3b82f6", "btype": "ml"},
    {"key": "nba_ats", "sport": "NBA", "label": "ATS",        "db": DB_PATH,     "table": "ats_bet_log",          "color": "#22c55e", "btype": "ats"},
    {"key": "nba_tot", "sport": "NBA", "label": "Totals",     "db": DB_PATH,     "table": "totals_bet_log",       "color": "#f59e0b", "btype": "totals"},
    {"key": "nba_pts", "sport": "NBA", "label": "Props Pts",  "db": DB_PATH,     "table": "props_bet_log",        "color": "#ec4899", "btype": "props"},
    {"key": "nba_reb", "sport": "NBA", "label": "Props Reb",  "db": DB_PATH,     "table": "props_reb_bet_log",    "color": "#8b5cf6", "btype": "props"},
    {"key": "nba_ast", "sport": "NBA", "label": "Props Ast",  "db": DB_PATH,     "table": "props_ast_bet_log",    "color": "#f97316", "btype": "props"},
    {"key": "nba_3pm", "sport": "NBA", "label": "Props 3PM",  "db": DB_PATH,     "table": "props_threes_bet_log", "color": "#06b6d4", "btype": "props"},
    {"key": "nba_stl", "sport": "NBA", "label": "Props Stl",  "db": DB_PATH,     "table": "props_stl_bet_log",    "color": "#10b981", "btype": "props"},
    {"key": "nba_blk", "sport": "NBA", "label": "Props Blk",  "db": DB_PATH,     "table": "props_blk_bet_log",    "color": "#eab308", "btype": "props"},
    {"key": "mlb_ml",  "sport": "MLB", "label": "Moneyline",  "db": MLB_DB_PATH, "table": "mlb_bet_log",          "color": "#60a5fa", "btype": "ml"},
    {"key": "mlb_rl",  "sport": "MLB", "label": "Run Line",   "db": MLB_DB_PATH, "table": "mlb_ats_bet_log",      "color": "#4ade80", "btype": "ats"},
    {"key": "mlb_tot", "sport": "MLB", "label": "Totals",     "db": MLB_DB_PATH, "table": "mlb_totals_bet_log",   "color": "#fbbf24", "btype": "totals"},
    {"key": "nhl_ml",   "sport": "NHL", "label": "Moneyline",    "db": NHL_DB_PATH, "table": "nhl_bet_log",          "color": "#38bdf8", "btype": "ml",     "schema": "nhl"},
    {"key": "nhl_pl",   "sport": "NHL", "label": "Puck Line",    "db": NHL_DB_PATH, "table": "nhl_ats_bet_log",      "color": "#34d399", "btype": "ats",    "schema": "nhl"},
    {"key": "nhl_tot",  "sport": "NHL", "label": "Totals",       "db": NHL_DB_PATH, "table": "nhl_totals_bet_log",   "color": "#fcd34d", "btype": "totals", "schema": "nhl"},
    {"key": "mlb_k",    "sport": "MLB", "label": "K Strikeouts", "db": MLB_DB_PATH, "table": "mlb_k_bet_log",        "color": "#3b82f6", "btype": "props",  "schema": "nhl"},
    {"key": "mlb_hits", "sport": "MLB", "label": "Batter Hits",  "db": MLB_DB_PATH, "table": "mlb_hits_bet_log",     "color": "#22c55e", "btype": "props",  "schema": "nhl"},
    {"key": "mlb_tb",   "sport": "MLB", "label": "Total Bases",  "db": MLB_DB_PATH, "table": "mlb_tb_bet_log",       "color": "#f59e0b", "btype": "props",  "schema": "nhl"},
]

# ── Strategy bet log helpers ──────────────────────────────────────────────────

def _load(db_path, table, schema="classic"):
    if not Path(db_path).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(db_path)
    try:
        if schema == "nhl":
            df = pd.read_sql(
                f"SELECT * FROM {table} WHERE won IS NOT NULL ORDER BY game_date ASC", conn
            )
            if not df.empty:
                df["predict_date"] = df["game_date"]
                df["result"]       = df["won"].map({1: "WIN", 0: "LOSS"})
                df["profit_units"] = df["pnl"]
                df["kelly_stake"]  = df.get("kelly", pd.Series(0.0, index=df.index))
                df["total_line"]   = df.get("line",  pd.Series(None, index=df.index))
        else:
            df = pd.read_sql(
                f"SELECT * FROM {table} WHERE result IN ('WIN','LOSS') ORDER BY predict_date ASC", conn
            )
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def _describe(row, btype):
    try:
        if btype == "ml":
            return str(row.get("bet_team", "?"))
        elif btype == "ats":
            spread = row.get("spread")
            s = f"{float(spread):+.1f}" if pd.notna(spread) else ""
            return f"{row.get('bet_team', '?')} {s}".strip()
        elif btype == "totals":
            home = (row.get("home_team") or "?").split()[-1]
            away = (row.get("away_team") or "?").split()[-1]
            side = str(row.get("bet_side", "?")).upper()
            line = row.get("total_line") or row.get("line", "?")
            return f"{away}@{home} {side} {line}"
        else:
            side = str(row.get("bet_side", "")).upper()
            line = row.get("line", "?")
            return f"{row.get('player_name', '?')} {side} {line}"
    except Exception:
        return "—"


_BTYPE_MAP = {
    "All": None, "Moneyline": "ml", "ATS / Run Line": "ats",
    "Totals": "totals", "Player Props": "props",
}


def _build_combined(sport_filter, start_date, btype_filter=None):
    rows = []
    for cfg in ALL_STRATEGIES:
        if sport_filter != "All" and cfg["sport"] != sport_filter:
            continue
        if btype_filter and cfg["btype"] != btype_filter:
            continue
        df = _load(cfg["db"], cfg["table"], cfg.get("schema", "classic"))
        if df.empty:
            continue
        df["predict_date"] = pd.to_datetime(df["predict_date"])
        if start_date:
            df = df[df["predict_date"] >= pd.Timestamp(start_date)]
        if df.empty:
            continue
        for _, row in df.iterrows():
            rows.append({
                "date":     row["predict_date"],
                "sport":    cfg["sport"],
                "strategy": f"{cfg['sport']} {cfg['label']}",
                "color":    cfg["color"],
                "key":      cfg["key"],
                "desc":     _describe(row, cfg["btype"]),
                "edge":     float(row.get("edge", 0)),
                "kelly":    float(row.get("kelly_stake", 0)),
                "units":    float(row.get("profit_units", 0)),
                "result":   str(row.get("result", "")),
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


# ── Custom Parlay helpers ─────────────────────────────────────────────────────

def _parlay_conn():
    conn = sqlite3.connect(BANKROLL_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_parlays (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            label        TEXT NOT NULL,
            legs         TEXT,
            n_legs       INTEGER DEFAULT 2,
            combined_odds REAL NOT NULL,
            units        REAL NOT NULL DEFAULT 1.0,
            bet_date     TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending',
            pnl          REAL,
            notes        TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def _fmt_odds(o):
    try:
        o = int(o)
        return f"+{o}" if o > 0 else str(o)
    except Exception:
        return str(o)


def _calc_pnl(odds: float, units: float, won: bool) -> float:
    if won:
        return units * (odds / 100) if odds > 0 else units * (100 / abs(odds))
    return -units


def _save_parlay(label, legs, n_legs, combined_odds, units, bet_date, notes):
    conn = _parlay_conn()
    conn.execute("""
        INSERT INTO custom_parlays (label, legs, n_legs, combined_odds, units, bet_date, status, pnl, notes)
        VALUES (?,?,?,?,?,?,'pending',NULL,?)
    """, (label, legs, n_legs, combined_odds, units, str(bet_date), notes))
    conn.commit()
    conn.close()


def _update_parlay_result(parlay_id: int, status: str, odds: float, units: float):
    won  = (status == "won")
    pnl  = _calc_pnl(odds, units, won)
    conn = _parlay_conn()
    conn.execute(
        "UPDATE custom_parlays SET status=?, pnl=? WHERE id=?",
        (status, pnl, parlay_id)
    )
    conn.commit()
    conn.close()


def _delete_parlay(parlay_id: int):
    conn = _parlay_conn()
    conn.execute("DELETE FROM custom_parlays WHERE id=?", (parlay_id,))
    conn.commit()
    conn.close()


def _load_parlays(start_date=None) -> pd.DataFrame:
    conn = _parlay_conn()
    df   = pd.read_sql("SELECT * FROM custom_parlays ORDER BY bet_date DESC", conn)
    conn.close()
    if df.empty:
        return df
    df["bet_date"] = pd.to_datetime(df["bet_date"])
    if start_date:
        df = df[df["bet_date"] >= pd.Timestamp(start_date)]
    return df


# ── RENDER ────────────────────────────────────────────────────────────────────

def render():
    st.markdown(_CSS, unsafe_allow_html=True)

    today_display = date.today().strftime("%A, %B %d, %Y")
    st.markdown(f"""
<div class="page-header">
  <div class="ph-tag">💰 Bankroll</div>
  <div class="ph-title">Bankroll Tracker</div>
  <div class="ph-sub">{today_display} · Strategy P&amp;L + custom parlay log — NBA · MLB · NHL</div>
</div>
""", unsafe_allow_html=True)

    # ── Global settings row (applies to both tabs) ────────────────────────────
    g1, g2 = st.columns([1, 3])
    with g1:
        st.caption("Unit size ($)")
        unit_size = st.number_input(
            "Unit size", min_value=1, max_value=100_000, value=100, step=10,
            label_visibility="collapsed",
            help="1 unit = how many dollars you bet per Kelly recommendation",
        )
    with g2:
        st.caption("Time period")
        period = st.selectbox(
            "Period", ["All time", "This month", "Last 30 days", "Last 7 days"],
            label_visibility="collapsed",
        )

    start_date = None
    today_dt   = date.today()
    if period == "This month":
        start_date = today_dt.replace(day=1)
    elif period == "Last 30 days":
        start_date = today_dt - timedelta(days=30)
    elif period == "Last 7 days":
        start_date = today_dt - timedelta(days=7)

    # ── Top-level tabs ────────────────────────────────────────────────────────
    tab_strat, tab_parlay = st.tabs(["📊  Strategy Performance", "🎲  Custom Parlays"])

    # ════════════════════════════════════════════════════════════════════════
    # TAB 1 — STRATEGY PERFORMANCE
    # ════════════════════════════════════════════════════════════════════════
    with tab_strat:

        # Filters
        f1, f2, f3 = st.columns([2, 2, 2])
        with f1:
            st.caption("Sport")
            sport_filter = st.selectbox("Sport", ["All", "NBA", "MLB", "NHL"],
                                        label_visibility="collapsed", key="sp_sport")
        with f2:
            st.caption("Bet type")
            bet_type_label = st.selectbox(
                "Bet type", ["All", "Moneyline", "ATS / Run Line", "Totals", "Player Props"],
                label_visibility="collapsed", key="sp_btype",
            )
        with f3:
            st.caption("Show strategies")
            show_zero = st.checkbox("Include strategies with no data", value=False, key="sp_zero")

        btype_filter = _BTYPE_MAP.get(bet_type_label)
        combined     = _build_combined(sport_filter, start_date, btype_filter)

        if combined.empty:
            st.info("No resolved bets found for the selected filters. Run the daily pipeline to populate bet logs.")
        else:
            # Summary metrics
            total_bets    = len(combined)
            wins          = (combined["result"] == "WIN").sum()
            total_units   = combined["units"].sum()
            total_dollars = total_units * unit_size
            win_pct       = wins / total_bets if total_bets > 0 else 0
            roi_pct       = total_units / total_bets * 100 if total_bets > 0 else 0
            uc = "normal" if total_units >= 0 else "inverse"

            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Total bets",  total_bets)
            c2.metric("Win rate",    f"{win_pct:.1%}")
            c3.metric("Record",      f"{wins}W–{total_bets-wins}L")
            c4.metric("Units P&L",   f"{total_units:+.2f}u",    delta_color=uc)
            c5.metric("$ P&L",       f"${total_dollars:+,.0f}", delta_color=uc)
            c6.metric("ROI / bet",   f"{roi_pct:+.2f}%")

            # Cumulative P&L chart
            st.markdown("<div class='sh'>Cumulative P&L</div>", unsafe_allow_html=True)
            combined["cumulative"] = combined["units"].cumsum()
            cum_color = "#10b981" if total_units >= 0 else "#ef4444"
            rgb       = _RGB.get(cum_color, "239,68,68")

            ct1, ct2 = st.tabs(["Combined", "By strategy"])
            with ct1:
                fig = go.Figure()
                fig.add_scatter(
                    x=combined["date"], y=combined["cumulative"] * unit_size,
                    mode="lines", line=dict(color=cum_color, width=2.5),
                    fill="tozeroy", fillcolor=f"rgba({rgb},0.08)",
                    name="Combined",
                )
                fig.add_hline(y=0, line_color="#1e2d42", line_width=1)
                fig.update_layout(height=260, yaxis_title=f"$ P&L (1u = ${unit_size})", **_CHART)
                st.plotly_chart(fig, use_container_width=True)

            with ct2:
                fig2 = go.Figure()
                for cfg in ALL_STRATEGIES:
                    if sport_filter != "All" and cfg["sport"] != sport_filter:
                        continue
                    sub = combined[combined["key"] == cfg["key"]]
                    if sub.empty:
                        continue
                    sub = sub.copy()
                    sub["strat_cum"] = sub["units"].cumsum()
                    fig2.add_scatter(
                        x=sub["date"], y=sub["strat_cum"],
                        mode="lines", name=f"{cfg['sport']} {cfg['label']}",
                        line=dict(color=cfg["color"], width=1.5),
                    )
                fig2.add_hline(y=0, line_color="#1e2d42", line_width=1)
                fig2.update_layout(height=280, yaxis_title="Units", **_CHART)
                st.plotly_chart(fig2, use_container_width=True)

            # Strategy breakdown + Monthly P&L
            col_left, col_right = st.columns([3, 2])
            with col_left:
                st.markdown("<div class='sh'>Strategy breakdown</div>", unsafe_allow_html=True)
                st.markdown("""
<div style="display:flex;padding:4px 0 6px;border-bottom:1px solid #1e2d42;
     font-size:10px;color:#7a8fa8;letter-spacing:.06em;text-transform:uppercase">
  <div style="width:18px"></div>
  <div style="flex:1">Strategy</div>
  <div style="width:48px;text-align:right">Bets</div>
  <div style="width:72px;text-align:right">Record</div>
  <div style="width:56px;text-align:right">Win%</div>
  <div style="width:72px;text-align:right">Units</div>
  <div style="width:60px;text-align:right">ROI</div>
</div>""", unsafe_allow_html=True)
                rows_html = ""
                for cfg in ALL_STRATEGIES:
                    if sport_filter != "All" and cfg["sport"] != sport_filter:
                        continue
                    sub = combined[combined["key"] == cfg["key"]]
                    if sub.empty and not show_zero:
                        continue
                    n  = len(sub)
                    w  = (sub["result"] == "WIN").sum() if n > 0 else 0
                    u  = sub["units"].sum() if n > 0 else 0
                    wp = w / n if n > 0 else 0
                    roi = u / n * 100 if n > 0 else 0
                    uc_ = "#22c55e" if u >= 0 else "#ef4444"
                    rc_ = "#22c55e" if roi >= 0 else "#ef4444"
                    rows_html += f"""
<div class="strat-row">
  <div class="strat-dot" style="background:{cfg['color']}"></div>
  <div class="strat-name">{cfg['sport']} {cfg['label']}</div>
  <div class="strat-bets">{n}</div>
  <div class="strat-rec">{w}–{n-w}</div>
  <div class="strat-winpct">{wp:.0%}</div>
  <div class="strat-units" style="color:{uc_}">{u:+.2f}</div>
  <div class="strat-roi" style="color:{rc_}">{roi:+.1f}%</div>
</div>"""
                st.markdown(
                    f'<div style="background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:.75rem 1.25rem">{rows_html}</div>',
                    unsafe_allow_html=True,
                )

            with col_right:
                st.markdown("<div class='sh'>Monthly P&L</div>", unsafe_allow_html=True)
                combined["month"] = combined["date"].dt.to_period("M").astype(str)
                mo = combined.groupby("month")["units"].sum().reset_index()
                mo_colors = ["#22c55e" if u >= 0 else "#ef4444" for u in mo["units"]]
                fig3 = go.Figure(go.Bar(
                    x=mo["month"], y=mo["units"] * unit_size,
                    marker_color=mo_colors, marker_line_width=0,
                    text=[f"${v*unit_size:+,.0f}" for v in mo["units"]],
                    textposition="outside", textfont=dict(color="#8090a8", size=10),
                ))
                fig3.add_hline(y=0, line_color="#1e2d42", line_width=1)
                fig3.update_layout(height=310, yaxis_title="$ P&L", **_CHART)
                st.plotly_chart(fig3, use_container_width=True)

            # Recent bets + Best/Worst
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("<div class='sh'>Recent bets — last 25</div>", unsafe_allow_html=True)
                recent   = combined.sort_values("date", ascending=False).head(25)
                log_html = ""
                for _, r in recent.iterrows():
                    rc  = "#22c55e" if r["result"] == "WIN" else "#ef4444"
                    ec  = "#22c55e" if r["edge"] > 0 else "#ef4444"
                    uc_ = "#22c55e" if r["units"] >= 0 else "#ef4444"
                    d   = r["date"].strftime("%b %d")
                    log_html += f"""
<div class="log-row">
  <div class="log-date">{d}</div>
  <div class="log-sport">{r['sport']}</div>
  <div class="log-desc">{r['desc'][:30]}</div>
  <div class="log-edge" style="color:{ec}">{r['edge']:+.1%}</div>
  <div class="log-units" style="color:{uc_}">{r['units']:+.2f}u</div>
  <div class="log-result" style="color:{rc}">{'✓ W' if r['result']=='WIN' else '✗ L'}</div>
</div>"""
                st.markdown(
                    f'<div style="background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:.75rem 1.25rem">'
                    f'<div style="display:flex;padding:0 0 6px;border-bottom:1px solid #1e2d42;'
                    f'font-size:10px;color:#7a8fa8;letter-spacing:.06em;text-transform:uppercase">'
                    f'<div style="width:68px">Date</div><div style="width:36px">Sport</div>'
                    f'<div style="flex:1">Bet</div><div style="width:60px;text-align:right">Edge</div>'
                    f'<div style="width:60px;text-align:right">Units</div>'
                    f'<div style="width:44px;text-align:right">Result</div></div>'
                    f'{log_html}</div>',
                    unsafe_allow_html=True,
                )

            with col_b:
                st.markdown("<div class='sh'>Best &amp; worst bets</div>", unsafe_allow_html=True)
                top5    = combined.nlargest(5,  "units")
                bottom5 = combined.nsmallest(5, "units")

                def _highlight_log(rows_df, header):
                    html = f'<div style="font-size:10px;color:#8090a8;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-bottom:6px">{header}</div>'
                    for _, r in rows_df.iterrows():
                        rc  = "#22c55e" if r["result"] == "WIN" else "#ef4444"
                        uc_ = "#22c55e" if r["units"] >= 0 else "#ef4444"
                        d   = r["date"].strftime("%b %d")
                        html += f"""
<div class="log-row">
  <div class="log-date">{d}</div>
  <div class="log-sport" style="color:#8090a8">{r['sport']}</div>
  <div class="log-desc">{r['desc'][:26]}</div>
  <div class="log-units" style="color:{uc_};width:64px;text-align:right">{r['units']:+.2f}u</div>
  <div class="log-result" style="color:{rc};width:44px;text-align:right">{'✓ W' if r['result']=='WIN' else '✗ L'}</div>
</div>"""
                    return html

                st.markdown(
                    f'<div style="background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:.75rem 1.25rem;margin-bottom:10px">'
                    f'{_highlight_log(top5, "🏆 Top wins")}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div style="background:#131d2e;border:1px solid #1e2d42;border-radius:10px;padding:.75rem 1.25rem">'
                    f'{_highlight_log(bottom5, "📉 Biggest losses")}</div>',
                    unsafe_allow_html=True,
                )

    # ════════════════════════════════════════════════════════════════════════
    # TAB 2 — CUSTOM PARLAYS
    # ════════════════════════════════════════════════════════════════════════
    with tab_parlay:

        parlays = _load_parlays(start_date)

        # ── Parlay stats strip ────────────────────────────────────────────────
        resolved = parlays[parlays["status"].isin(["won", "lost"])] if not parlays.empty else pd.DataFrame()
        p_wins   = (resolved["status"] == "won").sum()  if not resolved.empty else 0
        p_total  = len(resolved)
        p_units  = resolved["pnl"].sum()                if not resolved.empty else 0.0
        p_roi    = (p_units / p_total * 100)            if p_total > 0 else 0.0
        p_pend   = len(parlays[parlays["status"] == "pending"]) if not parlays.empty else 0
        p_units_c = "#22c55e" if p_units >= 0 else "#ef4444"

        st.markdown(f"""
<div class="prl-stat-strip">
  <div class="prl-stat-item">
    <span class="prl-stat-val">{len(parlays) if not parlays.empty else 0}</span>
    <span class="prl-stat-lbl">Total Parlays</span>
  </div>
  <div class="prl-stat-item">
    <span class="prl-stat-val">{p_wins}–{p_total - p_wins}</span>
    <span class="prl-stat-lbl">Record</span>
  </div>
  <div class="prl-stat-item">
    <span class="prl-stat-val" style="color:{p_units_c}">{p_units:+.2f}u</span>
    <span class="prl-stat-lbl">Units P&amp;L</span>
  </div>
  <div class="prl-stat-item">
    <span class="prl-stat-val" style="color:{p_units_c}">${p_units * unit_size:+,.0f}</span>
    <span class="prl-stat-lbl">Dollar P&amp;L</span>
  </div>
  <div class="prl-stat-item">
    <span class="prl-stat-val" style="color:{p_units_c}">{p_roi:+.1f}%</span>
    <span class="prl-stat-lbl">ROI</span>
  </div>
  <div class="prl-stat-item">
    <span class="prl-stat-val" style="color:#f59e0b;">{p_pend}</span>
    <span class="prl-stat-lbl">Pending</span>
  </div>
</div>""", unsafe_allow_html=True)

        # ── Two-column layout ─────────────────────────────────────────────────
        pcol_log, pcol_form = st.columns([3, 2], gap="large")

        # ── LEFT: Parlay history ──────────────────────────────────────────────
        with pcol_log:
            st.markdown("<div class='sh'>Parlay History</div>", unsafe_allow_html=True)

            if parlays.empty:
                st.markdown("""
<div style="background:#0f1828;border:1px dashed #1e2d42;border-radius:10px;
     padding:2rem;text-align:center;color:#8090a8">
  No custom parlays logged yet.<br>
  <span style="font-size:.8rem;color:#7a8fa8">Use the form → to log your first parlay.</span>
</div>""", unsafe_allow_html=True)
            else:
                # Column header
                st.markdown("""
<div style="display:flex;padding:4px 0 6px;border-bottom:1px solid #1e2d42;
     font-size:10px;color:#7a8fa8;letter-spacing:.06em;text-transform:uppercase;gap:.5rem">
  <div style="width:68px">Date</div>
  <div style="flex:1">Parlay</div>
  <div style="width:60px;text-align:right">Odds</div>
  <div style="width:56px;text-align:right">Units</div>
  <div style="width:64px;text-align:right">P&amp;L</div>
  <div style="width:70px;text-align:right">Status</div>
</div>""", unsafe_allow_html=True)

                rows_html = ""
                for _, p in parlays.iterrows():
                    status    = str(p["status"]).lower()
                    pnl_val   = p["pnl"] if pd.notna(p.get("pnl")) else None
                    pnl_str   = f"{pnl_val * unit_size:+,.0f}" if pnl_val is not None else "—"
                    pnl_c     = ("#22c55e" if pnl_val and pnl_val >= 0 else "#ef4444") if pnl_val is not None else "#8090a8"
                    status_c  = "#22c55e" if status == "won" else ("#ef4444" if status == "lost" else "#f59e0b")
                    status_lbl= {"won": "✓ WON", "lost": "✗ LOST", "pending": "⏳ OPEN"}.get(status, status.upper())
                    legs_txt  = str(p.get("legs") or "").strip()
                    legs_disp = (legs_txt[:55] + "…") if len(legs_txt) > 55 else legs_txt
                    n_legs    = int(p.get("n_legs", 2))
                    legs_badge= f'<span style="font-size:.68rem;background:#0e1828;border:1px solid #1e2d42;border-radius:10px;padding:1px 7px;color:#7a8fa8;margin-right:5px">{n_legs}-leg</span>'

                    rows_html += f"""
<div class="prl-row">
  <div class="prl-date">{p['bet_date'].strftime('%b %d')}</div>
  <div style="flex:1;min-width:0">
    <div style="color:#f0f2f5;font-weight:600;font-size:13px">{p['label']}</div>
    <div style="color:#8090a8;font-size:11px;margin-top:3px">{legs_badge}{legs_disp}</div>
  </div>
  <div class="prl-odds">{_fmt_odds(p['combined_odds'])}</div>
  <div class="prl-units">{float(p['units']):.2f}u</div>
  <div class="prl-pnl" style="color:{pnl_c}">${pnl_str}</div>
  <div class="prl-status" style="color:{status_c}">{status_lbl}</div>
</div>"""

                st.markdown(
                    f'<div style="background:#131d2e;border:1px solid #1e2d42;border-radius:10px;'
                    f'padding:.75rem 1.25rem">{rows_html}</div>',
                    unsafe_allow_html=True,
                )

                # Cumulative parlay P&L chart
                if not resolved.empty:
                    st.markdown("<div class='sh' style='margin-top:1.25rem'>Parlay Cumulative P&L</div>", unsafe_allow_html=True)
                    resolved_sorted = resolved.sort_values("bet_date").copy()
                    resolved_sorted["cum"] = resolved_sorted["pnl"].cumsum()
                    p_cum_color = "#22c55e" if p_units >= 0 else "#ef4444"
                    figp = go.Figure()
                    figp.add_scatter(
                        x=resolved_sorted["bet_date"], y=resolved_sorted["cum"] * unit_size,
                        mode="lines+markers",
                        line=dict(color=p_cum_color, width=2),
                        marker=dict(size=6, color=p_cum_color),
                        fill="tozeroy",
                        fillcolor=f"rgba({'34,197,94' if p_units >= 0 else '239,68,68'},0.07)",
                        hovertemplate="%{x}<br>%{y:+,.0f}<extra></extra>",
                    )
                    figp.add_hline(y=0, line_color="#1e2d42", line_width=1)
                    figp.update_layout(height=200, yaxis_title=f"$ P&L (1u=${unit_size})", **_CHART)
                    st.plotly_chart(figp, use_container_width=True)

        # ── RIGHT: Forms ──────────────────────────────────────────────────────
        with pcol_form:

            # ── Log a new parlay ──────────────────────────────────────────────
            st.markdown("<div class='sh'>Log New Parlay</div>", unsafe_allow_html=True)
            st.markdown('<div class="prl-form-card">', unsafe_allow_html=True)

            with st.form("log_parlay_form", clear_on_submit=True):
                prl_label = st.text_input(
                    "Parlay label",
                    placeholder="e.g. 3-leg SGP — Lakers / Celtics / Heat",
                    help="Short name to identify this parlay",
                )
                prl_legs = st.text_area(
                    "Legs (describe each leg)",
                    placeholder="LAL ML -110\nBOS -5.5 -115\nMIA Over 218.5 -108",
                    height=100,
                    help="One leg per line — team, market, odds",
                )
                fc1, fc2 = st.columns(2)
                with fc1:
                    prl_n_legs = st.number_input("# of legs", min_value=2, max_value=20, value=2, step=1)
                with fc2:
                    prl_units = st.number_input("Units wagered", min_value=0.01, max_value=100.0,
                                                value=1.0, step=0.25,
                                                help="How many units you're putting on this parlay")
                prl_odds = st.number_input(
                    "Combined parlay odds (American)",
                    min_value=-10000, max_value=100000,
                    value=300, step=10,
                    help="E.g. +300 for a 3-leg parlay at +300"
                )
                prl_date = st.date_input("Bet date", value=date.today())
                prl_notes = st.text_input("Notes (optional)", placeholder="Context, book used, etc.")

                # Live payout preview
                if prl_odds > 0:
                    payout_per_unit = prl_odds / 100
                else:
                    payout_per_unit = 100 / abs(prl_odds)
                potential = prl_units * payout_per_unit * unit_size
                risk      = prl_units * unit_size

                st.markdown(f"""
<div style="background:#131d2e;border:1px solid #1e2d42;border-radius:8px;
     padding:.65rem 1rem;margin:.5rem 0;display:flex;gap:1.5rem">
  <div>
    <div style="font-size:.68rem;color:#7a8fa8;text-transform:uppercase;letter-spacing:.06em">Risk</div>
    <div style="font-size:.95rem;font-weight:700;color:#ef4444">${risk:,.0f}</div>
  </div>
  <div>
    <div style="font-size:.68rem;color:#7a8fa8;text-transform:uppercase;letter-spacing:.06em">To win</div>
    <div style="font-size:.95rem;font-weight:700;color:#22c55e">${potential:,.0f}</div>
  </div>
  <div>
    <div style="font-size:.68rem;color:#7a8fa8;text-transform:uppercase;letter-spacing:.06em">Payout mult</div>
    <div style="font-size:.95rem;font-weight:700;color:#60a5fa">{payout_per_unit:.2f}x</div>
  </div>
</div>""", unsafe_allow_html=True)

                submitted = st.form_submit_button("➕ Log Parlay", use_container_width=True,
                                                   type="primary")
                if submitted:
                    if not prl_label.strip():
                        st.error("Please enter a parlay label.")
                    else:
                        _save_parlay(
                            prl_label.strip(), prl_legs.strip(),
                            int(prl_n_legs), float(prl_odds),
                            float(prl_units), prl_date, prl_notes.strip(),
                        )
                        st.success(f"✅ Parlay logged: **{prl_label}**")
                        st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

            # ── Mark result ───────────────────────────────────────────────────
            st.markdown("<div class='sh' style='margin-top:1.25rem'>Mark Result</div>", unsafe_allow_html=True)

            pending = parlays[parlays["status"] == "pending"] if not parlays.empty else pd.DataFrame()

            if pending.empty:
                st.markdown("""
<div class="prl-form-card" style="text-align:center;color:#8090a8;padding:1.5rem">
  No pending parlays — log one above.
</div>""", unsafe_allow_html=True)
            else:
                st.markdown('<div class="prl-form-card">', unsafe_allow_html=True)
                with st.form("mark_result_form", clear_on_submit=True):
                    parlay_options = {
                        f"{p['label']}  ({_fmt_odds(p['combined_odds'])} · {p['bet_date'].strftime('%b %d')})": p
                        for _, p in pending.iterrows()
                    }
                    chosen_key = st.selectbox(
                        "Select parlay",
                        options=list(parlay_options.keys()),
                        label_visibility="visible",
                    )
                    result_choice = st.radio(
                        "Result",
                        ["Won 🎉", "Lost 📉"],
                        horizontal=True,
                    )
                    mark_sub = st.form_submit_button("✔ Confirm Result", use_container_width=True,
                                                      type="primary")
                    if mark_sub and chosen_key:
                        chosen = parlay_options[chosen_key]
                        status = "won" if result_choice.startswith("Won") else "lost"
                        _update_parlay_result(
                            int(chosen["id"]), status,
                            float(chosen["combined_odds"]),
                            float(chosen["units"]),
                        )
                        pnl_val = _calc_pnl(float(chosen["combined_odds"]), float(chosen["units"]),
                                             status == "won")
                        emoji = "🎉" if status == "won" else "📉"
                        st.success(
                            f"{emoji} Marked **{chosen['label']}** as {status.upper()} "
                            f"— {pnl_val * unit_size:+,.0f} (${pnl_val:+.2f}u)"
                        )
                        st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)

            # ── Delete a parlay ───────────────────────────────────────────────
            if not parlays.empty:
                with st.expander("🗑 Delete a parlay", expanded=False):
                    del_options = {
                        f"[{p['status'].upper()}] {p['label']}  ({p['bet_date'].strftime('%b %d')})": int(p["id"])
                        for _, p in parlays.iterrows()
                    }
                    del_key = st.selectbox("Select parlay to delete", list(del_options.keys()),
                                           key="del_parlay")
                    if st.button("Delete", type="secondary", use_container_width=True):
                        _delete_parlay(del_options[del_key])
                        st.rerun()
