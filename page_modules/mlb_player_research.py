import sys, os
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sqlite3
from pathlib import Path
from mlb_config import MLB_DB_PATH

_CSS = """
<style>
.block-container{padding-top:1.5rem;padding-bottom:2rem;max-width:1200px}
[data-testid="metric-container"]{background:#13131a;border:1px solid #1e1e28;border-radius:10px;padding:1rem 1.25rem}
[data-testid="metric-container"] label{color:#6b6b78!important;font-size:11px!important;letter-spacing:.06em;text-transform:uppercase}
[data-testid="stMetricValue"]{color:#e8e8ec!important;font-size:22px!important;font-weight:600!important}
.sh{font-size:11px;font-weight:600;letter-spacing:.1em;color:#44444f;text-transform:uppercase;margin:1.5rem 0 .75rem;padding-bottom:8px;border-bottom:1px solid #1e1e28}
.card{background:#13131a;border:1px solid #1e1e28;border-radius:12px;padding:1.25rem 1.5rem;margin-bottom:10px}
.ph{background:#13131a;border:1px solid #1e1e28;border-radius:12px;padding:1.5rem 2rem;margin-bottom:1.5rem}
.gr{display:flex;align-items:center;padding:8px 0;border-bottom:1px solid #1a1a24;font-size:13px}
.gr:last-child{border-bottom:none}
.hit{color:#22c55e;font-weight:600}
.miss{color:#ef4444;font-weight:600}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;letter-spacing:.04em}
.bg{background:#0d2a0d;color:#22c55e;border:1px solid #1a4a1a}
.br{background:#2a0d0d;color:#ef4444;border:1px solid #4a1a1a}
.bn{background:#1a1a20;color:#6b6b78;border:1px solid #2a2a32}
.by{background:#2a1f0d;color:#f59e0b;border:1px solid #4a380d}
</style>
"""

_CHART = dict(
    paper_bgcolor="#13131a", plot_bgcolor="#13131a",
    margin=dict(l=0, r=0, t=10, b=0),
    xaxis=dict(showgrid=False, color="#44444f"),
    yaxis=dict(gridcolor="#1e1e28", color="#44444f", zeroline=False),
    legend=dict(font=dict(color="#9090a0", size=11), bgcolor="rgba(0,0,0,0)"),
    font=dict(color="#9090a0"),
)

STAT_LABELS = {
    "k":    "Strikeouts (K)",
    "ip":   "Innings Pitched",
    "er":   "Earned Runs",
    "h":    "Hits Allowed",
    "bb":   "Walks (BB)",
}

STAT_DEFAULTS = {"k": 5.5, "ip": 5.5, "er": 2.5, "h": 6.5, "bb": 2.5}


