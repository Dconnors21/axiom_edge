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
from config import DB_PATH, MIN_EDGE
from datetime import date

_CSS = """
<style>
.block-container{padding-top:1.5rem;padding-bottom:2rem;max-width:1200px}
[data-testid="metric-container"]{background:#16161a;border:1px solid #222228;border-radius:10px;padding:1rem 1.25rem}
[data-testid="metric-container"] label{color:#6b6b78!important;font-size:11px!important;letter-spacing:.06em;text-transform:uppercase}
[data-testid="stMetricValue"]{color:#e8e8ec!important;font-size:22px!important;font-weight:600!important}
.sh{font-size:11px;font-weight:600;letter-spacing:.1em;color:#44444f;text-transform:uppercase;margin:1.5rem 0 .75rem;padding-bottom:8px;border-bottom:1px solid #1e1e24}
.leg-card{background:#16161a;border:1px solid #222228;border-radius:10px;padding:1rem 1.25rem;margin-bottom:8px}
.leg-card.value{border-color:#1a3a1a;border-left:3px solid #22c55e}
.leg-card.no-value{border-left:3px solid #333340}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;letter-spacing:.04em}
.bg{background:#0d2a0d;color:#22c55e;border:1px solid #1a4a1a}
.br{background:#2a0d0d;color:#ef4444;border:1px solid #4a1a1a}
.bn{background:#1a1a20;color:#6b6b78;border:1px solid #2a2a32}
.by{background:#2a1f0d;color:#f59e0b;border:1px solid #4a380d}
.parlay-summary{background:#111118;border:1px solid #222228;border-radius:14px;padding:1.75rem 2rem;margin-bottom:1.5rem}
.big-prob{font-size:48px;font-weight:700;letter-spacing:-1px;line-height:1}
.stat-row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #1a1a20;font-size:13px}
.stat-row:last-child{border-bottom:none}
</style>
"""

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
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        return 0.5
    return float((s > line).mean() if direction == "over" else (s < line).mean())

def _american_to_implied(odds):
    try:
        o = float(odds)
        return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
    except Exception:
        return 0.5

def _fmt(price):
    try:
        p = int(price)
        return f"+{p}" if p > 0 else str(p)
    except Exception:
        return "N/A"

def _parlay_american_odds(probs):
    if not probs:
        return "+0"
    decimal = 1.0
    for p in probs:
        p = max(0.01, min(0.99, p))
        decimal *= (1 / p)
    if decimal >= 2:
        return f"+{round((decimal-1)*100)}"
    return f"-{round(100/(decimal-1))}"

def _correlation_warning(legs):
    from collections import Counter
    teams = [l.get("team", "") for l in legs if l.get("team", "")]
    counts = Counter(teams)
    shared = [(t, n) for t, n in counts.items() if n > 1]
    return shared if shared else None

STAT_LABELS = {"pts": "Points", "reb": "Rebounds", "ast": "Assists",
               "fg3m": "3-Pointers", "stl": "Steals", "blk": "Blocks"}

LEG_TYPES = ["🎲 Prop", "💰 Moneyline", "📐 Spread"]


def _load_todays_games():
    today = date.today().isoformat()
    preds = _load(
        "SELECT * FROM predictions WHERE predict_date=? ORDER BY commence_time",
        params=(today,)
    )
    return preds


def _load_todays_spreads():
    today = date.today().isoformat()
    return _load(
        "SELECT * FROM spread_predictions WHERE predict_date=? ORDER BY commence_time",
        params=(today,)
    )


def _build_game_label(row):
    away = row["away_team"].split()[-1]
    home = row["home_team"].split()[-1]
    return f"{away} @ {home}"


