import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.graph_objects as go
from datetime import date
from pathlib import Path
from config import DB_PATH

st.set_page_config(page_title="NBA Edge — Parlay Builder", page_icon="🏀",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.stApp{background-color:#0d0d0f}
[data-testid="stSidebar"]{background-color:#111114;border-right:1px solid #222228}
[data-testid="stSidebarContent"]{padding-top:1.5rem}
#MainMenu,footer,header{visibility:hidden}
[data-testid="stToolbar"]{display:none}
.block-container{padding-top:1.5rem;padding-bottom:2rem;max-width:1200px}
html,body,[class*="css"]{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e8e8ec}
[data-testid="metric-container"]{background:#16161a;border:1px solid #222228;border-radius:10px;padding:1rem 1.25rem}
[data-testid="metric-container"] label{color:#6b6b78!important;font-size:11px!important;letter-spacing:.06em;text-transform:uppercase}
[data-testid="stMetricValue"]{color:#e8e8ec!important;font-size:22px!important;font-weight:600!important}
.sh{font-size:11px;font-weight:600;letter-spacing:.1em;color:#44444f;text-transform:uppercase;
    margin:1.5rem 0 .75rem;padding-bottom:8px;border-bottom:1px solid #1e1e24}
.card{background:#16161a;border:1px solid #222228;border-radius:12px;
      padding:1.25rem 1.5rem;margin-bottom:10px}
.leg-card{background:#16161a;border:1px solid #222228;border-radius:10px;
          padding:1rem 1.25rem;margin-bottom:8px;position:relative}
.leg-card.value{border-color:#1a3a1a;border-left:3px solid #22c55e}
.leg-card.no-value{border-left:3px solid #333340}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;letter-spacing:.04em}
.bg{background:#0d2a0d;color:#22c55e;border:1px solid #1a4a1a}
.br{background:#2a0d0d;color:#ef4444;border:1px solid #4a1a1a}
.bn{background:#1a1a20;color:#6b6b78;border:1px solid #2a2a32}
.by{background:#2a1f0d;color:#f59e0b;border:1px solid #4a380d}
.parlay-summary{background:#111118;border:1px solid #222228;border-radius:14px;
                padding:1.75rem 2rem;margin-bottom:1.5rem}
.big-prob{font-size:48px;font-weight:700;letter-spacing:-1px;line-height:1}
.stat-row{display:flex;justify-content:space-between;padding:8px 0;
          border-bottom:1px solid #1a1a20;font-size:13px}
.stat-row:last-child{border-bottom:none}
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load(query, params=None):
    if not Path(DB_PATH).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(query, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

def get_players():
    return load("SELECT DISTINCT player_name FROM player_stats ORDER BY player_name")

def get_player_games(player_name, n=20):
    df = load("""
        SELECT ps.*, g.matchup, g.wl, g.is_home, g.team_name, g.team_abbreviation
        FROM player_stats ps
        LEFT JOIN games g ON ps.game_id = g.game_id
            AND g.team_abbreviation = ps.team_abbrev
        WHERE ps.player_name = ?
        ORDER BY ps.game_date DESC
        LIMIT ?
    """, params=(player_name, n))
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
    return df

def hit_rate(series, line, direction="over"):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return 0.5
    return float((s > line).mean() if direction == "over" else (s < line).mean())

def american_to_implied(odds):
    try:
        o = float(odds)
        return 100/(o+100) if o > 0 else abs(o)/(abs(o)+100)
    except Exception:
        return 0.5

def implied_to_american(prob):
    prob = max(0.01, min(0.99, prob))
    if prob >= 0.5:
        return f"-{round(prob/(1-prob)*100)}"
    return f"+{round((1-prob)/prob*100)}"

def parlay_american_odds(probs):
    """Convert list of probabilities to parlay American odds."""
    if not probs:
        return 0
    decimal = 1.0
    for p in probs:
        p = max(0.01, min(0.99, p))
        # Fair decimal odds
        decimal *= (1 / p)
    # Convert to American
    if decimal >= 2:
        return f"+{round((decimal-1)*100)}"
    return f"-{round(100/(decimal-1))}"

def correlation_warning(legs):
    """Check if multiple legs involve same-team players — correlated risk."""
    teams = [l.get("team","") for l in legs if l.get("team","")]
    if not teams:
        return None
    from collections import Counter
    counts = Counter(teams)
    shared = [(t, n) for t, n in counts.items() if n > 1]
    return shared if shared else None

STAT_LABELS = {"pts":"Points","reb":"Rebounds","ast":"Assists",
               "fg3m":"3-Pointers","stl":"Steals","blk":"Blocks"}
WINDOW = 15  # default rolling window

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
<div style="padding:0 8px 1.5rem">
  <div style="font-size:20px;font-weight:700;color:#e8e8ec;letter-spacing:-.5px">NBA Edge</div>
  <div style="font-size:11px;color:#44444f;margin-top:2px">Parlay builder</div>
</div>
""", unsafe_allow_html=True)
    st.markdown("<div style='height:1px;background:#1e1e24;margin:0 0 1rem'></div>",
                unsafe_allow_html=True)

    players_df = get_players()
    if players_df.empty:
        st.warning("No player data. Run `python props.py` first.")
        st.stop()

    player_list = players_df["player_name"].tolist()

    st.markdown("<div style='font-size:11px;color:#44444f;letter-spacing:.06em;text-transform:uppercase;margin-bottom:8px'>Parlay settings</div>",
                unsafe_allow_html=True)

    n_legs = st.selectbox("Number of legs", [2,3,4,5,6], index=1)
    window = st.selectbox("Stats window (games)", [5,10,15,20], index=1)
    min_hit_rate = st.slider("Min hit rate to show", 0.40, 0.80, 0.55, step=0.05)

    st.markdown("<div style='height:1px;background:#1e1e24;margin:1rem 0'></div>",
                unsafe_allow_html=True)
    st.markdown("<div style='font-size:11px;color:#44444f;letter-spacing:.06em;text-transform:uppercase;margin-bottom:8px'>Book parlay odds</div>",
                unsafe_allow_html=True)
    book_parlay_odds = st.number_input("Book parlay line (American)",
                                        value=0, step=50,
                                        help="Enter the book's offered parlay odds to calculate edge. Leave 0 to skip.")

# ── Main ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom:1.5rem">
  <div style="font-size:22px;font-weight:700;color:#e8e8ec;letter-spacing:-.3px">Parlay Builder</div>
  <div style="font-size:13px;color:#6b6b78;margin-top:4px">
    Build a multi-leg prop parlay and see the combined model probability vs the book.
  </div>
</div>
""", unsafe_allow_html=True)

# ── Leg inputs ────────────────────────────────────────────────────────────────
st.markdown("<div class='sh'>Configure legs</div>", unsafe_allow_html=True)

legs = []
cols_per_row = 2
leg_rows = [list(range(n_legs))[i:i+cols_per_row]
            for i in range(0, n_legs, cols_per_row)]

for row in leg_rows:
    cols = st.columns(cols_per_row)
    for col_idx, leg_idx in enumerate(row):
        with cols[col_idx]:
            st.markdown(f"<div style='font-size:12px;color:#4f8ef7;font-weight:600;margin-bottom:6px'>LEG {leg_idx+1}</div>",
                        unsafe_allow_html=True)
            player  = st.selectbox(f"Player", player_list, key=f"p{leg_idx}",
                                   label_visibility="collapsed")
            stat    = st.selectbox(f"Stat", list(STAT_LABELS.keys()),
                                   format_func=lambda x: STAT_LABELS[x],
                                   key=f"s{leg_idx}", label_visibility="collapsed")
            line    = st.number_input(f"Line", min_value=0.0, max_value=80.0,
                                      value=15.0, step=0.5, key=f"l{leg_idx}",
                                      label_visibility="collapsed")
            direction = st.radio(f"Direction", ["Over","Under"],
                                 key=f"d{leg_idx}", horizontal=True,
                                 label_visibility="collapsed")
            legs.append({"player":player, "stat":stat, "line":line,
                         "direction":direction.lower()})

# ── Analyze legs ──────────────────────────────────────────────────────────────
st.markdown("<div class='sh'>Leg analysis</div>", unsafe_allow_html=True)

analyzed = []
for i, leg in enumerate(legs):
    df = get_player_games(leg["player"], n=max(window, 20))
    if df.empty:
        continue

    team = str(df.iloc[0].get("team_name","")) if not df.empty else ""
    series = df.head(window)[leg["stat"]].astype(float)
    avg    = series.mean()
    std    = series.std() if len(series) > 1 else 0
    hr     = hit_rate(series, leg["line"], leg["direction"])
    l5_hr  = hit_rate(df.head(5)[leg["stat"]].astype(float), leg["line"], leg["direction"])
    hits   = int(hr * len(series))

    direction_icon = "⬆️" if leg["direction"] == "over" else "⬇️"
    stat_label     = STAT_LABELS.get(leg["stat"],"")

    if hr >= 0.65:
        cls, rec = "value", "STRONG"
        badge_cls = "bg"
    elif hr >= min_hit_rate:
        cls, rec = "value", "LEAN"
        badge_cls = "by"
    else:
        cls, rec = "no-value", "WEAK"
        badge_cls = "br"

    # Recent form — last 5 as mini sparkline
    last5 = df.head(5)[leg["stat"]].astype(float).tolist()
    sparks = " ".join([
        f'<span style="color:{"#22c55e" if (v > leg["line"] if leg["direction"]=="over" else v < leg["line"]) else "#ef4444"};font-weight:600">{v:.0f}</span>'
        for v in reversed(last5)
    ])

    st.markdown(f"""
<div class="leg-card {cls}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
    <div>
      <div style="font-size:15px;font-weight:600;color:#e8e8ec">{leg['player']}</div>
      <div style="font-size:12px;color:#6b6b78;margin-top:2px">
        {direction_icon} {leg['direction'].upper()} {leg['line']} {stat_label}
        &nbsp;·&nbsp; {team}
      </div>
    </div>
    <div style="text-align:right">
      <span class="badge {badge_cls}">{rec} &nbsp;{hr:.0%}</span>
      <div style="font-size:11px;color:#44444f;margin-top:4px">{hits}/{len(series)} last {window}</div>
    </div>
  </div>
  <div style="display:flex;gap:20px;font-size:13px;flex-wrap:wrap">
    <div><span style="color:#44444f">Avg L{window}</span>
         <span style="color:#e8e8ec;font-weight:500;margin-left:8px">{avg:.1f}</span></div>
    <div><span style="color:#44444f">Std dev</span>
         <span style="color:#e8e8ec;margin-left:8px">{std:.1f}</span></div>
    <div><span style="color:#44444f">L5 hit rate</span>
         <span style="color:{'#22c55e' if l5_hr >= 0.6 else '#ef4444'};font-weight:600;margin-left:8px">{l5_hr:.0%}</span></div>
    <div><span style="color:#44444f">Last 5</span>
         <span style="margin-left:8px">{sparks}</span></div>
  </div>
</div>
""", unsafe_allow_html=True)

    analyzed.append({**leg, "hit_rate": hr, "team": team, "avg": avg,
                     "rec": rec, "badge_cls": badge_cls})

# ── Parlay summary ────────────────────────────────────────────────────────────
if len(analyzed) >= 2:
    st.markdown("<div class='sh'>Parlay summary</div>", unsafe_allow_html=True)

    # Combined probability (assuming independence — with correlation warning)
    combined_prob = 1.0
    for leg in analyzed:
        combined_prob *= leg["hit_rate"]

    fair_odds = parlay_american_odds([l["hit_rate"] for l in analyzed])
    all_strong = all(l["rec"] in ["STRONG","LEAN"] for l in analyzed)
    prob_color = "#22c55e" if combined_prob >= 0.45 else ("#f59e0b" if combined_prob >= 0.30 else "#ef4444")

    # Edge vs book
    edge_html = ""
    if book_parlay_odds != 0:
        book_implied = american_to_implied(book_parlay_odds)
        edge = combined_prob - book_implied
        edge_color = "#22c55e" if edge > 0.03 else ("#f59e0b" if edge > 0 else "#ef4444")
        edge_html = f"""
<div style="margin-top:1rem;padding-top:1rem;border-top:1px solid #222228">
  <div style="display:flex;gap:32px;flex-wrap:wrap">
    <div>
      <div style="font-size:11px;color:#44444f;text-transform:uppercase;letter-spacing:.06em">Book implied</div>
      <div style="font-size:20px;font-weight:600;color:#e8e8ec;margin-top:2px">{book_implied:.1%}</div>
    </div>
    <div>
      <div style="font-size:11px;color:#44444f;text-transform:uppercase;letter-spacing:.06em">Your edge</div>
      <div style="font-size:20px;font-weight:600;color:{edge_color};margin-top:2px">{edge:+.1%}</div>
    </div>
    <div>
      <div style="font-size:11px;color:#44444f;text-transform:uppercase;letter-spacing:.06em">Verdict</div>
      <div style="font-size:20px;font-weight:600;color:{edge_color};margin-top:2px">
        {"✓ VALUE" if edge > 0.03 else ("~ MARGINAL" if edge > 0 else "✗ SKIP")}
      </div>
    </div>
  </div>
</div>"""

    # Correlation warning
    corr = correlation_warning(analyzed)
    corr_html = ""
    if corr:
        teams_str = ", ".join([f"{t} ({n} legs)" for t,n in corr])
        corr_html = f"""
<div style="background:#1f1a0d;border:1px solid #4a380d;border-radius:8px;
            padding:10px 14px;margin-top:12px;font-size:12px;color:#f59e0b">
  ⚠️ <strong>Correlation risk:</strong> Multiple legs share the same team ({teams_str}).
  These outcomes are correlated — wins/losses tend to happen together,
  which can amplify variance beyond what the independent probability suggests.
</div>"""

    # Leg breakdown rows
    leg_rows_html = "".join([
        f'<div class="stat-row">'
        f'<span style="color:#9090a0">{l["player"]} — '
        f'{"⬆️" if l["direction"]=="over" else "⬇️"} '
        f'{l["direction"].upper()} {l["line"]} {STAT_LABELS.get(l["stat"],"")}</span>'
        f'<span class="badge {l["badge_cls"]}" style="font-size:11px">{l["hit_rate"]:.0%}</span>'
        f'</div>'
        for l in analyzed
    ])

    st.markdown(f"""
<div class="parlay-summary">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px">
    <div>
      <div style="font-size:11px;color:#44444f;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">
        {len(analyzed)}-leg parlay · model probability
      </div>
      <div class="big-prob" style="color:{prob_color}">{combined_prob:.1%}</div>
      <div style="font-size:13px;color:#6b6b78;margin-top:6px">
        Fair odds: <strong style="color:#e8e8ec">{fair_odds}</strong>
      </div>
    </div>
    <div style="text-align:right">
      <div style="font-size:11px;color:#44444f;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Overall rating</div>
      <span class="badge {'bg' if all_strong and combined_prob >= 0.40 else ('by' if combined_prob >= 0.30 else 'br')}" style="font-size:14px;padding:6px 14px">
        {'✓ PLAY IT' if all_strong and combined_prob >= 0.40 else ('~ MARGINAL' if combined_prob >= 0.30 else '✗ SKIP')}
      </span>
    </div>
  </div>

  <div style="margin-top:1.25rem;padding-top:1.25rem;border-top:1px solid #1e1e24">
    {leg_rows_html}
  </div>

  {edge_html}
  {corr_html}
</div>
""", unsafe_allow_html=True)

    # Visual probability breakdown chart
    st.markdown("<div class='sh'>Probability breakdown</div>", unsafe_allow_html=True)

    labels  = [f"{l['player'].split()[-1]}\n{STAT_LABELS.get(l['stat'],'')} {l['direction'].upper()} {l['line']}"
               for l in analyzed]
    probs   = [l["hit_rate"] for l in analyzed]
    colors  = ["#22c55e" if p >= 0.65 else ("#f59e0b" if p >= 0.50 else "#ef4444")
               for p in probs]

    fig = go.Figure()

    # Individual leg bars
    fig.add_bar(x=labels, y=[p*100 for p in probs],
                marker_color=colors, marker_line_width=0,
                name="Hit rate %", text=[f"{p:.0%}" for p in probs],
                textposition="outside", textfont=dict(color="#e8e8ec", size=12))

    # Combined probability line
    fig.add_hline(y=combined_prob*100, line_color="#4f8ef7", line_width=1.5,
                  line_dash="dash",
                  annotation_text=f"Combined: {combined_prob:.1%}",
                  annotation_font_color="#4f8ef7",
                  annotation_position="top right")

    # Break-even line for -110
    fig.add_hline(y=52.4, line_color="#333340", line_width=1,
                  annotation_text="Break-even 52.4%",
                  annotation_font_color="#44444f",
                  annotation_position="bottom right")

    fig.update_layout(
        height=280, margin=dict(l=0,r=0,t=30,b=0),
        paper_bgcolor="#16161a", plot_bgcolor="#16161a",
        xaxis=dict(showgrid=False, color="#44444f"),
        yaxis=dict(gridcolor="#1e1e24", color="#44444f", range=[0,105], title="%"),
        showlegend=False, font=dict(color="#9090a0"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Comparison table
    st.markdown("<div class='sh'>Leg comparison table</div>", unsafe_allow_html=True)
    table_data = []
    for l in analyzed:
        df_tmp = get_player_games(l["player"], n=20)
        if df_tmp.empty:
            continue
        s = df_tmp[l["stat"]].astype(float)
        table_data.append({
            "Player":       l["player"],
            "Stat":         STAT_LABELS.get(l["stat"],""),
            "Direction":    l["direction"].upper(),
            "Line":         l["line"],
            "Avg L5":       round(s.head(5).mean(), 1),
            "Avg L10":      round(s.head(10).mean(), 1),
            "Avg L20":      round(s.head(20).mean(), 1),
            f"Hit rate L{window}": f"{l['hit_rate']:.0%}",
            "Rating":       l["rec"],
        })

    if table_data:
        st.dataframe(pd.DataFrame(table_data), use_container_width=True,
                     hide_index=True)

    # Important caveat
    st.markdown("""
<div style="background:#111118;border:1px solid #1e1e24;border-radius:8px;
            padding:12px 16px;margin-top:8px;font-size:12px;color:#44444f;line-height:1.6">
  <strong style="color:#6b6b78">Note:</strong>
  Combined probability assumes statistical independence between legs.
  Same-game legs on the same team are correlated and real probability may differ.
  Always compare fair odds to the book's offered odds before placing.
</div>
""", unsafe_allow_html=True)

else:
    st.markdown("""
<div style="background:#16161a;border:1px solid #222228;border-radius:12px;
            padding:2rem;text-align:center;color:#44444f;font-size:13px">
  Configure at least 2 legs above to see your parlay analysis
</div>
""", unsafe_allow_html=True)