def _load(query, params=None):
    if not Path(MLB_DB_PATH).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(MLB_DB_PATH)
    try:
        df = pd.read_sql(query, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def _hit_rate(series, line, direction="over"):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return 0.5
    return float((s > line).mean() if direction == "over" else (s < line).mean())


def render():
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown("""
<div style="margin-bottom:1rem">
  <div style="font-size:22px;font-weight:700;color:#e8e8ec;letter-spacing:-.3px">⚾ Pitcher Research</div>
  <div style="font-size:13px;color:#6b6b78;margin-top:4px">
    Analyse starting pitcher props — strikeouts, innings, earned runs and more.
  </div>
</div>
""", unsafe_allow_html=True)

    pitchers_df = _load("""
        SELECT DISTINCT pitcher_name FROM mlb_pitcher_logs
        WHERE is_starter = 1
        ORDER BY pitcher_name
    """)
    if pitchers_df.empty:
        st.warning("No pitcher data found in the database.")
        return

    all_pitchers = pitchers_df["pitcher_name"].tolist()

    # ── Filter row ──────────────────────────────────────────────────────────
    fc1, fc2, fc3, fc4, fc5 = st.columns([2, 2, 1, 1, 1])
    with fc1:
        st.caption("Search pitcher")
        search = st.text_input("Search pitcher", placeholder="Type name to filter…",
                               label_visibility="collapsed", key="pitcher_search")
    filtered = [p for p in all_pitchers if search.lower() in p.lower()] if search else all_pitchers
    with fc2:
        st.caption("Pitcher")
        if not filtered:
            st.caption("No pitchers match that search.")
            return
        selected = st.selectbox("Pitcher", filtered, label_visibility="collapsed")
    with fc3:
        st.caption("Stat")
        prop_stat = st.selectbox("Stat", list(STAT_LABELS.keys()),
                                 format_func=lambda x: STAT_LABELS[x],
                                 label_visibility="collapsed")
    with fc4:
        st.caption("Line")
        prop_line = st.number_input("Line", min_value=0.0, max_value=30.0,
                                    value=STAT_DEFAULTS.get(prop_stat, 5.5),
                                    step=0.5, label_visibility="collapsed")
    with fc5:
        st.caption("Window")
        prop_window = st.selectbox("Last N starts", [5, 8, 10, 15], index=1,
                                   label_visibility="collapsed")

    # ── Load pitcher logs ────────────────────────────────────────────────────
    df = _load("""
        SELECT * FROM mlb_pitcher_logs
        WHERE pitcher_name = ? AND is_starter = 1
        ORDER BY game_date DESC
    """, params=(selected,))

    if df.empty:
        st.markdown("""
<div style="background:#13131a;border:1px solid #1e1e28;border-radius:12px;padding:2rem;text-align:center">
  <div style="font-size:16px;color:#6b6b78">No start history found for this pitcher.</div>
</div>
""", unsafe_allow_html=True)
        return

    df["game_date"] = pd.to_datetime(df["game_date"])
    df_recent   = df.head(prop_window).copy()
    stat_series = pd.to_numeric(df_recent[prop_stat], errors="coerce").dropna()

    team   = df.iloc[0].get("team", "")
    latest = df["game_date"].max().strftime("%b %d, %Y")
    n_gs   = len(df)
    avg    = stat_series.mean() if len(stat_series) else 0
    high   = stat_series.max() if len(stat_series) else 0
    low    = stat_series.min() if len(stat_series) else 0
    std    = stat_series.std() if len(stat_series) > 1 else 0
    ho     = _hit_rate(stat_series, prop_line, "over")
    hu     = _hit_rate(stat_series, prop_line, "under")
    hits   = int(ho * len(stat_series))

    badge_cls = "bg" if ho >= 0.6 else ("br" if ho <= 0.4 else "bn")
    badge_txt = f"OVER {ho:.0%}" if ho >= 0.5 else f"UNDER {hu:.0%}"
    stat_lbl  = STAT_LABELS.get(prop_stat, "")

    # Season stats lookup
    season_df = _load("""
        SELECT * FROM pitcher_season_stats WHERE pitcher_name = ?
        ORDER BY season DESC LIMIT 1
    """, params=(selected,))
    era_s   = float(season_df.iloc[0]["era"])  if not season_df.empty else None
    whip_s  = float(season_df.iloc[0]["whip"]) if not season_df.empty else None
    k9_s    = float(season_df.iloc[0]["k_per_9"]) if not season_df.empty and "k_per_9" in season_df.columns else None

    era_color  = "#22c55e" if era_s and era_s < 3.5 else ("#f59e0b" if era_s and era_s < 4.5 else "#ef4444")
    whip_color = "#22c55e" if whip_s and whip_s < 1.2 else ("#f59e0b" if whip_s and whip_s < 1.35 else "#ef4444")

    season_pills = ""
    if era_s is not None:
        season_pills += f'<div style="background:#0f0f12;border:1px solid #1e1e28;border-radius:8px;padding:10px 16px;text-align:center;min-width:80px"><div style="font-size:18px;font-weight:700;color:{era_color}">{era_s:.2f}</div><div style="font-size:10px;color:#44444f;text-transform:uppercase;letter-spacing:.06em;margin-top:2px">Season ERA</div></div>'
    if whip_s is not None:
        season_pills += f'<div style="background:#0f0f12;border:1px solid #1e1e28;border-radius:8px;padding:10px 16px;text-align:center;min-width:80px"><div style="font-size:18px;font-weight:700;color:{whip_color}">{whip_s:.2f}</div><div style="font-size:10px;color:#44444f;text-transform:uppercase;letter-spacing:.06em;margin-top:2px">Season WHIP</div></div>'
    if k9_s is not None:
        season_pills += f'<div style="background:#0f0f12;border:1px solid #1e1e28;border-radius:8px;padding:10px 16px;text-align:center;min-width:80px"><div style="font-size:18px;font-weight:700;color:#6366f1">{k9_s:.1f}</div><div style="font-size:10px;color:#44444f;text-transform:uppercase;letter-spacing:.06em;margin-top:2px">K/9</div></div>'

    st.markdown(f"""
<div class="ph">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
    <div>
      <div style="font-size:26px;font-weight:700;color:#e8e8ec;letter-spacing:-.5px">{selected}</div>
      <div style="font-size:13px;color:#6b6b78;margin-top:4px">
        {team} &nbsp;·&nbsp; Last start: {latest} &nbsp;·&nbsp; {n_gs} starts in DB
      </div>
      <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap">
        {season_pills}
      </div>
    </div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <span class="badge {badge_cls}">{badge_txt} last {prop_window} starts</span>
      <span class="badge bn">{stat_lbl.upper()} line {prop_line}</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Key metrics ──────────────────────────────────────────────────────────
    st.markdown("<div class='sh'>Prop analysis</div>", unsafe_allow_html=True)
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric(f"Avg {stat_lbl.split()[0]} L{prop_window}", f"{avg:.1f}")
    m2.metric("Std dev",  f"{std:.1f}")
    m3.metric("High",     f"{high:.0f}")
    m4.metric("Low",      f"{low:.0f}")
    m5.metric(f"Over {prop_line}", f"{ho:.1%}", delta=f"{hits}/{len(stat_series)} starts")
    m6.metric(f"Under {prop_line}", f"{hu:.1%}")

    # ── Bar chart ────────────────────────────────────────────────────────────
    st.markdown(f"<div class='sh'>{stat_lbl} — last 20 starts</div>", unsafe_allow_html=True)
    df_plot    = df.sort_values("game_date").tail(20).copy()
    x          = df_plot["game_date"]
    y          = pd.to_numeric(df_plot[prop_stat], errors="coerce").fillna(0)
    bar_colors = ["#22c55e" if v >= prop_line else "#ef4444" for v in y]
    roll5      = y.reset_index(drop=True).rolling(5, min_periods=1).mean()

    fig = go.Figure()
    fig.add_bar(x=x, y=y, marker_color=bar_colors, marker_line_width=0, name=stat_lbl)
    fig.add_scatter(x=x, y=roll5.values, mode="lines",
                    line=dict(color="#f59e0b", width=1.5, dash="dot"), name="5-start avg")
    if prop_line > 0:
        fig.add_hline(y=prop_line, line_color="#ffffff", line_width=1, line_dash="dash",
                      annotation_text=f"Line: {prop_line}", annotation_font_color="#ffffff",
                      annotation_position="top right")
    fig.update_layout(height=220, **_CHART)
    st.plotly_chart(fig, use_container_width=True)

    # ── Multi-stat trend ─────────────────────────────────────────────────────
    st.markdown("<div class='sh'>Performance trend — last 15 starts</div>", unsafe_allow_html=True)
    df_multi = df.sort_values("game_date").tail(15)
    fig2 = go.Figure()
    for stat, label, color in [
        ("k",  "Strikeouts",    "#6366f1"),
        ("ip", "Inn. Pitched",  "#22c55e"),
        ("er", "Earned Runs",   "#ef4444"),
        ("h",  "Hits",          "#f59e0b"),
    ]:
        if stat in df_multi.columns:
            s = pd.to_numeric(df_multi[stat], errors="coerce")
            fig2.add_scatter(x=df_multi["game_date"], y=s,
                             mode="lines+markers", name=label,
                             line=dict(color=color, width=2), marker=dict(size=4, color=color))
    fig2.update_layout(height=260, **_CHART)
    st.plotly_chart(fig2, use_container_width=True)

    # ── Manual line comparison ───────────────────────────────────────────────
    st.markdown("<div class='sh'>Check multiple lines</div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:12px;color:#44444f;margin-bottom:1rem'>Enter lines from DraftKings, FanDuel, etc. Leave at 0 to skip.</div>",
                unsafe_allow_html=True)

    props_to_check = [
        ("k",  "Strikeouts"), ("ip", "Innings Pitched"),
        ("er", "Earned Runs"), ("h",  "Hits Allowed"), ("bb", "Walks"),
    ]
    col_a, col_b = st.columns(2)
    input_lines = {}
    for i, (stat, label) in enumerate(props_to_check):
        with (col_a if i % 2 == 0 else col_b):
            input_lines[stat] = st.number_input(
                f"{label} line", min_value=0.0, max_value=30.0,
                value=0.0, step=0.5, key=f"mlb_line_{stat}"
            )

    rows = []
    for stat, label in props_to_check:
        line = input_lines[stat]
        if line == 0:
            continue
        s   = pd.to_numeric(df.head(prop_window)[stat], errors="coerce").dropna()
        ho2 = _hit_rate(s, line, "over")
        hu2 = _hit_rate(s, line, "under")
        l5  = pd.to_numeric(df.head(5)[stat], errors="coerce").mean()
        l10 = pd.to_numeric(df.head(10)[stat], errors="coerce").mean()
        if ho2 >= 0.65:   rec, rcls = "OVER",       "bg"
        elif hu2 >= 0.65: rec, rcls = "UNDER",      "br"
        elif ho2 > hu2:   rec, rcls = "LEAN OVER",  "bn"
        else:             rec, rcls = "LEAN UNDER", "bn"
        rows.append({"stat": stat, "label": label, "line": line,
                     "l5": l5, "l10": l10, "ho": ho2, "hu": hu2,
                     "rec": rec, "rcls": rcls})

    if rows:
        for r in rows:
            ow = int(r["ho"] * 100); uw = 100 - ow
            bc = "#22c55e" if r["ho"] >= 0.65 else ("#ef4444" if r["ho"] <= 0.35 else "#f59e0b")
            ac = "#22c55e" if r["l10"] > r["line"] else "#ef4444"
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
</div>""", unsafe_allow_html=True)
    elif any(v > 0 for v in input_lines.values()):
        pass
    else:
        st.markdown("""
<div style="background:#13131a;border:1px solid #1e1e28;border-radius:10px;padding:1.25rem 1.5rem;color:#44444f;font-size:13px">
  Enter lines above to see over/under analysis across all prop markets.
</div>
""", unsafe_allow_html=True)

    # ── Start log ────────────────────────────────────────────────────────────
    n_show = min(20, len(df))
    st.markdown(f"<div class='sh'>Start log — last {n_show} games</div>", unsafe_allow_html=True)
    log_rows = ""
    for _, row in df.head(20).iterrows():
        val  = float(pd.to_numeric(row.get(prop_stat, 0), errors="coerce") or 0)
        hit  = val >= prop_line
        vcls = "hit" if hit else "miss"
        d    = pd.to_datetime(row["game_date"]).strftime("%b %d")
        k    = int(pd.to_numeric(row.get("k", 0), errors="coerce") or 0)
        ip   = float(pd.to_numeric(row.get("ip", 0), errors="coerce") or 0)
        er   = int(pd.to_numeric(row.get("er", 0), errors="coerce") or 0)
        h    = int(pd.to_numeric(row.get("h", 0), errors="coerce") or 0)
        bb   = int(pd.to_numeric(row.get("bb", 0), errors="coerce") or 0)
        log_rows += f"""
<div class="gr">
  <span style="color:#44444f;width:56px;font-size:12px">{d}</span>
  <span style="color:#6b6b78;flex:1;font-size:12px">{row.get('team','')}</span>
  <span style="color:#9090a0;width:36px;font-size:12px;text-align:right">{ip:.1f}</span>
  <span style="color:#9090a0;width:28px;font-size:12px;text-align:right">{k}</span>
  <span style="color:#9090a0;width:28px;font-size:12px;text-align:right">{er}</span>
  <span style="color:#9090a0;width:28px;font-size:12px;text-align:right">{h}</span>
  <span style="color:#9090a0;width:28px;font-size:12px;text-align:right">{bb}</span>
  <span class="{vcls}" style="width:52px;text-align:right">{val:.0f} {"✓" if hit else "✗"}</span>
</div>"""

    st.markdown(f"""
<div class="card">
  <div style="display:flex;padding:0 0 8px;border-bottom:1px solid #1e1e28;
    font-size:11px;color:#44444f;letter-spacing:.04em;text-transform:uppercase">
    <span style="width:56px">Date</span>
    <span style="flex:1">Team</span>
    <span style="width:36px;text-align:right">IP</span>
    <span style="width:28px;text-align:right">K</span>
    <span style="width:28px;text-align:right">ER</span>
    <span style="width:28px;text-align:right">H</span>
    <span style="width:28px;text-align:right">BB</span>
    <span style="width:52px;text-align:right">{STAT_LABELS.get(prop_stat,'').split()[0]} vs {prop_line}</span>
  </div>
  {log_rows}
</div>
""", unsafe_allow_html=True)