def _render_ml_leg(leg_idx, games_df):
    if games_df.empty:
        st.caption("No moneyline predictions for today.")
        return None

    game_labels = [_build_game_label(r) for _, r in games_df.iterrows()]
    game_idx = st.selectbox("Game", range(len(game_labels)),
                             format_func=lambda i: game_labels[i],
                             key=f"ml_game_{leg_idx}", label_visibility="collapsed")
    game = games_df.iloc[game_idx]
    side = st.radio("Side", ["Home", "Away"], key=f"ml_side_{leg_idx}",
                    horizontal=True, label_visibility="collapsed")
    side_key = side.lower()
    bet_team  = game["home_team"] if side_key == "home" else game["away_team"]
    model_prob = float(game.get(f"model_{side_key}_prob", 0.5))
    fair_prob  = float(game.get(f"{side_key}_fair_prob", 0.5))
    edge       = float(game.get(f"{side_key}_edge", 0))
    price      = game.get(f"{side_key}_price")
    is_value   = int(game.get(f"{side_key}_value", 0)) == 1

    label     = f"{bet_team} ML"
    if model_prob >= 0.65:   cls, rec, badge_cls = "value", "STRONG", "bg"
    elif model_prob >= 0.52: cls, rec, badge_cls = "value", "LEAN",   "by"
    else:                    cls, rec, badge_cls = "no-value", "WEAK", "br"

    st.markdown(f"""
<div class="leg-card {cls}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
    <div>
      <div style="font-size:15px;font-weight:600;color:#e8e8ec">{bet_team} ML</div>
      <div style="font-size:12px;color:#6b6b78;margin-top:2px">
        {game['away_team'].split()[-1]} @ {game['home_team'].split()[-1]} &nbsp;·&nbsp; Moneyline &nbsp;·&nbsp; {_fmt(price)}
      </div>
    </div>
    <span class="badge {badge_cls}">{rec} &nbsp;{model_prob:.0%}</span>
  </div>
  <div style="display:flex;gap:20px;font-size:13px;flex-wrap:wrap">
    <div><span style="color:#44444f">Model prob</span><span style="color:#e8e8ec;font-weight:500;margin-left:8px">{model_prob:.1%}</span></div>
    <div><span style="color:#44444f">Book implied</span><span style="color:#e8e8ec;margin-left:8px">{fair_prob:.1%}</span></div>
    <div><span style="color:#44444f">Edge</span><span style="color:{'#22c55e' if edge>0.03 else '#ef4444'};font-weight:600;margin-left:8px">{edge:+.1%}</span></div>
    {'<span class="badge bg" style="margin-left:4px">VALUE BET</span>' if is_value else ''}
  </div>
</div>""", unsafe_allow_html=True)

    return {"type": "ml", "label": label, "hit_rate": model_prob,
            "team": bet_team, "rec": rec, "badge_cls": badge_cls,
            "edge": edge, "price": price}


def _render_spread_leg(leg_idx, spreads_df):
    if spreads_df.empty:
        st.caption("No spread predictions for today.")
        return None

    game_labels = [_build_game_label(r) for _, r in spreads_df.iterrows()]
    game_idx = st.selectbox("Game", range(len(game_labels)),
                             format_func=lambda i: game_labels[i],
                             key=f"sp_game_{leg_idx}", label_visibility="collapsed")
    game = spreads_df.iloc[game_idx]
    side = st.radio("Side", ["Home", "Away"], key=f"sp_side_{leg_idx}",
                    horizontal=True, label_visibility="collapsed")
    side_key = side.lower()
    bet_team   = game["home_team"] if side_key == "home" else game["away_team"]
    spread_val = game.get(f"{side_key}_point")
    cover_prob = float(game.get(f"{side_key}_cover_prob", 0.5))
    edge       = float(game.get(f"{side_key}_ats_edge", 0))
    price      = game.get(f"{side_key}_price")
    is_value   = int(game.get(f"{side_key}_ats_value", 0)) == 1

    spread_str = f"{spread_val:+.1f}" if spread_val is not None else ""
    label      = f"{bet_team} {spread_str}"

    if cover_prob >= 0.65:   cls, rec, badge_cls = "value", "STRONG", "bg"
    elif cover_prob >= 0.52: cls, rec, badge_cls = "value", "LEAN",   "by"
    else:                    cls, rec, badge_cls = "no-value", "WEAK", "br"

    st.markdown(f"""
<div class="leg-card {cls}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
    <div>
      <div style="font-size:15px;font-weight:600;color:#e8e8ec">{bet_team} {spread_str}</div>
      <div style="font-size:12px;color:#6b6b78;margin-top:2px">
        {game['away_team'].split()[-1]} @ {game['home_team'].split()[-1]} &nbsp;·&nbsp; Spread &nbsp;·&nbsp; {_fmt(price)}
      </div>
    </div>
    <span class="badge {badge_cls}">{rec} &nbsp;{cover_prob:.0%}</span>
  </div>
  <div style="display:flex;gap:20px;font-size:13px;flex-wrap:wrap">
    <div><span style="color:#44444f">P(cover)</span><span style="color:#e8e8ec;font-weight:500;margin-left:8px">{cover_prob:.1%}</span></div>
    <div><span style="color:#44444f">Pred margin</span><span style="color:#e8e8ec;margin-left:8px">{float(game.get('pred_home_margin',0)):+.1f}</span></div>
    <div><span style="color:#44444f">Edge</span><span style="color:{'#22c55e' if edge>0.03 else '#ef4444'};font-weight:600;margin-left:8px">{edge:+.1%}</span></div>
    {'<span class="badge bg" style="margin-left:4px">VALUE BET</span>' if is_value else ''}
  </div>
</div>""", unsafe_allow_html=True)

    return {"type": "spread", "label": label, "hit_rate": cover_prob,
            "team": bet_team, "rec": rec, "badge_cls": badge_cls,
            "edge": edge, "price": price}


