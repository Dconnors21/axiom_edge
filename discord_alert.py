"""
discord_alert.py — Sends today's AXIOM Edge best bets to Discord as rich embeds.

Called automatically by run_daily.py at the end of the morning pipeline.
Run manually any time: python discord_alert.py

Setup: add your webhook URL to .env → DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
"""

import json
import sqlite3
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path
import pandas as pd

# ── Constants ─────────────────────────────────────────────────────────────────
NBA_DB       = Path("nba.db")
MLB_DB       = Path("mlb.db")
NBA_MIN_EDGE = 0.03
MLB_MIN_EDGE = 0.03

NBA_COLOR  = int("6366f1", 16)   # indigo  #6366f1
MLB_COLOR  = int("22c55e", 16)   # green   #22c55e
SKIP_COLOR = int("2a2a35", 16)   # dark gray (no pick)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_env() -> dict:
    """Parse .env for DISCORD_WEBHOOK_URL without requiring python-dotenv."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return {}
    result = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result

def _load(db: Path, query: str, params=None) -> pd.DataFrame:
    if not db.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(db)
    try:
        df = pd.read_sql(query, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

def _fmt_price(price) -> str:
    try:
        p = int(price)
        return f"+{p}" if p > 0 else str(p)
    except Exception:
        return "N/A"

def _fmt_tip(commence_time) -> str:
    try:
        return pd.to_datetime(commence_time, utc=True) \
                 .tz_convert("America/New_York") \
                 .strftime("%I:%M %p ET").lstrip("0")
    except Exception:
        return str(commence_time)

def _get_best(preds: pd.DataFrame, min_edge: float):
    if preds.empty:
        return None
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
                "bet_team":      bet_team,
                "edge":          edge,
                "prob":          prob,
                "fair_prob":     float(game.get(f"{side}_fair_prob", 0.5)),
                "price":         price,
                "kelly":         kelly,
                "commence_time": game.get("commence_time", ""),
                "bookmaker":     str(game.get("bookmaker", "")).upper(),
                "home_team":     game["home_team"],
                "away_team":     game["away_team"],
                "home_pitcher":  game.get("home_pitcher"),
                "away_pitcher":  game.get("away_pitcher"),
                "home_era":      game.get("home_era"),
                "away_era":      game.get("away_era"),
            })
    if not candidates:
        return None
    # Prefer ladder-eligible (price <= -250 or <= +250 favorite), then highest edge
    candidates.sort(key=lambda x: (
        int(float(x["price"]) <= 250) if x["price"] else 0,
        x["edge"]
    ), reverse=True)
    return candidates[0]


# ── Embed builders ────────────────────────────────────────────────────────────

def _get_best_ats(spread_preds: pd.DataFrame, min_edge: float):
    if spread_preds.empty:
        return None
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
                "spread":           g.get(f"{side}_point"),
                "pred_home_margin": float(g.get("pred_home_margin", 0)),
                "cover_prob":       prob,
                "edge":             edge,
                "kelly":            kelly,
                "price":            price,
                "commence_time":    g.get("commence_time", ""),
                "bookmaker":        str(g.get("bookmaker", "")),
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _get_best_prop(props_preds: pd.DataFrame, min_edge: float):
    if props_preds.empty:
        return None
    candidates = []
    for _, g in props_preds.iterrows():
        for side in ["over", "under"]:
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005 or price is None:
                continue
            candidates.append({
                "side":         side,
                "player_name":  g["player_name"],
                "home_team":    g["home_team"],
                "away_team":    g["away_team"],
                "bookmaker":    str(g.get("bookmaker", "")).upper(),
                "line":         g.get("line"),
                "pred_pts":     float(g.get("pred_pts", 0)),
                "ou_prob":      prob,
                "edge":         edge,
                "kelly":        kelly,
                "price":        price,
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _get_best_total(totals_preds: pd.DataFrame, min_edge: float):
    if totals_preds.empty:
        return None
    candidates = []
    for _, g in totals_preds.iterrows():
        for side in ["over", "under"]:
            edge  = float(g.get(f"{side}_edge", 0))
            prob  = float(g.get(f"{side}_prob", 0))
            kelly = float(g.get(f"{side}_kelly", 0))
            price = g.get(f"{side}_price")
            val   = int(g.get(f"{side}_value", 0))
            if val != 1 or edge < min_edge or kelly < 0.005 or price is None:
                continue
            candidates.append({
                "side":       side,
                "home_team":  g["home_team"],
                "away_team":  g["away_team"],
                "commence_time": g.get("commence_time", ""),
                "bookmaker":  g.get("bookmaker", ""),
                "total_line": g.get("total_line"),
                "pred_total": float(g.get("pred_total", 0)),
                "ou_prob":    prob,
                "edge":       edge,
                "kelly":      kelly,
                "price":      price,
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x["edge"], reverse=True)[0]


def _build_nba_embed(today: str) -> dict:
    preds = _load(NBA_DB,
                  "SELECT * FROM predictions WHERE predict_date=? ORDER BY commence_time",
                  params=(today,))
    spread_preds = _load(NBA_DB,
                         "SELECT * FROM spread_predictions WHERE predict_date=? ORDER BY commence_time",
                         params=(today,))
    totals_preds = _load(NBA_DB,
                         "SELECT * FROM totals_predictions WHERE predict_date=? ORDER BY commence_time",
                         params=(today,))
    props_preds  = _load(NBA_DB,
                         "SELECT * FROM props_predictions WHERE predict_date=? ORDER BY over_edge DESC",
                         params=(today,))
    best         = _get_best(preds, NBA_MIN_EDGE)
    ats_best     = _get_best_ats(spread_preds, NBA_MIN_EDGE)
    totals_best  = _get_best_total(totals_preds, NBA_MIN_EDGE)
    props_best   = _get_best_prop(props_preds, 0.08)
    val_count = int(((preds["home_value"] == 1) | (preds["away_value"] == 1)).sum()) \
                if not preds.empty else 0
    game_count = len(preds)

    if best:
        tip = _fmt_tip(best["commence_time"])
        try:
            ladder = "Yes 🪜" if float(best["price"]) <= 250 else "No"
        except Exception:
            ladder = "—"

        fields = [
            {"name": "🎯 Pick",         "value": f"**{best['bet_team']}** `{_fmt_price(best['price'])}`", "inline": True},
            {"name": "⏰ Tip (ET)",     "value": tip or "—",                              "inline": True},
            {"name": "📚 Book",         "value": best["bookmaker"] or "—",                "inline": True},
            {"name": "📈 Edge",         "value": f"**{best['edge']:+.1%}**",              "inline": True},
            {"name": "🤖 Model Prob",   "value": f"{best['prob']:.1%}",                   "inline": True},
            {"name": "📊 Book Implied", "value": f"{best['fair_prob']:.1%}",              "inline": True},
            {"name": "💰 Kelly Stake",  "value": f"{best['kelly']*100:.1f}% of bankroll", "inline": True},
            {"name": "🪜 Ladder",       "value": ladder,                                  "inline": True},
            {"name": "🏟️ Matchup",     "value": f"{best['away_team']} @ {best['home_team']}", "inline": False},
        ]
        if ats_best:
            spr = f"{ats_best['spread']:+.1f}" if ats_best["spread"] is not None else ""
            fields.append({
                "name": "📐 ATS Pick",
                "value": (
                    f"**{ats_best['bet_team']} {spr}** `{_fmt_price(ats_best['price'])}`  "
                    f"P(cover): {ats_best['cover_prob']:.1%}  "
                    f"Edge: **{ats_best['edge']:+.1%}**  "
                    f"Pred margin: {ats_best['pred_home_margin']:+.1f} pts"
                ),
                "inline": False,
            })
        if totals_best:
            side_label = "OVER" if totals_best["side"] == "over" else "UNDER"
            line_str   = f"{totals_best['total_line']:.1f}" if totals_best["total_line"] is not None else "N/A"
            fields.append({
                "name": "🎯 Totals Pick",
                "value": (
                    f"**{side_label} {line_str}** `{_fmt_price(totals_best['price'])}`  "
                    f"P(hit): {totals_best['ou_prob']:.1%}  "
                    f"Edge: **{totals_best['edge']:+.1%}**  "
                    f"Pred total: {totals_best['pred_total']:.1f} pts"
                ),
                "inline": False,
            })
        if props_best:
            side_label = "OVER" if props_best["side"] == "over" else "UNDER"
            away = props_best["away_team"].split()[-1]
            home = props_best["home_team"].split()[-1]
            fields.append({
                "name": "🎲 Props Pick",
                "value": (
                    f"**{props_best['player_name']} {side_label} {props_best['line']}** `{_fmt_price(props_best['price'])}`  "
                    f"({away} @ {home})  "
                    f"P(hit): {props_best['ou_prob']:.1%}  "
                    f"Edge: **{props_best['edge']:+.1%}**  "
                    f"Pred: {props_best['pred_pts']:.1f} pts"
                ),
                "inline": False,
            })
        return {
            "title":       "🏀 NBA — Best Bet of the Day",
            "color":       NBA_COLOR,
            "description": f"{game_count} games today · **{val_count} value bet{'s' if val_count != 1 else ''} found**",
            "fields":      fields,
            "footer":      {"text": f"AXIOM Edge · {today}"},
        }
    else:
        msg = ("No NBA predictions yet — run `python odds.py && python predict.py`."
               if preds.empty else
               f"{game_count} games analysed — no strong edge found today. Skip NBA.")
        return {
            "title":       "🏀 NBA — No Bet Today",
            "color":       SKIP_COLOR,
            "description": msg,
            "footer":      {"text": f"AXIOM Edge · {today}"},
        }


def _build_mlb_embed(today: str) -> dict:
    preds = _load(MLB_DB,
                  "SELECT * FROM mlb_predictions WHERE predict_date=? ORDER BY commence_time",
                  params=(today,))
    spread_preds = _load(MLB_DB,
                         "SELECT * FROM mlb_spread_predictions WHERE predict_date=? ORDER BY commence_time",
                         params=(today,))
    totals_preds = _load(MLB_DB,
                         "SELECT * FROM mlb_totals_predictions WHERE predict_date=? ORDER BY commence_time",
                         params=(today,))
    best         = _get_best(preds, MLB_MIN_EDGE)
    rl_best      = _get_best_ats(spread_preds, MLB_MIN_EDGE)
    totals_best  = _get_best_total(totals_preds, MLB_MIN_EDGE)
    val_count = int(((preds["home_value"] == 1) | (preds["away_value"] == 1)).sum()) \
                if not preds.empty else 0
    game_count = len(preds)

    if best:
        tip = _fmt_tip(best["commence_time"])
        try:
            ladder = "Yes 🪜" if float(best["price"]) <= 250 else "No"
        except Exception:
            ladder = "—"

        fields = [
            {"name": "🎯 Pick",         "value": f"**{best['bet_team']}** `{_fmt_price(best['price'])}`", "inline": True},
            {"name": "⏰ Tip (ET)",     "value": tip or "—",                              "inline": True},
            {"name": "📚 Book",         "value": best["bookmaker"] or "—",                "inline": True},
            {"name": "📈 Edge",         "value": f"**{best['edge']:+.1%}**",              "inline": True},
            {"name": "🤖 Model Prob",   "value": f"{best['prob']:.1%}",                   "inline": True},
            {"name": "📊 Book Implied", "value": f"{best['fair_prob']:.1%}",              "inline": True},
            {"name": "💰 Kelly Stake",  "value": f"{best['kelly']*100:.1f}% of bankroll", "inline": True},
            {"name": "🪜 Ladder",       "value": ladder,                                  "inline": True},
            {"name": "🏟️ Matchup",     "value": f"{best['away_team']} @ {best['home_team']}", "inline": False},
        ]

        # Pitcher matchup (MLB-specific)
        hp = best.get("home_pitcher"); ap = best.get("away_pitcher")
        he = best.get("home_era");     ae = best.get("away_era")
        if hp and ap:
            h_str = f"{hp} ({float(he):.2f} ERA)" if he else hp
            a_str = f"{ap} ({float(ae):.2f} ERA)" if ae else ap
            fields.append({"name": "⚾ Pitchers", "value": f"{a_str} vs {h_str}", "inline": False})

        if rl_best:
            spr = f"{rl_best['spread']:+.1f}" if rl_best["spread"] is not None else ""
            fields.append({
                "name": "📐 Run Line Pick",
                "value": (
                    f"**{rl_best['bet_team']} {spr}** `{_fmt_price(rl_best['price'])}`  "
                    f"P(cover): {rl_best['cover_prob']:.1%}  "
                    f"Edge: **{rl_best['edge']:+.1%}**  "
                    f"Pred margin: {rl_best['pred_home_margin']:+.1f}r"
                ),
                "inline": False,
            })
        if totals_best:
            side_label = "OVER" if totals_best["side"] == "over" else "UNDER"
            line_str   = f"{totals_best['total_line']:.1f}" if totals_best["total_line"] is not None else "N/A"
            fields.append({
                "name": "🎯 Totals Pick",
                "value": (
                    f"**{side_label} {line_str}** `{_fmt_price(totals_best['price'])}`  "
                    f"P(hit): {totals_best['ou_prob']:.1%}  "
                    f"Edge: **{totals_best['edge']:+.1%}**  "
                    f"Pred total: {totals_best['pred_total']:.1f}r"
                ),
                "inline": False,
            })

        return {
            "title":       "⚾ MLB — Best Bet of the Day",
            "color":       MLB_COLOR,
            "description": f"{game_count} games today · **{val_count} value bet{'s' if val_count != 1 else ''} found**",
            "fields":      fields,
            "footer":      {"text": f"AXIOM Edge · {today}"},
        }
    else:
        msg = ("No MLB predictions yet — run `python mlb_pitchers.py && python mlb_odds.py && python mlb_predict.py`."
               if preds.empty else
               f"{game_count} games analysed — no strong edge found today. Skip MLB.")
        return {
            "title":       "⚾ MLB — No Bet Today",
            "color":       SKIP_COLOR,
            "description": msg,
            "footer":      {"text": f"AXIOM Edge · {today}"},
        }


# ── Send ──────────────────────────────────────────────────────────────────────

def send_alert() -> bool:
    env         = _load_env()
    webhook_url = env.get("DISCORD_WEBHOOK_URL", "").strip()

    if not webhook_url or webhook_url == "YOUR_WEBHOOK_URL_HERE":
        print("  ⚠  No Discord webhook URL configured.")
        print("     Edit .env and set: DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...")
        return False

    today     = date.today().isoformat()
    date_nice = date.today().strftime("%B %d, %Y")

    payload = {
        "username":   "AXIOM Edge",
        "content":    f"**⚡ AXIOM Edge  ·  Daily Picks  ·  {date_nice}**",
        "embeds":     [_build_nba_embed(today), _build_mlb_embed(today)],
    }

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"  ✓ Discord alert sent (HTTP {resp.status})")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  ✗ Discord returned HTTP {e.code}: {body[:300]}")
        return False
    except Exception as e:
        print(f"  ✗ Discord alert failed: {e}")
        return False


if __name__ == "__main__":
    print("── AXIOM Edge Discord Alert ──────────────────────────────")
    send_alert()
