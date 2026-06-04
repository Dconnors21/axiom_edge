import streamlit as st
from datetime import date
import sqlite3
import pandas as pd
from pathlib import Path
from seed_demo import seed_if_empty

seed_if_empty()

st.set_page_config(
    page_title="AXIOM Edge",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Global design system ───────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ── */
.stApp { background-color: #0e1525 }
[data-testid="stSidebar"] { background-color: #0b0d14; border-right: 1px solid #1a2030 }
[data-testid="stSidebarContent"] { padding-top: 0 }
#MainMenu, footer { visibility: hidden }
[data-testid="stToolbar"] { display: none }
header { background: transparent !important }
header svg, header a, header button:not([data-testid="baseButton-headerNoPadding"]) { display: none !important }
[data-testid="collapsedControl"] { display: flex !important; visibility: visible !important; opacity: 1 !important; z-index: 999999 !important }
[data-testid="collapsedControl"] button { display: flex !important; visibility: visible !important }
.block-container { padding-top: 0; padding-bottom: 3rem; max-width: 1600px; padding-left: 2rem; padding-right: 2rem }
html, body, [class*="css"] { font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif; color: #f0f2f5 }

/* ── Metrics ── */
[data-testid="metric-container"] { background: #131d2e; border: 1px solid #1e2d42; border-radius: 10px; padding: 1rem 1.25rem }
[data-testid="metric-container"] label { color: #8090a8 !important; font-size: 11px !important; letter-spacing: .06em; text-transform: uppercase }
[data-testid="stMetricValue"] { color: #f0f2f5 !important; font-size: 22px !important; font-weight: 700 !important }

/* ── Sidebar nav buttons ── */
[data-testid="stSidebar"] button {
    background: transparent !important; border: none !important; box-shadow: none !important;
    color: #8090a8 !important; font-size: 13px !important; font-weight: 400 !important;
    padding: 6px 10px !important; text-align: left !important; justify-content: flex-start !important;
    border-radius: 6px !important; transition: all .12s !important; margin-bottom: 1px !important;
    width: 100% !important;
}
[data-testid="stSidebar"] button:hover { background: #131925 !important; color: #d0d8e8 !important }
[data-testid="stSidebar"] button p { font-size: 13px !important; text-align: left !important }

/* ── Nav active ── */
.nav-active {
    font-size: 13px; font-weight: 600; color: #60a5fa;
    padding: 6px 10px; border-radius: 6px;
    background: #0e1e3a; border-left: 2px solid #3b82f6;
    margin-bottom: 1px; display: block;
}

/* ── Nav section labels ── */
.nav-section {
    font-size: 10px; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; color: #6a7f96;
    padding: 14px 10px 5px; margin-top: 2px;
}

/* ── Sidebar record ── */
.record-mini { display: flex; gap: 0; border: 1px solid #1a2030; border-radius: 8px; overflow: hidden; margin: 6px 10px 12px }
.rc-mini { flex: 1; padding: .6rem .5rem; background: #0c0f18; border-right: 1px solid #1a2030; text-align: center }
.rc-mini:last-child { border-right: none }
.rcm-val { font-size: 13px; font-weight: 700; color: #f0f2f5 }
.rcm-lbl { font-size: 9px; color: #6a7f96; letter-spacing: .05em; text-transform: uppercase; margin-top: 1px }
.rcm-val.green { color: #10b981 } .rcm-val.red { color: #ef4444 }

/* ── Page header ── */
.page-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 1.25rem 0 1rem; border-bottom: 1px solid #1e2d42; margin-bottom: 1.25rem;
}
.page-title { font-size: 22px; font-weight: 800; color: #f0f2f5; letter-spacing: -.4px; line-height: 1 }
.page-subtitle { font-size: 12px; color: #8090a8; margin-top: 3px }
.page-date { font-size: 11px; color: #7a8fa8; font-weight: 500 }
.live-dot { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600;
            letter-spacing: .06em; color: #10b981; text-transform: uppercase }
.live-dot::before { content: ''; width: 6px; height: 6px; border-radius: 50%;
                    background: #10b981; display: inline-block; animation: pulse 1.8s infinite }
@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: .35 } }

/* ── Stats strip ── */
.stats-strip { display: flex; gap: 0; border: 1px solid #1e2d42; border-radius: 10px; overflow: hidden; margin-bottom: 1.25rem }
.stat-cell { flex: 1; padding: .7rem 1rem; background: #131d2e; border-right: 1px solid #1e2d42; text-align: center }
.stat-cell:last-child { border-right: none }
.sc-val { font-size: 18px; font-weight: 700; color: #f0f2f5 }
.sc-lbl { font-size: 10px; color: #8090a8; letter-spacing: .06em; text-transform: uppercase; margin-top: 2px }
.sc-val.green { color: #10b981 } .sc-val.red { color: #ef4444 }

/* ── Sport cards ── */
.sport-card {
    background: #131d2e; border: 1px solid #1e2d42; border-radius: 10px;
    overflow: hidden; margin-bottom: 12px;
}
.sport-card-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: .75rem 1.25rem; border-bottom: 1px solid #1e2d42;
}
.sport-card-icon { font-size: 18px; line-height: 1 }
.sport-card-name { font-size: 14px; font-weight: 700; color: #f0f2f5; margin-left: 9px }
.sport-card-sub { font-size: 11px; color: #8090a8; margin-top: 1px }
.sport-card-meta { display: flex; align-items: center; gap: 8px }
.sport-badge-live { font-size: 10px; font-weight: 700; letter-spacing: .08em; color: #10b981;
                    text-transform: uppercase; padding: 2px 7px; border-radius: 4px;
                    background: rgba(16,185,129,.1); border: 1px solid rgba(16,185,129,.2) }
.sport-badge-off { font-size: 10px; font-weight: 600; letter-spacing: .08em; color: #7a8fa8;
                   text-transform: uppercase; padding: 2px 7px; border-radius: 4px;
                   border: 1px solid #1e2d42 }

/* ── Pick columns (side-by-side inside sport card) ── */
.picks-row { display: flex; border-bottom: 1px solid #1a2840 }
.pick-col { flex: 1; padding: .875rem 1.25rem }
.pick-col + .pick-col { border-left: 1px solid #1a2840 }
.pick-type-label { font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
                   color: #96aec8; margin-bottom: 6px }
.pick-team { font-size: 15px; font-weight: 700; color: #f0f2f5; letter-spacing: -.2px }
.pick-odds { font-size: 13px; font-weight: 600; color: #8090a8; margin-left: 5px }
.pick-chips { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 7px }
.chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 20px;
        font-size: 11px; font-weight: 600 }
.chip-green { background: rgba(16,185,129,.12); color: #10b981; border: 1px solid rgba(16,185,129,.22) }
.chip-blue  { background: rgba(59,130,246,.12); color: #60a5fa; border: 1px solid rgba(59,130,246,.22) }
.chip-gray  { background: rgba(255,255,255,.07); color: #8090a8; border: 1px solid #1e2d42 }
.chip-orange{ background: rgba(249,115,22,.12); color: #fb923c; border: 1px solid rgba(249,115,22,.25) }
.no-pick-col { padding: .875rem 1.25rem; font-size: 13px; color: #96aec8; font-style: italic;
               display: flex; align-items: center }

/* ── Val count pills ── */
.val-pills { display: flex; gap: 5px; flex-wrap: wrap; padding: .55rem 1.25rem;
             border-top: 1px solid #1a2840 }
.val-pill { font-size: 10px; font-weight: 600; letter-spacing: .04em; padding: 2px 7px;
            border-radius: 10px; color: #7a8fa8; background: #0f1828; border: 1px solid #1e2d42 }
.val-pill.active { color: #60a5fa; background: rgba(59,130,246,.10); border-color: rgba(59,130,246,.25) }

/* ── Coming soon ── */
.coming-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: .6rem 1.25rem; border-bottom: 1px solid #131a26; opacity: .5;
}
.coming-row:last-child { border-bottom: none }
.coming-sport-name { font-size: 13px; font-weight: 600; color: #f0f2f5 }
.coming-eta-tag { font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
                  color: #6a7f96; padding: 2px 7px; border-radius: 4px; border: 1px solid #1e2d42 }

/* ── Section header ── */
.sh { font-size: 11px; font-weight: 700; letter-spacing: .1em; color: #8090a8;
      text-transform: uppercase; margin: 1.25rem 0 .75rem; padding-bottom: 7px;
      border-bottom: 1px solid #1e2d42 }

/* ── Override page module cards to match new palette ── */
.game-card, .leg-card, .parlay-summary, .roi-section {
    background: #131d2e !important; border-color: #1e2d42 !important;
}
.best-bet-card.value { background: linear-gradient(135deg,#0a0e1a 0%,#0d1320 100%) !important;
                        border-color: #3b82f6 !important; }
.best-bet-card.value::before { background: linear-gradient(90deg,#3b82f6,#10b981,#3b82f6) !important }
.bb-tier-value { color: #3b82f6 !important }
.bb-pick-value { background: #0a1428 !important; border-color: #3b82f6 !important; color: #60a5fa !important }
.vbadge { background: #062318 !important; color: #10b981 !important; border-color: #0d4a2a !important }
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
NBA_DB = "nba.db"
MLB_DB = "mlb.db"
NHL_DB = "nhl.db"

def load(db_path, query, params=None):
    if not Path(db_path).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql(query, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

def fmt(price):
    try:
        p = int(price)
        return f"+{p}" if p > 0 else str(p)
    except Exception:
        return "N/A"

def fmt_tip(commence_time):
    try:
        return pd.to_datetime(commence_time, utc=True)\
                 .tz_convert("America/New_York")\
                 .strftime("%-I:%M %p ET")
    except Exception:
        try:
            return pd.to_datetime(commence_time, utc=True)\
                     .tz_convert("America/New_York")\
                     .strftime("%I:%M %p ET").lstrip("0")
        except Exception:
            return ""

def composite_score(edge, prob, kelly, recent_hr=None):
    """Rank picks by edge + model confidence + kelly. Optional recent hit rate."""
    base = 0.40 * edge + 0.35 * max(0, prob - 0.5) + 0.25 * kelly
    if recent_hr is not None:
        base = base * 0.90 + 0.10 * max(0, recent_hr - 0.5)
    return base

def get_best_bet(preds, min_edge=0.05):
    candidates = []
    for _, game in preds.iterrows():
        for side in ["home", "away"]:
            if not game.get(f"{side}_value"):
                continue
            edge  = float(game.get(f"{side}_edge", 0))
            prob  = float(game.get(f"model_{side}_prob", 0))
            kelly = float(game.get(f"{side}_kelly", 0))
            price = game.get(f"{side}_price")
            if edge < min_edge or prob < 0.50 or kelly < 0.005:
                continue
            bet_team = game["home_team"] if side == "home" else game["away_team"]
            candidates.append({
                "bet_team": bet_team, "edge": edge, "prob": prob,
                "price": price, "kelly": kelly,
                "commence_time": game.get("commence_time", ""),
                "score": composite_score(edge, prob, kelly),
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["score"], reverse=True)[0]

def get_best_ats(spread_preds, min_edge=0.03):
    candidates = []
    for _, g in spread_preds.iterrows():
        for side in ["home", "away"]:
            edge  = float(g.get(f"{side}_ats_edge", 0))
            prob  = float(g.get(f"{side}_cover_prob", 0))
            kelly = float(g.get(f"{side}_ats_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_ats_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005:
                continue
            candidates.append({
                "side": side,
                "bet_team":         g["home_team"] if side == "home" else g["away_team"],
                "home_team":        g["home_team"],
                "away_team":        g["away_team"],
                "commence_time":    g.get("commence_time", ""),
                "spread":           g.get(f"{side}_point"),
                "pred_home_margin": float(g.get("pred_home_margin", 0)),
                "cover_prob":       prob,
                "edge":             edge,
                "kelly":            kelly,
                "price":            price,
                "score":            composite_score(edge, prob, kelly),
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["score"], reverse=True)[0]

def get_best_prop(db_path, tables, today, min_edge=0.08):
    """Return the best value prop pick across the given list of (table, pred_col, unit) tuples."""
    best = None
    for table, pred_col, unit in tables:
        df = load(db_path, f"SELECT * FROM {table} WHERE predict_date=? ORDER BY over_edge DESC", params=(today,))
        if df.empty:
            continue
        for _, g in df.iterrows():
            for side in ["over", "under"]:
                edge  = float(g.get(f"{side}_edge", 0))
                prob  = float(g.get(f"{side}_prob", 0))
                kelly = float(g.get(f"{side}_kelly", 0))
                price = g.get(f"{side}_price")
                val   = int(g.get(f"{side}_value", 0))
                if val != 1 or edge < min_edge or kelly < 0.005:
                    continue
                score = composite_score(edge, prob, kelly)
                if best is None or score > best["score"]:
                    best = {
                        "player_name": g["player_name"],
                        "side":        side,
                        "line":        g.get("line"),
                        "pred_val":    float(g.get(pred_col, 0)),
                        "unit":        unit,
                        "edge":        edge,
                        "prob":        prob,
                        "kelly":       kelly,
                        "price":       price,
                        "score":       score,
                    }
    return best

def get_overall_record(db_path, table="bet_log"):
    df = load(db_path, f"SELECT result, profit_units FROM {table} WHERE result IN ('WIN','LOSS')")
    if df.empty:
        return 0, 0, 0.0
    wins  = (df["result"] == "WIN").sum()
    total = len(df)
    return int(wins), int(total - wins), float(df["profit_units"].sum())

# ── Pre-load season record ────────────────────────────────────────────────────
nba_w, nba_l, nba_u = get_overall_record(NBA_DB, "bet_log")
mlb_w, mlb_l, mlb_u = get_overall_record(MLB_DB, "mlb_bet_log")
nhl_w, nhl_l, nhl_u = get_overall_record(NHL_DB, "nhl_bet_log")
total_w = nba_w + mlb_w + nhl_w
total_l = nba_l + mlb_l + nhl_l
total_u = nba_u + mlb_u + nhl_u
win_pct = total_w / (total_w + total_l) if (total_w + total_l) > 0 else 0
uc = "green" if total_u >= 0 else "red"
wc = "green" if win_pct >= 0.55 else ("red" if win_pct < 0.50 else "")

# ── Session state ─────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "home"

# ── Sidebar ───────────────────────────────────────────────────────────────────
def _nav(label, key):
    if st.session_state.page == key:
        st.sidebar.markdown(f'<div class="nav-active">{label}</div>', unsafe_allow_html=True)
    else:
        if st.sidebar.button(label, key=f"btn_{key}", use_container_width=True):
            st.session_state.page = key
            st.rerun()

with st.sidebar:
    # Branding
    st.markdown("""
<div style="padding:1.4rem 10px 1rem">
  <div style="font-size:10px;font-weight:700;letter-spacing:.22em;color:#3b82f6;
              text-transform:uppercase;margin-bottom:5px">⚡ AXIOM</div>
  <div style="font-size:20px;font-weight:800;color:#f0f2f5;letter-spacing:-.4px;
              line-height:1">Edge</div>
  <div style="font-size:11px;color:#7a8fa8;margin-top:3px;font-weight:400">
    AI Sports Analytics
  </div>
</div>
<div style="height:1px;background:#1a2030;margin:0 10px .25rem"></div>
""", unsafe_allow_html=True)

    _nav("🏠  Dashboard",        "home")
    _nav("💰  Bankroll Tracker", "bankroll")
    _nav("📊  Model Performance","model_perf")

    # NBA group
    st.markdown('<div class="nav-section">🏀  NBA</div>', unsafe_allow_html=True)
    _nav("  Today's Picks", "nba_picks")
    _nav("  ROI Tracker",   "nba_roi")
    _nav("  Parlay Builder","parlay")
    _nav("  Player Research","player")

    # MLB group
    st.markdown('<div class="nav-section">⚾  MLB</div>', unsafe_allow_html=True)
    _nav("  Today's Picks", "mlb_picks")
    _nav("  Player Props",  "mlb_props")
    _nav("  ROI Tracker",   "mlb_roi")
    _nav("  Player Research","mlb_player")

    # NHL group
    st.markdown('<div class="nav-section">🏒  NHL</div>', unsafe_allow_html=True)
    _nav("  Today's Picks", "nhl_picks")
    _nav("  ROI Tracker",   "nhl_roi")

    # Coming soon
    st.markdown("""
<div style="height:1px;background:#1a2030;margin:8px 10px 0"></div>
<div class="nav-section" style="margin-top:0">🔜  Coming Soon</div>
<div style="padding:3px 10px 8px;font-size:12px;color:#222d3e;
            display:flex;justify-content:space-between">
  <span>🏈 NFL</span>
  <span style="font-size:9px;letter-spacing:.06em;color:#1e2a3a;text-transform:uppercase">Aug 2026</span>
</div>
""", unsafe_allow_html=True)

    # Season record
    st.markdown(f"""
<div style="height:1px;background:#1a2030;margin:4px 10px 0"></div>
<div style="padding:8px 10px 3px;font-size:9px;font-weight:700;
            letter-spacing:.12em;color:#1e2a3a;text-transform:uppercase">
  Season record
</div>
<div class="record-mini">
  <div class="rc-mini">
    <div class="rcm-val {wc}">{win_pct:.1%}</div>
    <div class="rcm-lbl">Win%</div>
  </div>
  <div class="rc-mini">
    <div class="rcm-val">{total_w}–{total_l}</div>
    <div class="rcm-lbl">W–L</div>
  </div>
  <div class="rc-mini">
    <div class="rcm-val {uc}">{total_u:+.1f}u</div>
    <div class="rcm-lbl">Units</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Page routing ──────────────────────────────────────────────────────────────
page = st.session_state.page

# ── HOME ──────────────────────────────────────────────────────────────────────
if page == "home":
    today      = date.today().isoformat()
    try:
        today_long = date.today().strftime("%A, %B %-d")
    except ValueError:
        today_long = date.today().strftime("%A, %B %d").replace(" 0", " ")

    # ── Page header ──────────────────────────────────────────────────────────
    st.markdown(f"""
<div class="page-header">
  <div>
    <div class="page-title">Today's Report</div>
    <div class="page-subtitle">Machine learning picks across NBA &amp; MLB</div>
  </div>
  <div style="display:flex;align-items:center;gap:14px">
    <div class="live-dot">Models active</div>
    <div class="page-date">{today_long}</div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Stats strip ──────────────────────────────────────────────────────────
    total_bets = total_w + total_l
    roi_pct    = (total_u / total_bets * 100) if total_bets > 0 else 0
    roi_c      = "green" if roi_pct >= 0 else "red"

    st.markdown(f"""
<div class="stats-strip">
  <div class="stat-cell">
    <div class="sc-val {wc}">{win_pct:.1%}</div>
    <div class="sc-lbl">Win rate</div>
  </div>
  <div class="stat-cell">
    <div class="sc-val">{total_w}W &nbsp;{total_l}L</div>
    <div class="sc-lbl">All-sports record</div>
  </div>
  <div class="stat-cell">
    <div class="sc-val {uc}">{total_u:+.2f}</div>
    <div class="sc-lbl">Units P&L</div>
  </div>
  <div class="stat-cell">
    <div class="sc-val {roi_c}">{roi_pct:+.1f}%</div>
    <div class="sc-lbl">ROI per bet</div>
  </div>
  <div class="stat-cell">
    <div class="sc-val">{total_bets:,}</div>
    <div class="sc-lbl">Bets tracked</div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Sport cards ──────────────────────────────────────────────────────────
    st.markdown("<div class='sh'>Today's best bets</div>", unsafe_allow_html=True)

    # ── NBA card (full-width, ML + ATS side by side) ─────────────────────────
    nba_preds  = load(NBA_DB, "SELECT * FROM predictions WHERE predict_date=? ORDER BY commence_time", params=(today,))
    nba_spread = load(NBA_DB, "SELECT * FROM spread_predictions WHERE predict_date=? ORDER BY commence_time", params=(today,))
    nba_totals = load(NBA_DB, "SELECT * FROM totals_predictions WHERE predict_date=?", params=(today,))
    nba_props  = load(NBA_DB, "SELECT * FROM props_predictions WHERE predict_date=?",  params=(today,))
    nba_best   = get_best_bet(nba_preds)  if not nba_preds.empty  else None
    nba_ats    = get_best_ats(nba_spread) if not nba_spread.empty else None
    nba_prop   = get_best_prop(NBA_DB, [
        ("props_predictions",       "pred_pts",    "pts"),
        ("props_reb_predictions",   "pred_reb",    "reb"),
        ("props_ast_predictions",   "pred_ast",    "ast"),
        ("props_threes_predictions","pred_threes", "3PM"),
        ("props_stl_predictions",   "pred_stl",    "stl"),
        ("props_blk_predictions",   "pred_blk",    "blk"),
    ], today)

    nba_ml_val  = int(((nba_preds["home_value"]==1)|(nba_preds["away_value"]==1)).sum())            if not nba_preds.empty  else 0
    nba_ats_val = int(((nba_spread["home_ats_value"]==1)|(nba_spread["away_ats_value"]==1)).sum())  if not nba_spread.empty else 0
    nba_tot_val = int(((nba_totals["over_value"]==1)|(nba_totals["under_value"]==1)).sum())         if not nba_totals.empty else 0
    nba_prp_val = int(((nba_props["over_value"]==1)|(nba_props["under_value"]==1)).sum())           if not nba_props.empty  else 0
    nba_games   = len(nba_preds)

    # Build pick column content (inner HTML only, outer div added below)
    if nba_best:
        tip     = fmt_tip(nba_best.get("commence_time", ""))
        tip_str = f'<span style="font-size:11px;color:#7a8fa8;margin-left:5px">{tip}</span>' if tip else ""
        nba_ml_inner = f"""
  <div class="pick-type-label">Best moneyline</div>
  <div><span class="pick-team">{nba_best['bet_team']}</span><span class="pick-odds">{fmt(nba_best['price'])}</span>{tip_str}</div>
  <div class="pick-chips">
    <span class="chip chip-green">+{nba_best['edge']:.1%} edge</span>
    <span class="chip chip-blue">{nba_best['prob']:.0%} prob</span>
    <span class="chip chip-gray">Kelly {nba_best['kelly']*100:.1f}%</span>
  </div>"""
    else:
        nba_ml_inner = f'<span style="font-size:13px;color:#96aec8;font-style:italic">{"No games today" if nba_preds.empty else "No ML edge today"}</span>'

    if nba_ats:
        spr = f"{nba_ats['spread']:+.1f}" if nba_ats["spread"] is not None else ""
        nba_ats_inner = f"""
  <div class="pick-type-label">Best spread</div>
  <div><span class="pick-team">{nba_ats['bet_team']} {spr}</span><span class="pick-odds">{fmt(nba_ats['price'])}</span></div>
  <div class="pick-chips">
    <span class="chip chip-green">+{nba_ats['edge']:.1%} edge</span>
    <span class="chip chip-blue">{nba_ats['cover_prob']:.0%} cover</span>
    <span class="chip chip-gray">{nba_ats['pred_home_margin']:+.1f} pred margin</span>
  </div>"""
    else:
        nba_ats_inner = '<span style="font-size:13px;color:#96aec8;font-style:italic">No spread edge today</span>'

    if nba_prop:
        side_lbl = "OVER" if nba_prop["side"] == "over" else "UNDER"
        nba_prop_inner = f"""
  <div class="pick-type-label">Best prop · {nba_prop['unit'].upper()}</div>
  <div><span class="pick-team">{nba_prop['player_name']}</span></div>
  <div style="font-size:13px;color:#5a6478;margin-top:2px">{side_lbl} {nba_prop['line']} {nba_prop['unit']} &nbsp;<span style="color:#8892a4">{fmt(nba_prop['price'])}</span></div>
  <div class="pick-chips">
    <span class="chip chip-green">+{nba_prop['edge']:.1%} edge</span>
    <span class="chip chip-blue">{nba_prop['prob']:.0%} prob</span>
    <span class="chip chip-gray">Kelly {nba_prop['kelly']*100:.1f}%</span>
  </div>"""
    else:
        nba_prop_inner = '<span style="font-size:13px;color:#96aec8;font-style:italic">No prop edge today</span>'

    nba_ml_a  = f'<span class="val-pill{"  active" if nba_ml_val  > 0 else ""}">{nba_ml_val} ML</span>'
    nba_ats_a = f'<span class="val-pill{"  active" if nba_ats_val > 0 else ""}">{nba_ats_val} ATS</span>'
    nba_tot_a = f'<span class="val-pill{"  active" if nba_tot_val > 0 else ""}">{nba_tot_val} O/U</span>'
    nba_prp_a = f'<span class="val-pill{"  active" if nba_prp_val > 0 else ""}">{nba_prp_val} Props</span>'

    st.markdown(f"""
<div class="sport-card">
  <div class="sport-card-header">
    <div style="display:flex;align-items:center">
      <span class="sport-card-icon">🏀</span>
      <div style="margin-left:9px">
        <div class="sport-card-name">NBA</div>
        <div class="sport-card-sub">{nba_games} game{'s' if nba_games != 1 else ''} today</div>
      </div>
    </div>
    <span class="{'sport-badge-live' if nba_games > 0 else 'sport-badge-off'}">
      {'● Live' if nba_games > 0 else 'No games'}
    </span>
  </div>
  <div class="picks-row">
    <div class="pick-col">{nba_ml_inner}</div>
    <div class="pick-col" style="border-left:1px solid #131a26">{nba_ats_inner}</div>
    <div class="pick-col" style="border-left:1px solid #131a26">{nba_prop_inner}</div>
  </div>
  <div class="val-pills">{nba_ml_a}{nba_ats_a}{nba_tot_a}{nba_prp_a}</div>
</div>
""", unsafe_allow_html=True)

    if st.button("View all NBA picks →", key="home_nba_btn", use_container_width=True):
        st.session_state.page = "nba_picks"
        st.rerun()

    # ── MLB card (full-width, ML + RL side by side) ───────────────────────────
    mlb_preds  = load(MLB_DB, "SELECT * FROM mlb_predictions WHERE predict_date=? ORDER BY commence_time", params=(today,))
    mlb_spread = load(MLB_DB, "SELECT * FROM mlb_spread_predictions WHERE predict_date=?", params=(today,))
    mlb_totals = load(MLB_DB, "SELECT * FROM mlb_totals_predictions WHERE predict_date=?", params=(today,))
    mlb_best   = get_best_bet(mlb_preds)  if not mlb_preds.empty  else None
    mlb_ats    = get_best_ats(mlb_spread) if not mlb_spread.empty else None
    mlb_prop   = get_best_prop(MLB_DB, [
        ("mlb_props_predictions_k",    "pred_ks",   "K's"),
        ("mlb_props_predictions_hits", "pred_hits", "hits"),
        ("mlb_props_predictions_tb",   "pred_tb",   "TB"),
    ], today)

    mlb_ml_val  = int(((mlb_preds["home_value"]==1)|(mlb_preds["away_value"]==1)).sum())            if not mlb_preds.empty  else 0
    mlb_ats_val = int(((mlb_spread["home_ats_value"]==1)|(mlb_spread["away_ats_value"]==1)).sum())  if not mlb_spread.empty else 0
    mlb_tot_val = int(((mlb_totals["over_value"]==1)|(mlb_totals["under_value"]==1)).sum())         if not mlb_totals.empty else 0
    mlb_prp_val = 0
    for _tbl in ["mlb_props_predictions_k", "mlb_props_predictions_hits", "mlb_props_predictions_tb"]:
        _tdf = load(MLB_DB, f"SELECT over_value, under_value FROM {_tbl} WHERE predict_date=?", params=(today,))
        if not _tdf.empty:
            mlb_prp_val += int(_tdf["over_value"].fillna(0).sum() + _tdf["under_value"].fillna(0).sum())
    mlb_games   = len(mlb_preds)

    if mlb_best:
        tip     = fmt_tip(mlb_best.get("commence_time", ""))
        tip_str = f'<span style="font-size:11px;color:#7a8fa8;margin-left:5px">{tip}</span>' if tip else ""
        mlb_ml_inner = f"""
  <div class="pick-type-label">Best moneyline</div>
  <div><span class="pick-team">{mlb_best['bet_team']}</span><span class="pick-odds">{fmt(mlb_best['price'])}</span>{tip_str}</div>
  <div class="pick-chips">
    <span class="chip chip-green">+{mlb_best['edge']:.1%} edge</span>
    <span class="chip chip-blue">{mlb_best['prob']:.0%} prob</span>
    <span class="chip chip-gray">Kelly {mlb_best['kelly']*100:.1f}%</span>
  </div>"""
    else:
        mlb_ml_inner = f'<span style="font-size:13px;color:#96aec8;font-style:italic">{"No games today" if mlb_preds.empty else "No ML edge today"}</span>'

    if mlb_ats:
        spr = f"{mlb_ats['spread']:+.1f}" if mlb_ats["spread"] is not None else ""
        mlb_ats_inner = f"""
  <div class="pick-type-label">Best run line</div>
  <div><span class="pick-team">{mlb_ats['bet_team']} {spr}</span><span class="pick-odds">{fmt(mlb_ats['price'])}</span></div>
  <div class="pick-chips">
    <span class="chip chip-green">+{mlb_ats['edge']:.1%} edge</span>
    <span class="chip chip-blue">{mlb_ats['cover_prob']:.0%} cover</span>
  </div>"""
    else:
        mlb_ats_inner = '<span style="font-size:13px;color:#96aec8;font-style:italic">No run line edge today</span>'

    if mlb_prop:
        side_lbl = "OVER" if mlb_prop["side"] == "over" else "UNDER"
        mlb_prop_inner = f"""
  <div class="pick-type-label">Best prop · {mlb_prop['unit'].upper()}</div>
  <div><span class="pick-team">{mlb_prop['player_name']}</span></div>
  <div style="font-size:13px;color:#5a6478;margin-top:2px">{side_lbl} {mlb_prop['line']} {mlb_prop['unit']} &nbsp;<span style="color:#8892a4">{fmt(mlb_prop['price'])}</span></div>
  <div class="pick-chips">
    <span class="chip chip-green">+{mlb_prop['edge']:.1%} edge</span>
    <span class="chip chip-blue">{mlb_prop['prob']:.0%} prob</span>
    <span class="chip chip-gray">Kelly {mlb_prop['kelly']*100:.1f}%</span>
  </div>"""
    else:
        mlb_prop_inner = '<span style="font-size:13px;color:#96aec8;font-style:italic">No prop edge today</span>'

    mlb_ml_a  = f'<span class="val-pill{"  active" if mlb_ml_val  > 0 else ""}">{mlb_ml_val} ML</span>'
    mlb_ats_a = f'<span class="val-pill{"  active" if mlb_ats_val > 0 else ""}">{mlb_ats_val} RL</span>'
    mlb_tot_a = f'<span class="val-pill{"  active" if mlb_tot_val > 0 else ""}">{mlb_tot_val} O/U</span>'
    mlb_prp_a = f'<span class="val-pill{"  active" if mlb_prp_val > 0 else ""}">{mlb_prp_val} Props</span>'

    st.markdown(f"""
<div class="sport-card">
  <div class="sport-card-header">
    <div style="display:flex;align-items:center">
      <span class="sport-card-icon">⚾</span>
      <div style="margin-left:9px">
        <div class="sport-card-name">MLB</div>
        <div class="sport-card-sub">{mlb_games} game{'s' if mlb_games != 1 else ''} today</div>
      </div>
    </div>
    <span class="{'sport-badge-live' if mlb_games > 0 else 'sport-badge-off'}">
      {'● Live' if mlb_games > 0 else 'No games'}
    </span>
  </div>
  <div class="picks-row">
    <div class="pick-col">{mlb_ml_inner}</div>
    <div class="pick-col" style="border-left:1px solid #131a26">{mlb_ats_inner}</div>
    <div class="pick-col" style="border-left:1px solid #131a26">{mlb_prop_inner}</div>
  </div>
  <div class="val-pills">{mlb_ml_a}{mlb_ats_a}{mlb_tot_a}{mlb_prp_a}</div>
</div>
""", unsafe_allow_html=True)

    if st.button("View all MLB picks →", key="home_mlb_btn", use_container_width=True):
        st.session_state.page = "mlb_picks"
        st.rerun()

    # ── NHL card ──────────────────────────────────────────────────────────────
    nhl_preds  = load(NHL_DB, "SELECT * FROM nhl_predictions WHERE predict_date=? ORDER BY commence_time", params=(today,))
    nhl_spread = load(NHL_DB, "SELECT * FROM nhl_spread_predictions WHERE predict_date=?", params=(today,))
    nhl_totals = load(NHL_DB, "SELECT * FROM nhl_totals_predictions WHERE predict_date=?", params=(today,))

    nhl_ml_val  = int(((nhl_preds["home_value"]==1)|(nhl_preds["away_value"]==1)).sum())          if not nhl_preds.empty  else 0
    nhl_ats_val = int(((nhl_spread["home_value"]==1)|(nhl_spread["away_value"]==1)).sum())         if not nhl_spread.empty else 0
    nhl_tot_val = int(((nhl_totals["over_value"]==1)|(nhl_totals["under_value"]==1)).sum())        if not nhl_totals.empty else 0
    nhl_games   = len(nhl_preds)

    # Best NHL ML pick
    nhl_best = None
    for _, g in nhl_preds.iterrows():
        for side in ["home", "away"]:
            if not g.get(f"{side}_value", 0):
                continue
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"model_{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            score = composite_score(edge, prob, kelly)
            team  = g[f"{side}_team"]
            price = g.get(f"{side}_price")
            ct    = g.get("commence_time", "")
            if nhl_best is None or score > nhl_best["score"]:
                nhl_best = {"bet_team": team, "edge": edge, "prob": prob,
                            "kelly": kelly, "price": price, "score": score,
                            "commence_time": ct}

    # Best NHL puck line pick
    nhl_pl_best = None
    for _, g in nhl_spread.iterrows():
        for side in ["home", "away"]:
            if not g.get(f"{side}_value", 0):
                continue
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"model_{side}_cover_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            score = composite_score(edge, prob, kelly)
            team  = g[f"{side}_team"]
            price = g.get(f"{side}_price")
            pt    = g.get(f"{side}_point", -1.5 if side == "home" else 1.5)
            if nhl_pl_best is None or score > nhl_pl_best["score"]:
                nhl_pl_best = {"bet_team": team, "spread": pt, "edge": edge,
                               "prob": prob, "kelly": kelly, "price": price, "score": score}

    if nhl_best:
        tip     = fmt_tip(nhl_best.get("commence_time", ""))
        tip_str = f'<span style="font-size:11px;color:#7a8fa8;margin-left:5px">{tip}</span>' if tip else ""
        nhl_ml_inner = f"""
  <div class="pick-type-label">Best moneyline</div>
  <div><span class="pick-team">{nhl_best['bet_team']}</span><span class="pick-odds">{fmt(nhl_best['price'])}</span>{tip_str}</div>
  <div class="pick-chips">
    <span class="chip chip-green">+{nhl_best['edge']:.1%} edge</span>
    <span class="chip chip-blue">{nhl_best['prob']:.0%} prob</span>
    <span class="chip chip-gray">Kelly {nhl_best['kelly']*100:.1f}%</span>
  </div>"""
    else:
        nhl_ml_inner = f'<span style="font-size:13px;color:#96aec8;font-style:italic">{"No games today" if nhl_preds.empty else "No ML edge today"}</span>'

    if nhl_pl_best:
        spr = f"{nhl_pl_best['spread']:+.1f}" if nhl_pl_best["spread"] is not None else ""
        nhl_pl_inner = f"""
  <div class="pick-type-label">Best puck line</div>
  <div><span class="pick-team">{nhl_pl_best['bet_team']} {spr}</span><span class="pick-odds">{fmt(nhl_pl_best['price'])}</span></div>
  <div class="pick-chips">
    <span class="chip chip-green">+{nhl_pl_best['edge']:.1%} edge</span>
    <span class="chip chip-blue">{nhl_pl_best['prob']:.0%} cover</span>
  </div>"""
    else:
        nhl_pl_inner = '<span style="font-size:13px;color:#96aec8;font-style:italic">No puck line edge today</span>'

    nhl_ml_a  = f'<span class="val-pill{"  active" if nhl_ml_val  > 0 else ""}">{nhl_ml_val} ML</span>'
    nhl_ats_a = f'<span class="val-pill{"  active" if nhl_ats_val > 0 else ""}">{nhl_ats_val} PL</span>'
    nhl_tot_a = f'<span class="val-pill{"  active" if nhl_tot_val > 0 else ""}">{nhl_tot_val} O/U</span>'

    st.markdown(f"""
<div class="sport-card">
  <div class="sport-card-header">
    <div style="display:flex;align-items:center">
      <span class="sport-card-icon">🏒</span>
      <div style="margin-left:9px">
        <div class="sport-card-name">NHL</div>
        <div class="sport-card-sub">{nhl_games} game{'s' if nhl_games != 1 else ''} today</div>
      </div>
    </div>
    <span class="{'sport-badge-live' if nhl_games > 0 else 'sport-badge-off'}">
      {'● Live' if nhl_games > 0 else 'No games'}
    </span>
  </div>
  <div class="picks-row">
    <div class="pick-col">{nhl_ml_inner}</div>
    <div class="pick-col" style="border-left:1px solid #131a26">{nhl_pl_inner}</div>
  </div>
  <div class="val-pills">{nhl_ml_a}{nhl_ats_a}{nhl_tot_a}</div>
</div>
""", unsafe_allow_html=True)

    if st.button("View all NHL picks →", key="home_nhl_btn", use_container_width=True):
        st.session_state.page = "nhl_picks"
        st.rerun()

    # ── Coming soon ───────────────────────────────────────────────────────────
    st.markdown("<div class='sh'>In development</div>", unsafe_allow_html=True)
    st.markdown("""
<div style="background:#0f1218;border:1px solid #1d2333;border-radius:10px;overflow:hidden">
  <div class="coming-row">
    <div style="display:flex;align-items:center;gap:10px">
      <span style="font-size:16px">🏈</span>
      <div>
        <div class="coming-sport-name">NFL</div>
        <div style="font-size:11px;color:#7a8fa8;margin-top:1px">Moneyline · spread · totals · player props</div>
      </div>
    </div>
    <span class="coming-eta-tag">Aug 2026</span>
  </div>
</div>""", unsafe_allow_html=True)

# ── Page routing ──────────────────────────────────────────────────────────────
elif page == "bankroll":
    from page_modules.bankroll_tracker import render as render_bankroll
    render_bankroll()

elif page == "nba_picks":
    from page_modules.nba_picks import render
    render()

elif page == "nba_roi":
    from page_modules.nba_roi import render as render_nba_roi
    render_nba_roi()

elif page == "parlay":
    from page_modules.parlay_builder import render as render_parlay
    render_parlay()

elif page == "player":
    from page_modules.player_research import render as render_player
    render_player()

elif page == "mlb_picks":
    from page_modules.mlb_picks import render as render_mlb
    render_mlb()

elif page == "mlb_roi":
    from page_modules.mlb_roi import render as render_roi
    render_roi()

elif page == "mlb_player":
    from page_modules.mlb_player_research import render as render_mlb_player
    render_mlb_player()

elif page == "mlb_props":
    from page_modules.mlb_props import render as render_mlb_props
    render_mlb_props()

elif page == "nhl_picks":
    from page_modules.nhl_picks import render as render_nhl
    render_nhl()

elif page == "nhl_roi":
    from page_modules.nhl_roi import render as render_nhl_roi
    render_nhl_roi()

elif page == "model_perf":
    from page_modules.model_performance import render as render_perf
    render_perf()