def _render_prop_leg(leg_idx, player_list, window):
    # Search filter — narrows the dropdown before rendering it
    search = st.text_input("Search player", key=f"search_{leg_idx}",
                            placeholder="Type name to filter...",
                            label_visibility="collapsed")
    filtered = [p for p in player_list if search.lower() in p.lower()] if search else player_list
    if not filtered:
        st.caption("No players match that search.")
        return None

    player    = st.selectbox("Player", filtered, key=f"p{leg_idx}", label_visibility="collapsed")
    stat      = st.selectbox("Stat", list(STAT_LABELS.keys()),
                              format_func=lambda x: STAT_LABELS[x],
                              key=f"s{leg_idx}", label_visibility="collapsed")
    line      = st.number_input("Line", min_value=0.0, max_value=80.0, value=15.0,
                                step=0.5, key=f"l{leg_idx}", label_visibility="collapsed")
    direction = st.radio("Direction", ["Over", "Under"], key=f"d{leg_idx}",
                         horizontal=True, label_visibility="collapsed")

    df = _load("""
        SELECT player_name, game_id, game_date, team_abbreviation, is_home,
               pts, reb, ast, fg3m, stl, blk, min_played
        FROM player_game_logs
        WHERE player_name = ?
        ORDER BY game_date DESC LIMIT ?
    """, params=(player, max(window, 20)))

    if df.empty:
        st.caption(f"No game log data for {player}.")
        return None

    team   = str(df.iloc[0].get("team_abbreviation", ""))
    series = df.head(window)[stat].astype(float)
    avg    = series.mean()
    std    = series.std() if len(series) > 1 else 0
    hr     = _hit_rate(series, line, direction.lower())
    l5_hr  = _hit_rate(df.head(5)[stat].astype(float), line, direction.lower())
    hits   = int(hr * len(series))
    direction_icon = "⬆️" if direction.lower() == "over" else "⬇️"
    stat_label     = STAT_LABELS.get(stat, "")

    if hr >= 0.65:            cls, rec, badge_cls = "value", "STRONG", "bg"
    elif hr >= 0.55:          cls, rec, badge_cls = "value", "LEAN",   "by"
    else:                     cls, rec, badge_cls = "no-value", "WEAK", "br"

    last5  = df.head(5)[stat].astype(float).tolist()
    sparks = " ".join([
        f'<span style="color:{"#22c55e" if (v > line if direction.lower()=="over" else v < line) else "#ef4444"};font-weight:600">{v:.0f}</span>'
        for v in reversed(last5)
    ])
    label = f"{player} {direction.upper()} {line} {stat_label}"

    st.markdown(f"""
<div class="leg-card {cls}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
    <div>
      <div style="font-size:15px;font-weight:600;color:#e8e8ec">{player}</div>
      <div style="font-size:12px;color:#6b6b78;margin-top:2px">
        {direction_icon} {direction.upper()} {line} {stat_label} &nbsp;·&nbsp; {team}
      </div>
    </div>
    <div style="text-align:right">
      <span class="badge {badge_cls}">{rec} &nbsp;{hr:.0%}</span>
      <div style="font-size:11px;color:#44444f;margin-top:4px">{hits}/{len(series)} last {window}</div>
    </div>
  </div>
  <div style="display:flex;gap:20px;font-size:13px;flex-wrap:wrap">
    <div><span style="color:#44444f">Avg L{window}</span><span style="color:#e8e8ec;font-weight:500;margin-left:8px">{avg:.1f}</span></div>
    <div><span style="color:#44444f">Std dev</span><span style="color:#e8e8ec;margin-left:8px">{std:.1f}</span></div>
    <div><span style="color:#44444f">L5 hit rate</span><span style="color:{'#22c55e' if l5_hr>=0.6 else '#ef4444'};font-weight:600;margin-left:8px">{l5_hr:.0%}</span></div>
    <div><span style="color:#44444f">Last 5</span><span style="margin-left:8px">{sparks}</span></div>
  </div>
</div>""", unsafe_allow_html=True)

    return {"type": "prop", "label": label, "hit_rate": hr,
            "team": team, "rec": rec, "badge_cls": badge_cls,
            "player": player, "stat": stat, "line": line, "direction": direction.lower(),
            "avg": avg}


