import sys, os
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.graph_objects as go
from pathlib import Path
from config import DB_PATH

_CSS = """
<style>
.block-container{padding-top:1.5rem;padding-bottom:2rem;max-width:1200px}
[data-testid="metric-container"]{background:#16161a;border:1px solid #222228;border-radius:10px;padding:1rem 1.25rem}
[data-testid="metric-container"] label{color:#6b6b78!important;font-size:11px!important;letter-spacing:.06em;text-transform:uppercase}
[data-testid="stMetricValue"]{color:#e8e8ec!important;font-size:22px!important;font-weight:600!important}
.sh{font-size:11px;font-weight:600;letter-spacing:.1em;color:#44444f;text-transform:uppercase;margin:1.5rem 0 .75rem;padding-bottom:8px;border-bottom:1px solid #1e1e24}
.card{background:#16161a;border:1px solid #222228;border-radius:12px;padding:1.25rem 1.5rem;margin-bottom:10px}
.ph{background:#16161a;border:1px solid #222228;border-radius:12px;padding:1.5rem 2rem;margin-bottom:1.5rem}
.gr{display:flex;align-items:center;padding:8px 0;border-bottom:1px solid #1a1a20;font-size:13px}
.gr:last-child{border-bottom:none}
.hit{color:#22c55e;font-weight:600}
.miss{color:#ef4444;font-weight:600}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;letter-spacing:.04em}
.bg{background:#0d2a0d;color:#22c55e;border:1px solid #1a4a1a}
.br{background:#2a0d0d;color:#ef4444;border:1px solid #4a1a1a}
.bn{background:#1a1a20;color:#6b6b78;border:1px solid #2a2a32}
</style>
"""

_CHART_LAYOUT = dict(
    paper_bgcolor="#16161a", plot_bgcolor="#16161a",
    margin=dict(l=0, r=0, t=10, b=0),
    xaxis=dict(showgrid=False, color="#44444f"),
    yaxis=dict(gridcolor="#1e1e24", color="#44444f", zeroline=False),
    legend=dict(font=dict(color="#9090a0", size=11), bgcolor="rgba(0,0,0,0)"),
    font=dict(color="#9090a0"),
)

STAT_LABELS = {"pts": "Points", "reb": "Rebounds", "ast": "Assists",
               "fg3m": "3-Pointers", "stl": "Steals", "blk": "Blocks"}

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

def _hit_rate(series, line, direction="over"):
    return (series > line).mean() if direction == "over" else (series < line).mean()


