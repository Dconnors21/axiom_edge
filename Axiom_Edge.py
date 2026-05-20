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

# ── Session state ──────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "home"

st.markdown("""
<style>
/* ── App background ── */
.stApp{background-color:#0a0a0c}
[data-testid="stSidebar"]{background-color:#0f0f12;border-right:1px solid #1e1e28}
[data-testid="stSidebarContent"]{padding-top:0}
#MainMenu,footer,header{visibility:hidden}
[data-testid="stToolbar"]{display:none}
.block-container{padding-top:0;padding-bottom:2rem;max-width:1200px}
html,body,[class*="css"]{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e8e8ec}

/* ── Metrics ── */
[data-testid="metric-container"]{background:#13131a;border:1px solid #1e1e28;border-radius:10px;padding:1rem 1.25rem}
[data-testid="metric-container"] label{color:#6b6b78!important;font-size:11px!important;letter-spacing:.06em;text-transform:uppercase}
[data-testid="stMetricValue"]{color:#e8e8ec!important;font-size:22px!important;font-weight:700!important}

/* ── Sidebar nav buttons — strip all Streamlit chrome ── */
[data-testid="stSidebar"] button{
    background:transparent!important;
    border:none!important;
    box-shadow:none!important;
    color:#6b6b78!important;
    font-size:13px!important;
    font-weight:400!important;
    padding:7px 12px!important;
    text-align:left!important;
    justify-content:flex-start!important;
    border-radius:6px!important;
    transition:all .15s!important;
    margin-bottom:1px!important;
    width:100%!important;
}
[data-testid="stSidebar"] button:hover{background:#1a1a24!important;color:#e8e8ec!important}
[data-testid="stSidebar"] button p{font-size:13px!important;text-align:left!important}

/* ── Nav active item ── */
.nav-active{
    font-size:13px;font-weight:600;color:#6b8ef7;
    padding:7px 12px;border-radius:6px;background:#1a2040;
    margin-bottom:1px;
}

/* ── Nav section labels ── */
.nav-section{
    font-size:10px;font-weight:700;letter-spacing:.12em;
    text-transform:uppercase;color:#333340;
    padding:12px 12px 4px;margin-top:4px;
    border-top:1px solid #1a1a20;
}
.nav-coming{
    font-size:12px;color:#2a2a35;
    padding:5px 12px;
    display:flex;justify-content:space-between;align-items:center;
}
.nav-coming-badge{font-size:9px;letter-spacing:.06em;color:#2a2a35;text-transform:uppercase}

/* ── Compact record strip (sidebar) ── */
.record-mini{display:flex;gap:0;border:1px solid #1a1a20;border-radius:10px;overflow:hidden;margin:6px 12px 12px}
.rc-mini{flex:1;padding:.6rem .75rem;background:#0d0d12;border-right:1px solid #1a1a20;text-align:center}
.rc-mini:last-child{border-right:none}
.rcm-val{font-size:14px;font-weight:700;color:#e8e8ec}
.rcm-lbl{font-size:9px;color:#333340;letter-spacing:.05em;text-transform:uppercase;margin-top:1px}
.rcm-val.green{color:#22c55e}.rcm-val.red{color:#ef4444}

/* ── Hero ── */
.axiom-hero{
    background:linear-gradient(135deg,#0a0a0c 0%,#0d0d18 50%,#0a0a0c 100%);
    border-bottom:1px solid #1e1e28;
    padding:3rem 2rem 2.5rem;
    margin:-1.5rem -1rem 2rem;
    position:relative;overflow:hidden;
}
.axiom-hero::before{
    content:'';position:absolute;top:-60px;right:-60px;
    width:300px;height:300px;border-radius:50%;
    background:radial-gradient(circle,rgba(99,102,241,.08) 0%,transparent 70%);
}
.axiom-hero::after{
    content:'';position:absolute;bottom:-40px;left:20%;
    width:200px;height:200px;border-radius:50%;
    background:radial-gradient(circle,rgba(34,197,94,.05) 0%,transparent 70%);
}
.axiom-wordmark{font-size:13px;font-weight:700;letter-spacing:.2em;color:#6366f1;text-transform:uppercase;margin-bottom:8px}
.axiom-headline{font-size:42px;font-weight:800;letter-spacing:-1.5px;line-height:1.05;color:#e8e8ec;margin-bottom:10px}
.axiom-headline span{background:linear-gradient(135deg,#6366f1,#22c55e);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.axiom-sub{font-size:15px;color:#6b6b78;max-width:520px;line-height:1.6}

/* ── Full record strip (home) ── */
.record-strip{display:flex;gap:0;border:1px solid #1e1e28;border-radius:12px;overflow:hidden;margin-bottom:2rem}
.record-cell{flex:1;padding:1rem 1.25rem;background:#13131a;border-right:1px solid #1e1e28;text-align:center}
.record-cell:last-child{border-right:none}
.rc-val{font-size:22px;font-weight:700;color:#e8e8ec}
.rc-lbl{font-size:10px;color:#44444f;letter-spacing:.06em;text-transform:uppercase;margin-top:2px}
.rc-val.green{color:#22c55e}.rc-val.red{color:#ef4444}

/* ── Sport cards (home) ── */
.sport-card{background:#13131a;border:1px solid #1e1e28;border-radius:14px;padding:0;margin-bottom:16px;overflow:hidden}
.sport-card.nba{border-top:3px solid #6366f1}
.sport-card.mlb{border-top:3px solid #22c55e}
.sport-card.coming{border-top:3px solid #222228;opacity:.5}
.sport-header{display:flex;justify-content:space-between;align-items:center;padding:1.25rem 1.5rem 1rem}
.sport-name{font-size:18px;font-weight:700;color:#e8e8ec}
.sport-status-live{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#22c55e}
.sport-status-soon{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#333340}
.sport-divider{height:1px;background:#1e1e28;margin:0 1.5rem}
.best-bet-row{padding:1.25rem 1.5rem}
.bb-label{font-size:10px;color:#44444f;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px}
.bb-pick{font-size:16px;font-weight:700;color:#e8e8ec;margin-bottom:4px}
.bb-tip{font-size:11px;color:#44444f;margin-bottom:6px}
.bb-meta{font-size:12px;color:#6b6b78}
.bb-edge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700;background:#0d2a0d;color:#22c55e;border:1px solid #1a4a1a;margin-left:8px}
.bb-edge.blue{background:#0d0d2a;color:#6366f1;border-color:#1a1a4a}
.no-pick{font-size:13px;color:#44444f;font-style:italic;padding:1.25rem 1.5rem}
.sh{font-size:11px;font-weight:600;letter-spacing:.1em;color:#44444f;text-transform:uppercase;margin:2rem 0 1rem;padding-bottom:8px;border-bottom:1px solid #1e1e28}
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
NBA_DB = "nba.db"
MLB_DB = "mlb.db"

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
                 .strftime("%I:%M %p ET").lstrip("0")
    except Exception:
        return ""

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
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]

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
                "side":             side,
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
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]

def get_overall_record(db_path, table="bet_log"):
    df = load(db_path, f"SELECT result, profit_units FROM {table} WHERE result IN ('WIN','LOSS')")
    if df.empty:
        return 0, 0, 0.0
    wins  = (df["result"] == "WIN").sum()
    total = len(df)
    return int(wins), int(total - wins), float(df["profit_units"].sum())

# ── Pre-load record (shared by sidebar + home) ────────────────────────────────
nba_w, nba_l, nba_u = get_overall_record(NBA_DB, "bet_log")
mlb_w, mlb_l, mlb_u = get_overall_record(MLB_DB, "mlb_bet_log")
total_w = nba_w + mlb_w; total_l = nba_l + mlb_l; total_u = nba_u + mlb_u
win_pct = total_w / (total_w + total_l) if (total_w + total_l) > 0 else 0
uc = "green" if total_u >= 0 else "red"
wc = "green" if win_pct >= 0.55 else ("red" if win_pct < 0.50 else "")

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
<div style="padding:1.25rem 12px 1rem">
  <div style="font-size:11px;font-weight:700;letter-spacing:.2em;color:#6366f1;text-transform:uppercase;margin-bottom:4px">⚡ AXIOM</div>
  <div style="font-size:18px;font-weight:700;color:#e8e8ec;letter-spacing:-.3px">Edge</div>
  <div style="font-size:11px;color:#333340;margin-top:2px">AI-powered sports analytics</div>
</div>
<div style="height:1px;background:#1a1a20;margin:0 12px .5rem"></div>
""", unsafe_allow_html=True)

    # Home link
    _nav("🏠 Home", "home")

    # ── NBA ──
    st.markdown('<div class="nav-section" style="border-top:1px solid #1a1a20">🏀 NBA</div>', unsafe_allow_html=True)
    _nav("NBA Picks", "nba_picks")
    _nav("ROI Tracker", "nba_roi")
    _nav("Parlay Builder", "parlay")
    _nav("Player Research", "player")

    # ── MLB ──
    st.markdown('<div class="nav-section">⚾ MLB</div>', unsafe_allow_html=True)
    _nav("MLB Picks", "mlb_picks")
    _nav("ROI Tracker", "mlb_roi")

    # ── Coming soon ──
    st.markdown("""
<div style="height:1px;background:#1a1a20;margin:6px 12px 0"></div>
<div class="nav-section" style="border-top:none">🔜 Coming Soon</div>
<div class="nav-coming">
  <span>🏈 NFL</span><span class="nav-coming-badge">AUG 2026</span>
</div>
<div class="nav-coming">
  <span>🏒 NHL</span><span class="nav-coming-badge">OCT 2026</span>
</div>
""", unsafe_allow_html=True)

    # ── Compact season record ──
    st.markdown(f"""
<div style="height:1px;background:#1a1a20;margin:8px 12px 0"></div>
<div style="padding:8px 12px 4px;font-size:9px;font-weight:700;letter-spacing:.1em;color:#2a2a35;text-transform:uppercase">Season record</div>
<div class="record-mini">
  <div class="rc-mini"><div class="rcm-val {wc}">{win_pct:.1%}</div><div class="rcm-lbl">Win%</div></div>
  <div class="rc-mini"><div class="rcm-val">{total_w}–{total_l}</div><div class="rcm-lbl">W–L</div></div>
  <div class="rc-mini"><div class="rcm-val {uc}">{total_u:+.1f}u</div><div class="rcm-lbl">Units</div></div>
</div>
""", unsafe_allow_html=True)