def render():
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown("""
<div style="margin-bottom:1rem">
  <div style="font-size:22px;font-weight:700;color:#e8e8ec;letter-spacing:-.3px">Parlay Builder</div>
  <div style="font-size:13px;color:#6b6b78;margin-top:4px">Build a multi-leg parlay with props, moneyline, or spread legs.</div>
</div>
""", unsafe_allow_html=True)

    players_df = _load("SELECT DISTINCT player_name FROM player_game_logs ORDER BY player_name")
    if players_df.empty:
        st.warning("No player data. Run `python collect_props.py` first.")
        return

    player_list = players_df["player_name"].tolist()
    games_df    = _load_todays_games()
    spreads_df  = _load_todays_spreads()

    s1, s2, s3, s4 = st.columns(4)
    with s1: n_legs = st.selectbox("Number of legs", [2, 3, 4, 5, 6], index=1)
    with s2: window = st.selectbox("Stats window (games)", [5, 10, 15, 20], index=1)
    with s3: min_hit_rate = st.slider("Min hit rate", 0.40, 0.80, 0.55, step=0.05)
    with s4: book_parlay_odds = st.number_input("Book parlay line (American)", value=0, step=50,
                                                 help="Enter book's parlay odds to calc edge. 0 to skip.")

    st.markdown("<div class='sh'>Configure legs</div>", unsafe_allow_html=True)

    legs = []
    leg_rows = [list(range(n_legs))[i:i+2] for i in range(0, n_legs, 2)]
    for row in leg_rows:
        cols = st.columns(2)
        for col_idx, leg_idx in enumerate(row):
            with cols[col_idx]:
                st.markdown(
                    f"<div style='font-size:12px;color:#4f8ef7;font-weight:600;margin-bottom:6px'>LEG {leg_idx+1}</div>",
                    unsafe_allow_html=True
                )
                leg_type = st.radio(
                    "Type", LEG_TYPES, key=f"type_{leg_idx}",
                    horizontal=True, label_visibility="collapsed"
                )
                legs.append((leg_idx, leg_type))

    st.markdown("<div class='sh'>Leg analysis</div>", unsafe_allow_html=True)

    analyzed = []
    for leg_idx, leg_type in legs:
        leg_cols = st.columns(2)
        with leg_cols[leg_idx % 2]:
            st.markdown(
                f"<div style='font-size:11px;color:#4f8ef7;font-weight:600;margin-bottom:4px'>LEG {leg_idx+1} · {leg_type}</div>",
                unsafe_allow_html=True
            )
            if "Moneyline" in leg_type:
                result = _render_ml_leg(leg_idx, games_df)
            elif "Spread" in leg_type:
                result = _render_spread_leg(leg_idx, spreads_df)
            else:
                result = _render_prop_leg(leg_idx, player_list, window)

            if result:
                analyzed.append(result)

    if len(analyzed) >= 2:
        st.markdown("<div class='sh'>Parlay summary</div>", unsafe_allow_html=True)

        combined_prob = 1.0
        for leg in analyzed:
            combined_prob *= leg["hit_rate"]

        fair_odds  = _parlay_american_odds([l["hit_rate"] for l in analyzed])
        all_strong = all(l["rec"] in ["STRONG", "LEAN"] for l in analyzed)
        prob_color = "#22c55e" if combined_prob >= 0.45 else ("#f59e0b" if combined_prob >= 0.30 else "#ef4444")

        edge_html = ""
        if book_parlay_odds != 0:
            book_implied = _american_to_implied(book_parlay_odds)
            edge = combined_prob - book_implied
            edge_color = "#22c55e" if edge > 0.03 else ("#f59e0b" if edge > 0 else "#ef4444")
            edge_html = f"""
<div style="margin-top:1rem;padding-top:1rem;border-top:1px solid #222228">
  <div style="display:flex;gap:32px;flex-wrap:wrap">
    <div><div style="font-size:11px;color:#44444f;text-transform:uppercase;letter-spacing:.06em">Book implied</div>
         <div style="font-size:20px;font-weight:600;color:#e8e8ec;margin-top:2px">{book_implied:.1%}</div></div>
    <div><div style="font-size:11px;color:#44444f;text-transform:uppercase;letter-spacing:.06em">Your edge</div>
         <div style="font-size:20px;font-weight:600;color:{edge_color};margin-top:2px">{edge:+.1%}</div></div>
    <div><div style="font-size:11px;color:#44444f;text-transform:uppercase;letter-spacing:.06em">Verdict</div>
         <div style="font-size:20px;font-weight:600;color:{edge_color};margin-top:2px">
           {"✓ VALUE" if edge>0.03 else ("~ MARGINAL" if edge>0 else "✗ SKIP")}
         </div></div>
  </div>
</div>"""

        corr = _correlation_warning(analyzed)
        corr_html = ""
        if corr:
            teams_str = ", ".join([f"{t} ({n} legs)" for t, n in corr])
            corr_html = f"""
<div style="background:#1f1a0d;border:1px solid #4a380d;border-radius:8px;padding:10px 14px;margin-top:12px;font-size:12px;color:#f59e0b">
  ⚠️ <strong>Correlation risk:</strong> Multiple legs share the same team ({teams_str}).
</div>"""

        type_icons = {"ml": "💰", "spread": "📐", "prop": "🎲"}
        leg_rows_html = "".join([
            f'<div class="stat-row">'
            f'<span style="color:#9090a0">{type_icons.get(l["type"],"🎲")} {l["label"]}</span>'
            f'<span class="badge {l["badge_cls"]}">{l["hit_rate"]:.0%}</span>'
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
      <span class="badge {'bg' if all_strong and combined_prob>=0.40 else ('by' if combined_prob>=0.30 else 'br')}"
            style="font-size:14px;padding:6px 14px">
        {'✓ PLAY IT' if all_strong and combined_prob>=0.40 else ('~ MARGINAL' if combined_prob>=0.30 else '✗ SKIP')}
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

        st.markdown("<div class='sh'>Probability breakdown</div>", unsafe_allow_html=True)
        labels = [l["label"] for l in analyzed]
        probs  = [l["hit_rate"] for l in analyzed]
        colors = ["#22c55e" if p >= 0.65 else ("#f59e0b" if p >= 0.50 else "#ef4444") for p in probs]
        fig = go.Figure()
        fig.add_bar(x=labels, y=[p * 100 for p in probs],
                    marker_color=colors, marker_line_width=0,
                    text=[f"{p:.0%}" for p in probs], textposition="outside",
                    textfont=dict(color="#e8e8ec", size=12))
        fig.add_hline(y=combined_prob * 100, line_color="#4f8ef7", line_width=1.5, line_dash="dash",
                      annotation_text=f"Combined: {combined_prob:.1%}",
                      annotation_font_color="#4f8ef7", annotation_position="top right")
        fig.add_hline(y=52.4, line_color="#333340", line_width=1,
                      annotation_text="Break-even 52.4%",
                      annotation_font_color="#44444f", annotation_position="bottom right")
        fig.update_layout(height=280, margin=dict(l=0, r=0, t=30, b=0),
                          paper_bgcolor="#16161a", plot_bgcolor="#16161a",
                          xaxis=dict(showgrid=False, color="#44444f"),
                          yaxis=dict(gridcolor="#1e1e24", color="#44444f", range=[0, 105], title="%"),
                          showlegend=False, font=dict(color="#9090a0"))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("""
<div style="background:#111118;border:1px solid #1e1e24;border-radius:8px;padding:12px 16px;margin-top:8px;font-size:12px;color:#44444f;line-height:1.6">
  <strong style="color:#6b6b78">Note:</strong>
  Prop hit rates use rolling historical data. ML and spread probabilities come from today's model predictions.
  Same-game legs on the same team are correlated — combined probability will overstate true hit rate.
</div>
""", unsafe_allow_html=True)
    else:
        st.markdown("""
<div style="background:#16161a;border:1px solid #222228;border-radius:12px;padding:2rem;text-align:center;color:#44444f;font-size:13px">
  Configure at least 2 legs above to see your parlay analysis
</div>
""", unsafe_allow_html=True)