def render():
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown("<div class='sh'>Player research</div>", unsafe_allow_html=True)

    players_df = _load("SELECT DISTINCT player_name FROM player_stats ORDER BY player_name")
    if players_df.empty:
        st.warning("No player data. Run `python props.py` first.")
        return

    teams_df     = _load("SELECT DISTINCT team_name FROM games WHERE team_name IS NOT NULL ORDER BY team_name")
    team_options = ["All opponents"] + (teams_df["team_name"].tolist() if not teams_df.empty else [])

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: selected_player = st.selectbox("Player", players_df["player_name"].tolist())
    with c2: opp_team = st.selectbox("vs Opponent", team_options)
    with c3: prop_stat = st.selectbox("Stat", list(STAT_LABELS.keys()), format_func=lambda x: STAT_LABELS[x])
    with c4: prop_line = st.number_input("Line", min_value=0.0, max_value=80.0, value=20.0, step=0.5)
    with c5: prop_window = st.selectbox("Last N games", [5, 10, 15, 20], index=1)

    opp_arg = opp_team if opp_team != "All opponents" else None
    df = _load("""
        SELECT ps.*, g.matchup, g.wl, g.is_home, g.team_name, g.team_abbreviation
        FROM player_stats ps
        LEFT JOIN games g ON ps.game_id = g.game_id AND g.team_abbreviation = ps.team_abbrev
        WHERE ps.player_name = ?
        ORDER BY ps.game_date DESC
    """, params=(selected_player,))
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
        if opp_arg:
            df = df[df["matchup"].str.contains(opp_arg[:3].upper(), na=False, case=False)]

    if df.empty:
        st.markdown("""
<div style="background:#16161a;border:1px solid #222228;border-radius:12px;padding:2rem;text-align:center">
  <div style="font-size:16px;color:#6b6b78;margin-bottom:8px">No data found</div>
  <div style="font-size:13px;color:#44444f">
    Run <code style="background:#1e1e24;padding:2px 6px;border-radius:4px;color:#9090a0">python props.py</code> to pull player game logs.
  </div>
</div>
""", unsafe_allow_html=True)
        return

    df_recent   = df.head(prop_window).copy()
    stat_series = df_recent[prop_stat].astype(float)
    team        = df.iloc[0].get("team_name", "")
    latest      = df["game_date"].max().strftime("%b %d, %Y")
    gp          = len(df)
    avg         = stat_series.mean()
    high        = stat_series.max()
    low         = stat_series.min()
    std         = stat_series.std() if len(stat_series) > 1 else 0
    ho          = _hit_rate(stat_series, prop_line, "over")
    hu          = _hit_rate(stat_series, prop_line, "under")
    hits        = int(ho * len(stat_series))

    badge_cls = "bg" if ho >= 0.6 else ("br" if ho <= 0.4 else "bn")
    badge_txt = f"OVER {ho:.0%}" if ho >= 0.5 else f"UNDER {hu:.0%}"
    opp_tag   = f"&nbsp;·&nbsp; vs {opp_team}" if opp_team != "All opponents" else ""

    st.markdown(f"""
<div class="ph">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
    <div>
      <div style="font-size:26px;font-weight:700;color:#e8e8ec;letter-spacing:-.5px">{selected_player}</div>
      <div style="font-size:13px;color:#6b6b78;margin-top:4px">
        {team} &nbsp;·&nbsp; Last game: {latest} &nbsp;·&nbsp; {gp} games in DB{opp_tag}
      </div>
    </div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <span class="badge {badge_cls}">{badge_txt} last {prop_window}</span>
      <span class="badge bn">{STAT_LABELS.get(prop_stat,'').upper()} line {prop_line}</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<div class='sh'>Prop line analysis</div>", unsafe_allow_html=True)
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric(f"Avg {STAT_LABELS.get(prop_stat,'Stat')} L{prop_window}", f"{avg:.1f}")
    m2.metric("Std dev",   f"{std:.1f}")
    m3.metric("High",      f"{high:.0f}")
    m4.metric("Low",       f"{low:.0f}")
    m5.metric(f"Over {prop_line}", f"{ho:.1%}", delta=f"{hits}/{len(stat_series)} games")
    m6.metric(f"Under {prop_line}", f"{hu:.1%}")

    st.markdown(f"<div class='sh'>{STAT_LABELS.get(prop_stat,'Stat')} — last 20 games</div>",
                unsafe_allow_html=True)
    df_plot    = df.sort_values("game_date").tail(20).copy()
    x          = df_plot["game_date"]
    y          = df_plot[prop_stat].astype(float)
    bar_colors = ["#22c55e" if v >= prop_line else "#ef4444" for v in y]
    roll5      = y.reset_index(drop=True).rolling(5, min_periods=1).mean()
    fig = go.Figure()
    fig.add_bar(x=x, y=y, marker_color=bar_colors, marker_line_width=0,
                name=STAT_LABELS.get(prop_stat, ""))
    fig.add_scatter(x=x, y=roll5.values, mode="lines",
                    line=dict(color="#f59e0b", width=1.5, dash="dot"), name="5-game avg")
    if prop_line > 0:
        fig.add_hline(y=prop_line, line_color="#ffffff", line_width=1, line_dash="dash",
                      annotation_text=f"Line: {prop_line}", annotation_font_color="#ffffff",
                      annotation_position="top right")
    fig.update_layout(height=220, **_CHART_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("<div class='sh'>Manual line comparison</div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:12px;color:#44444f;margin-bottom:1rem'>Enter lines from DraftKings, FanDuel, etc. Leave at 0 to skip.</div>",
                unsafe_allow_html=True)

    props_to_check = [("pts","Points"),("reb","Rebounds"),("ast","Assists"),
                      ("fg3m","3-Pointers"),("stl","Steals"),("blk","Blocks")]
    col_a, col_b = st.columns(2)
    input_lines = {}
    for i, (stat, label) in enumerate(props_to_check):
        with (col_a if i % 2 == 0 else col_b):
            input_lines[stat] = st.number_input(f"{label} line", min_value=0.0, max_value=80.0,
                                                value=0.0, step=0.5, key=f"line_{stat}")

    rows = []
    for stat, label in props_to_check:
        line = input_lines[stat]
        if line == 0:
            continue
        s   = df.head(prop_window)[stat].astype(float)
        ho2 = _hit_rate(s, line, "over")
        hu2 = _hit_rate(s, line, "under")
        l5  = df.head(5)[stat].astype(float).mean()
        l10 = df.head(10)[stat].astype(float).mean()
        l20 = df.head(20)[stat].astype(float).mean()
        if ho2 >= 0.65:   rec, rcls = "OVER",       "bg"
        elif hu2 >= 0.65: rec, rcls = "UNDER",      "br"
        elif ho2 > hu2:   rec, rcls = "LEAN OVER",  "bn"
        else:             rec, rcls = "LEAN UNDER", "bn"
        rows.append({"stat": stat, "label": label, "line": line,
                     "l5": l5, "l10": l10, "l20": l20,
                     "ho": ho2, "hu": hu2, "rec": rec, "rcls": rcls})

    if rows:
        for r in rows:
            ow = int(r["ho"] * 100); uw = 100 - ow
            ac = "#22c55e" if r["l10"] > r["line"] else "#ef4444"
            bc = "#22c55e" if r["ho"] >= 0.65 else ("#ef4444" if r["ho"] <= 0.35 else "#f59e0b")
            st.markdown(f"""
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
    <div>
      <span style="font-size:15px;font-weight:600;color:#e8e8ec">{r['label']}</span>
      <span style="font-size:13px;color:#44444f;margin-left:10px">line: {r['line']}</span>
    </div>
    <span class="badge {r['rcls']}">{r['rec']}</span>
  </div>
  <div style="display:flex;gap:20px;font-size:13px;margin-bottom:12px;flex-wrap:wrap">
    <div><span style="color:#44444f">Avg L5</span> <span style="color:{ac};font-weight:600;margin-left:8px">{r['l5']:.1f}</span></div>
    <div><span style="color:#44444f">Avg L10</span> <span style="color:{ac};font-weight:600;margin-left:8px">{r['l10']:.1f}</span></div>
    <div><span style="color:#44444f">Avg L20</span> <span style="color:#e8e8ec;margin-left:8px">{r['l20']:.1f}</span></div>
    <div><span style="color:#44444f">Over rate</span> <span style="color:#22c55e;font-weight:600;margin-left:8px">{r['ho']:.0%}</span></div>
    <div><span style="color:#44444f">Under rate</span> <span style="color:#ef4444;font-weight:600;margin-left:8px">{r['hu']:.0%}</span></div>
  </div>
  <div style="display:flex;align-items:center;gap:10px">
    <span style="font-size:11px;color:#22c55e;width:36px">OVER</span>
    <div style="flex:1;background:#222228;border-radius:3px;height:6px;overflow:hidden">
      <div style="width:{ow}%;height:100%;background:{bc};border-radius:3px"></div>
    </div>
    <span style="font-size:11px;color:#ef4444;width:42px;text-align:right">UNDER</span>
  </div>
  <div style="display:flex;justify-content:space-between;font-size:11px;color:#44444f;margin-top:3px">
    <span>{ow}%</span><span>{uw}%</span>
  </div>
</div>
""", unsafe_allow_html=True)
    else:
        st.markdown("""
<div style="background:#16161a;border:1px solid #222228;border-radius:10px;padding:1.25rem 1.5rem;color:#44444f;font-size:13px">
  Enter lines above to see over/under analysis
</div>
""", unsafe_allow_html=True)

    st.markdown("<div class='sh'>Scoring profile — last 20 games</div>", unsafe_allow_html=True)
    df_multi = df.sort_values("game_date").tail(20)
    fig2 = go.Figure()
    for stat, label, color in [("pts","Points","#4f8ef7"),("reb","Rebounds","#22c55e"),
                                ("ast","Assists","#f59e0b"),("fg3m","3PM","#a78bfa")]:
        if stat in df_multi.columns:
            fig2.add_scatter(x=df_multi["game_date"], y=df_multi[stat].astype(float),
                             mode="lines+markers", name=label,
                             line=dict(color=color, width=2), marker=dict(size=4, color=color))
    fig2.update_layout(height=260, **_CHART_LAYOUT)
    st.plotly_chart(fig2, use_container_width=True)

    if opp_team != "All opponents" and not df.empty:
        st.markdown(f"<div class='sh'>vs {opp_team} — historical breakdown</div>", unsafe_allow_html=True)
        co1, co2 = st.columns(2)
        with co1:
            rows_html = "".join([
                f'<div style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid #1a1a20;font-size:13px">'
                f'<span style="color:#6b6b78">{lbl}</span>'
                f'<span style="color:#e8e8ec;font-weight:500">{df[s].astype(float).mean():.1f}</span></div>'
                for s, lbl in [("pts","Points"),("reb","Rebounds"),("ast","Assists"),
                               ("fg3m","3PM"),("stl","Steals"),("blk","Blocks")]
            ])
            st.markdown(f"""
<div class="card">
  <div style="font-size:12px;color:#44444f;letter-spacing:.05em;text-transform:uppercase;margin-bottom:12px">Averages vs {opp_team[:20]}</div>
  {rows_html}
  <div style="display:flex;justify-content:space-between;padding:7px 0;font-size:13px">
    <span style="color:#6b6b78">Games played</span>
    <span style="color:#e8e8ec;font-weight:500">{len(df)}</span>
  </div>
</div>
""", unsafe_allow_html=True)
        with co2:
            log_rows = ""
            for _, row in df.head(8).iterrows():
                wlc = "#22c55e" if row.get("wl") == "W" else "#ef4444"
                d   = pd.to_datetime(row["game_date"]).strftime("%b %d, %Y")
                log_rows += f"""
<div class="gr">
  <span style="color:#44444f;width:90px;font-size:12px">{d}</span>
  <span style="color:{wlc};width:24px;font-weight:600">{row.get('wl','')}</span>
  <span style="color:#e8e8ec;width:36px">{int(row['pts'])}</span>
  <span style="color:#6b6b78;font-size:12px">{int(row['reb'])}r &nbsp;{int(row['ast'])}a &nbsp;{int(row['fg3m'])}3</span>
</div>"""
            st.markdown(f"""
<div class="card">
  <div style="font-size:12px;color:#44444f;letter-spacing:.05em;text-transform:uppercase;margin-bottom:12px">Game log</div>
  {log_rows}
</div>
""", unsafe_allow_html=True)

    n_show = min(20, len(df))
    st.markdown(f"<div class='sh'>Game log — last {n_show} games</div>", unsafe_allow_html=True)
    log_rows = ""
    for _, row in df.head(20).iterrows():
        val  = float(row.get(prop_stat, 0))
        hit  = val >= prop_line
        vcls = "hit" if hit else "miss"
        wlc  = "#22c55e" if row.get("wl") == "W" else "#ef4444"
        d    = pd.to_datetime(row["game_date"]).strftime("%b %d")
        mtch = str(row.get("matchup", ""))[:24]
        log_rows += f"""
<div class="gr">
  <span style="color:#44444f;width:56px;font-size:12px">{d}</span>
  <span style="color:#6b6b78;flex:1;font-size:12px">{mtch}</span>
  <span style="color:{wlc};width:20px;font-size:12px;font-weight:600">{row.get('wl','')}</span>
  <span style="color:#9090a0;width:32px;font-size:12px;text-align:right">{int(row['pts'])}</span>
  <span style="color:#9090a0;width:28px;font-size:12px;text-align:right">{int(row['reb'])}</span>
  <span style="color:#9090a0;width:28px;font-size:12px;text-align:right">{int(row['ast'])}</span>
  <span style="color:#9090a0;width:28px;font-size:12px;text-align:right">{int(row['fg3m'])}</span>
  <span class="{vcls}" style="width:52px;text-align:right">{val:.0f} {"✓" if hit else "✗"}</span>
</div>"""
    st.markdown(f"""
<div class="card">
  <div style="display:flex;padding:0 0 8px;border-bottom:1px solid #1e1e24;
    font-size:11px;color:#44444f;letter-spacing:.04em;text-transform:uppercase">
    <span style="width:56px">Date</span>
    <span style="flex:1">Matchup</span>
    <span style="width:20px">W/L</span>
    <span style="width:32px;text-align:right">PTS</span>
    <span style="width:28px;text-align:right">REB</span>
    <span style="width:28px;text-align:right">AST</span>
    <span style="width:28px;text-align:right">3PM</span>
    <span style="width:52px;text-align:right">{STAT_LABELS.get(prop_stat,'')} vs {prop_line}</span>
  </div>
  {log_rows}
</div>
""", unsafe_allow_html=True)