# ── Main content routing ───────────────────────────────────────────────────────
page = st.session_state.page

if page == "home":
    today_str = date.today().strftime("%A, %B %d %Y")
    st.markdown(f"""
<div class="axiom-hero">
  <div class="axiom-wordmark">⚡ AXIOM Edge</div>
  <div class="axiom-headline">Data finds the <span>edge</span>.</div>
  <div class="axiom-sub">Machine learning models analyzing every game across every sport. Real probabilities. Real edge. No opinions.</div>
  <div style="margin-top:1.5rem;font-size:12px;color:#44444f">{today_str}</div>
</div>
""", unsafe_allow_html=True)

    # Full record strip
    st.markdown(f"""
<div class="record-strip">
  <div class="record-cell"><div class="rc-val {wc}">{win_pct:.1%}</div><div class="rc-lbl">Win rate</div></div>
  <div class="record-cell"><div class="rc-val">{total_w}W – {total_l}L</div><div class="rc-lbl">All sports record</div></div>
  <div class="record-cell"><div class="rc-val {uc}">{total_u:+.3f}</div><div class="rc-lbl">Units P&L</div></div>
  <div class="record-cell"><div class="rc-val">{total_w+total_l}</div><div class="rc-lbl">Total bets tracked</div></div>
</div>
""", unsafe_allow_html=True)

    # Sport cards
    today = date.today().isoformat()
    st.markdown("<div class='sh'>Today's best bets by sport</div>", unsafe_allow_html=True)

    # NBA card
    nba_preds  = load(NBA_DB, "SELECT * FROM predictions WHERE predict_date=? ORDER BY commence_time", params=(today,))
    nba_best   = get_best_bet(nba_preds) if not nba_preds.empty else None
    nba_val    = int(((nba_preds["home_value"] == 1) | (nba_preds["away_value"] == 1)).sum()) if not nba_preds.empty else 0
    nba_spread = load(NBA_DB, "SELECT * FROM spread_predictions WHERE predict_date=? ORDER BY commence_time", params=(today,))
    nba_ats    = get_best_ats(nba_spread) if not nba_spread.empty else None

    if nba_best:
        tip = fmt_tip(nba_best.get("commence_time", ""))
        ats_html = ""
        if nba_ats:
            ats_spread = f"{nba_ats['spread']:+.1f}" if nba_ats["spread"] is not None else ""
            ats_html = (
                f'<div style="border-top:1px solid #1a1a24;padding:.9rem 1.5rem">'
                f'<div class="bb-label">Best ATS pick</div>'
                f'<div class="bb-pick">{nba_ats["bet_team"]} {ats_spread}'
                f'&nbsp;{fmt(nba_ats["price"])}'
                f'<span class="bb-edge blue">{nba_ats["edge"]:+.1%} edge</span></div>'
                f'<div class="bb-meta">P(cover): {nba_ats["cover_prob"]:.1%} &nbsp;·&nbsp; '
                f'Pred margin: {nba_ats["pred_home_margin"]:+.1f} pts</div>'
                f'</div>'
            )
        nba_body = f"""
<div class="sport-divider"></div>
<div class="best-bet-row">
  <div class="bb-label">Best moneyline</div>
  <div class="bb-pick">{nba_best['bet_team']} &nbsp;{fmt(nba_best['price'])}<span class="bb-edge blue">{nba_best['edge']:+.1%} edge</span></div>
  <div class="bb-tip">{tip}</div>
  <div class="bb-meta">Model: {nba_best['prob']:.1%} &nbsp;·&nbsp; Kelly: {nba_best['kelly']*100:.1f}%</div>
</div>{ats_html}"""
    else:
        nba_body = f'<div class="no-pick">{"No predictions yet — run python predict.py" if nba_preds.empty else "No strong edge found today"}</div>'

    st.markdown(f"""
<div class="sport-card nba">
  <div class="sport-header">
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:28px">🏀</span>
      <div><div class="sport-name">NBA</div>
      <div style="font-size:12px;color:#6b6b78">{len(nba_preds)} games · {nba_val} value bets</div></div>
    </div>
    <div class="sport-status-live">● LIVE</div>
  </div>
  {nba_body}
</div>
""", unsafe_allow_html=True)

    # MLB card
    mlb_preds = load(MLB_DB, "SELECT * FROM mlb_predictions WHERE predict_date=? ORDER BY commence_time", params=(today,))
    mlb_best  = get_best_bet(mlb_preds) if not mlb_preds.empty else None
    mlb_val   = int(((mlb_preds["home_value"] == 1) | (mlb_preds["away_value"] == 1)).sum()) if not mlb_preds.empty else 0

    if mlb_best:
        tip = fmt_tip(mlb_best.get("commence_time", ""))
        mlb_body = f"""
<div class="sport-divider"></div>
<div class="best-bet-row">
  <div class="bb-label">Best bet today</div>
  <div class="bb-pick">{mlb_best['bet_team']} &nbsp;{fmt(mlb_best['price'])}<span class="bb-edge">{mlb_best['edge']:+.1%} edge</span></div>
  <div class="bb-tip">{tip}</div>
  <div class="bb-meta">Model: {mlb_best['prob']:.1%} &nbsp;·&nbsp; Kelly: {mlb_best['kelly']*100:.1f}%</div>
</div>"""
    else:
        mlb_body = f'<div class="no-pick">{"No predictions yet — run python mlb_predict.py" if mlb_preds.empty else "No strong edge found today"}</div>'

    st.markdown(f"""
<div class="sport-card mlb">
  <div class="sport-header">
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:28px">⚾</span>
      <div><div class="sport-name">MLB</div>
      <div style="font-size:12px;color:#6b6b78">{len(mlb_preds)} games · {mlb_val} value bets</div></div>
    </div>
    <div class="sport-status-live">● LIVE</div>
  </div>
  {mlb_body}
</div>
""", unsafe_allow_html=True)

    # Coming soon
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
<div class="sport-card coming">
  <div class="sport-header">
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:28px">🏈</span>
      <div><div class="sport-name">NFL</div></div>
    </div>
    <div class="sport-status-soon">Coming soon</div>
  </div>
  <div class="no-pick">Model in development. Launching August 2026.</div>
</div>""", unsafe_allow_html=True)
    with col2:
        st.markdown("""
<div class="sport-card coming">
  <div class="sport-header">
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:28px">🏒</span>
      <div><div class="sport-name">NHL</div></div>
    </div>
    <div class="sport-status-soon">Coming soon</div>
  </div>
  <div class="no-pick">Model in development. Launching October 2026.</div>
</div>""", unsafe_allow_html=True)

    st.markdown("""
<div style="text-align:center;padding:2rem 0 1rem;color:#2a2a35;font-size:13px">
  Select a sport from the sidebar to view full picks and ROI tracking
</div>
""", unsafe_allow_html=True)

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
