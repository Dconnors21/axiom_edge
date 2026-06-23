# ── run_daily.py ──────────────────────────────────────────────────────────────
# Master automation script — runs the full daily pipeline for NBA + MLB.
#
# Usage:
#   python run_daily.py --morning   pull data + generate picks + send Discord alert
#   python run_daily.py --evening   fetch results + update ROI trackers (runs at 2 AM)
#   python run_daily.py --discord   re-send today's Discord alert only
#
# Windows Task Scheduler: run setup_tasks.ps1 (once, as Administrator) to
# register the 8:00 AM morning and 11:30 PM evening tasks automatically.

import subprocess
import argparse
import sys
import os
import time
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / f"daily_{date.today().isoformat()}.log"

# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str):
    ts   = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_DIR.mkdir(exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(script: str, label: str, args: list = None) -> bool:
    log(f"Starting {label}...")
    start  = time.time()
    env    = {**os.environ, "PYTHONUTF8": "1"}
    cmd    = [sys.executable, script] + (args or [])
    result = subprocess.run(
        cmd,
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(Path(__file__).parent), env=env
    )
    elapsed = time.time() - start

    if result.returncode == 0:
        log(f"✓ {label} completed in {elapsed:.1f}s")
        for line in result.stdout.splitlines():
            if any(kw in line for kw in ["rows", "AUC", "accuracy", "VALUE BET",
                                          "found", "Done", "saved", "Error", "FAILED",
                                          "transactions", "Saving", "Updated", "picks",
                                          "predictions", "games", "edge"]):
                log(f"  → {line.strip()}")
    else:
        log(f"✗ {label} FAILED after {elapsed:.1f}s")
        if result.stderr:
            log(f"  Error: {result.stderr[-500:]}")
    return result.returncode == 0

def _clear_stale_predictions(db_path: str, table: str, today: str):
    try:
        conn    = sqlite3.connect(db_path)
        deleted = conn.execute(
            f"DELETE FROM {table} WHERE predict_date = ?", (today,)
        ).rowcount
        conn.commit()
        conn.close()
        if deleted:
            log(f"  Cleared {deleted} stale {table} rows for {today}")
    except Exception as e:
        log(f"  Warning: could not clear stale predictions — {e}")

def _should_retrain(model_file: str = "model.pkl") -> bool:
    path = Path(model_file)
    if not path.exists():
        return True
    age_days  = (time.time() - path.stat().st_mtime) / 86400
    is_monday = date.today().weekday() == 0
    return is_monday or age_days > 7


_STAMP_DIR = Path("logs") / "stamps"

def _already_ran_today(pipeline: str) -> bool:
    """Returns True if this pipeline already completed successfully today."""
    _STAMP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _STAMP_DIR / f"{pipeline}_{date.today().isoformat()}.stamp"
    return stamp.exists()

def _mark_ran_today(pipeline: str):
    """Write a stamp file so we know this pipeline ran today."""
    _STAMP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _STAMP_DIR / f"{pipeline}_{date.today().isoformat()}.stamp"
    stamp.write_text(datetime.now().isoformat())


# League seasons as (month, day) windows, inclusive. NBA/NHL wrap the new year
# (Oct -> mid-Jun, covering playoffs); MLB runs Mar -> early Nov (covering the WS).
# Used to skip the dead offseason so we don't burn data pulls / Odds API credits
# fetching slates that don't exist. Generous on the playoff end to avoid cutting
# off Finals/Cup/WS games.
_SEASON = {
    "nba": ((10, 1), (6, 20)),
    "nhl": ((10, 1), (6, 20)),
    "mlb": ((3, 15), (11, 5)),
}


def _in_season(league: str, today: date = None) -> bool:
    today = today or date.today()
    (sm, sd), (em, ed) = _SEASON[league]
    cur, start, end = (today.month, today.day), (sm, sd), (em, ed)
    if start <= end:           # within one calendar year (MLB)
        return start <= cur <= end
    return cur >= start or cur <= end   # wraps year-end (NBA/NHL)


# ── Pipelines ─────────────────────────────────────────────────────────────────

def morning_pipeline():
    today = date.today().isoformat()
    if _already_ran_today("morning"):
        log(f"Morning pipeline already ran today ({today}) — skipping.")
        return True
    log("=" * 60)
    log(f"AXIOM EDGE — MORNING PIPELINE — {today}")
    log("=" * 60)

    # ── NBA ──────────────────────────────────────────────────────────────────
    log("─── NBA ───────────────────────────────────────────────────")

    if _in_season("nba"):
        run("collect.py",       "NBA: data collection")
        run("collect_props.py", "NBA: player game logs")
        run("features.py",      "NBA: feature engineering")

        if _should_retrain("model.pkl"):
            log("Retraining NBA model (weekly schedule or missing)...")
            run("train.py", "NBA: model training")
        else:
            age = (time.time() - Path("model.pkl").stat().st_mtime) / 86400
            log(f"Skipping NBA retrain — model is {age:.1f} days old")

        odds_ok = run("odds.py", "NBA: odds fetching")
    else:
        log("NBA out of season — skipping data pull and picks")
        odds_ok = False
    if odds_ok:
        _clear_stale_predictions("nba.db", "predictions", today)
        _clear_stale_predictions("nba.db", "spread_predictions", today)
        _clear_stale_predictions("nba.db", "totals_predictions", today)
        _clear_stale_predictions("nba.db", "props_predictions",     today)
        _clear_stale_predictions("nba.db", "props_reb_predictions", today)
        _clear_stale_predictions("nba.db", "props_ast_predictions",    today)
        _clear_stale_predictions("nba.db", "props_threes_predictions", today)
        _clear_stale_predictions("nba.db", "props_stl_predictions",   today)
        _clear_stale_predictions("nba.db", "props_blk_predictions",   today)
        # Pull injuries/inactives BEFORE predictions so the team model gets a
        # serve-time nudge and props skip players ruled Out. --no-manual keeps
        # the automated pipeline from ever blocking on interactive entry.
        run("lineup_injury.py",  "NBA: injury/inactive report", ["--no-manual"])
        run("predict.py",        "NBA: generating moneyline picks")
        run("spread_predict.py", "NBA: generating ATS picks")
        run("totals_predict.py", "NBA: generating totals picks")
        run("props_odds.py",     "NBA: fetching player props lines (pts + reb + ast + 3PM + stl + blk)")
        run("props_predict.py",  "NBA: generating player points picks")
        if _should_retrain("props_reb_model.pkl"):
            log("Retraining rebounds model (weekly schedule or missing)...")
            run("train_props_reb.py", "NBA: training rebounds model")
        else:
            age = (time.time() - Path("props_reb_model.pkl").stat().st_mtime) / 86400
            log(f"Skipping reb retrain — model is {age:.1f} days old")
        run("props_predict_reb.py", "NBA: generating player rebounds picks")
        if _should_retrain("props_ast_model.pkl"):
            log("Retraining assists model (weekly schedule or missing)...")
            run("train_props_ast.py", "NBA: training assists model")
        else:
            age = (time.time() - Path("props_ast_model.pkl").stat().st_mtime) / 86400
            log(f"Skipping ast retrain — model is {age:.1f} days old")
        run("props_predict_ast.py", "NBA: generating player assists picks")
        if _should_retrain("props_threes_model.pkl"):
            log("Retraining 3-pointers model (weekly schedule or missing)...")
            run("train_props_threes.py", "NBA: training 3-pointers model")
        else:
            age = (time.time() - Path("props_threes_model.pkl").stat().st_mtime) / 86400
            log(f"Skipping 3PM retrain — model is {age:.1f} days old")
        run("props_predict_threes.py", "NBA: generating player 3-pointers picks")
        if _should_retrain("props_stl_model.pkl"):
            log("Retraining steals model (weekly schedule or missing)...")
            run("train_props_stl.py", "NBA: training steals model")
        else:
            age = (time.time() - Path("props_stl_model.pkl").stat().st_mtime) / 86400
            log(f"Skipping stl retrain — model is {age:.1f} days old")
        run("props_predict_stl.py", "NBA: generating player steals picks")
        if _should_retrain("props_blk_model.pkl"):
            log("Retraining blocks model (weekly schedule or missing)...")
            run("train_props_blk.py", "NBA: training blocks model")
        else:
            age = (time.time() - Path("props_blk_model.pkl").stat().st_mtime) / 86400
            log(f"Skipping blk retrain — model is {age:.1f} days old")
        run("props_predict_blk.py", "NBA: generating player blocks picks")
    else:
        log("NBA odds fetch failed — skipping NBA predictions today")

    # ── MLB ──────────────────────────────────────────────────────────────────
    log("─── MLB ───────────────────────────────────────────────────")

    if _in_season("mlb"):
        run("mlb_collect.py",   "MLB: data collection")
        run("mlb_features.py",  "MLB: feature engineering")

        if _should_retrain("mlb_model.pkl"):
            log("Retraining MLB model (weekly schedule or missing)...")
            run("mlb_train.py", "MLB: model training")
        else:
            age = (time.time() - Path("mlb_model.pkl").stat().st_mtime) / 86400
            log(f"Skipping MLB retrain — model is {age:.1f} days old")

        mlb_odds_ok = run("mlb_pitchers.py", "MLB: pitcher data")
        mlb_odds_ok = run("mlb_odds.py",     "MLB: odds fetching") and mlb_odds_ok
    else:
        log("MLB out of season — skipping data pull and picks")
        mlb_odds_ok = False
    if mlb_odds_ok:
        _clear_stale_predictions("mlb.db", "mlb_predictions", today)
        _clear_stale_predictions("mlb.db", "mlb_spread_predictions", today)
        _clear_stale_predictions("mlb.db", "mlb_totals_predictions", today)
        run("mlb_predict.py",        "MLB: generating moneyline picks")
        run("mlb_spread_predict.py", "MLB: generating run line picks")
        run("mlb_totals_predict.py", "MLB: generating totals picks")
    else:
        log("MLB odds/pitcher fetch failed — skipping MLB predictions today")

    # ── MLB Player Props ──────────────────────────────────────────────────────
    log("─── MLB Player Props ──────────────────────────────────────")

    if _in_season("mlb"):
        run("mlb_props_collect.py",      "MLB Props: collecting player game logs")
        # Fill opponent on freshly pulled logs (date + team -> mlb_games). Idempotent.
        run("mlb_backfill_opponents.py", "MLB Props: backfilling opponents")

        if _should_retrain("mlb_k_model.pkl"):
            log("Retraining MLB props models (weekly schedule or missing)...")
            run("mlb_props_train.py", "MLB Props: model training (K's, hits, TB)")
        else:
            age = (time.time() - Path("mlb_k_model.pkl").stat().st_mtime) / 86400
            log(f"Skipping MLB props retrain — models are {age:.1f} days old")

        mlb_props_odds_ok = run("mlb_props_odds.py", "MLB Props: fetching prop odds (K's, hits, TB)")
    else:
        log("MLB out of season — skipping player props")
        mlb_props_odds_ok = False
    if mlb_props_odds_ok:
        _clear_stale_predictions("mlb.db", "mlb_props_predictions_k",    today)
        _clear_stale_predictions("mlb.db", "mlb_props_predictions_hits", today)
        _clear_stale_predictions("mlb.db", "mlb_props_predictions_tb",   today)
        run("mlb_props_predict.py", "MLB Props: generating player prop picks")
    else:
        log("MLB props odds fetch failed — skipping prop predictions today")

    # ── NHL ──────────────────────────────────────────────────────────────────
    log("─── NHL ───────────────────────────────────────────────────")

    if _in_season("nhl"):
        run("nhl_collect.py",  "NHL: data collection")
        run("nhl_features.py", "NHL: feature engineering")

        if _should_retrain("nhl_model.pkl"):
            log("Retraining NHL moneyline model (weekly schedule or missing)...")
            run("nhl_train.py",          "NHL: moneyline model training")
            run("nhl_train_spread.py",   "NHL: puck line model training")
            run("nhl_train_totals.py",   "NHL: totals model training")
        else:
            age = (time.time() - Path("nhl_model.pkl").stat().st_mtime) / 86400
            log(f"Skipping NHL retrain — model is {age:.1f} days old")

        nhl_odds_ok = run("nhl_odds.py", "NHL: odds fetching")
    else:
        log("NHL out of season — skipping data pull and picks")
        nhl_odds_ok = False
    if nhl_odds_ok:
        _clear_stale_predictions("nhl.db", "nhl_predictions",        today)
        _clear_stale_predictions("nhl.db", "nhl_spread_predictions",  today)
        _clear_stale_predictions("nhl.db", "nhl_totals_predictions",  today)
        run("nhl_predict.py",        "NHL: generating moneyline picks")
        run("nhl_spread_predict.py", "NHL: generating puck line picks")
        run("nhl_totals_predict.py", "NHL: generating totals picks")
    else:
        log("NHL odds fetch failed — skipping NHL predictions today")

    # ── Discord alert ─────────────────────────────────────────────────────────
    log("─── Discord ────────────────────────────────────────────────")
    try:
        from discord_alert import send_alert
        send_alert()
    except Exception as e:
        log(f"  Discord alert error: {e}")

    # ── Web-push edge alert (eligible subscribers only) ────────────────────────
    run("push_notify.py", "Push: edge alerts")

    _mark_ran_today("morning")
    log("=" * 60)
    log("Morning pipeline complete — check dashboard: streamlit run Axiom_Edge.py")
    log("=" * 60)
    return True


def _unresolved_dates(db, table, null_col, date_col="predict_date", lookback_days=14):
    """Distinct predict_dates within the lookback window that still have unresolved
    rows (null_col IS NULL). Lets the evening sweep catch games that were missed on
    prior runs (postponements, skipped evenings) rather than only today/yesterday."""
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    try:
        conn = sqlite3.connect(db)
        try:
            rows = conn.execute(
                f"SELECT DISTINCT {date_col} FROM {table} "
                f"WHERE {null_col} IS NULL AND {date_col} >= ? ORDER BY {date_col}",
                (cutoff,)
            ).fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def evening_pipeline():
    today = date.today().isoformat()
    if _already_ran_today("evening"):
        log(f"Evening pipeline already ran today ({today}) — skipping.")
        return
    log("=" * 60)
    log(f"AXIOM EDGE — EVENING PIPELINE — {today}")
    log("=" * 60)

    # ── NBA results ───────────────────────────────────────────────────────────
    log("─── NBA results ────────────────────────────────────────────")
    nba_dates = _unresolved_dates("nba.db", "predictions", "actual_home_win")
    if nba_dates:
        log(f"Sweeping {len(nba_dates)} unresolved NBA date(s): {', '.join(nba_dates)}")
        for d in nba_dates:
            log(f"Fetching NBA results for {d}...")
            subprocess.run(
                [sys.executable, "results_fetcher.py", "--date", d],
                cwd=str(Path(__file__).parent)
            )
            # Pull player logs for that date, then resolve props (all stats)
            log(f"Resolving player props for {d}...")
            subprocess.run(
                [sys.executable, "collect_props.py", "--date", d],
                cwd=str(Path(__file__).parent)
            )
            subprocess.run(
                [sys.executable, "props_results_fetcher.py", "--date", d, "--stat", "all"],
                cwd=str(Path(__file__).parent)
            )
    else:
        log("No unresolved NBA predictions found (last 14 days)")

    # ── MLB results ───────────────────────────────────────────────────────────
    log("─── MLB results ────────────────────────────────────────────")
    try:
        mlb_dates = _unresolved_dates("mlb.db", "mlb_predictions", "actual_home_win")
        if mlb_dates:
            log(f"Sweeping {len(mlb_dates)} unresolved MLB date(s): {', '.join(mlb_dates)}")
            for d in mlb_dates:
                log(f"Fetching MLB results for {d}...")
                subprocess.run(
                    [sys.executable, "mlb_results_fetcher.py", "--date", d],
                    cwd=str(Path(__file__).parent)
                )
        else:
            log("No unresolved MLB predictions found (last 14 days)")
    except Exception as e:
        log(f"MLB results check failed: {e}")

    # ── MLB Props results ─────────────────────────────────────────────────────
    log("─── MLB props results ──────────────────────────────────────")
    try:
        mlb_props_dates = _unresolved_dates("mlb.db", "mlb_props_predictions_k", "actual_val")
        if mlb_props_dates:
            log(f"Sweeping {len(mlb_props_dates)} unresolved MLB prop date(s): {', '.join(mlb_props_dates)}")
            for d in mlb_props_dates:
                log(f"Fetching MLB prop results for {d}...")
                subprocess.run(
                    [sys.executable, "mlb_props_results_fetcher.py", "--date", d],
                    cwd=str(Path(__file__).parent)
                )
        else:
            log("No unresolved MLB prop predictions found (last 14 days)")
        # Reliable local backfill of actual_val from the game logs, so the props
        # models stay self-validating regardless of the API fetcher above.
        run("mlb_props_grade.py", "MLB props: grading from game logs")
    except Exception as e:
        log(f"MLB props results check failed: {e}")

    # ── NHL results ───────────────────────────────────────────────────────────
    log("─── NHL results ────────────────────────────────────────────")
    try:
        nhl_dates = _unresolved_dates("nhl.db", "nhl_predictions", "actual_home_win")
        if nhl_dates:
            log(f"Sweeping {len(nhl_dates)} unresolved NHL date(s): {', '.join(nhl_dates)}")
            for d in nhl_dates:
                log(f"Fetching NHL results for {d}...")
                subprocess.run(
                    [sys.executable, "nhl_results_fetcher.py", "--date", d],
                    cwd=str(Path(__file__).parent)
                )
        else:
            log("No unresolved NHL predictions found (last 14 days)")
    except Exception as e:
        log(f"NHL results check failed: {e}")

    _mark_ran_today("evening")
    log("=" * 60)
    log("Evening pipeline complete — ROI tracker updated")
    log("=" * 60)


def afternoon_pipeline():
    today = date.today().isoformat()
    log("=" * 60)
    log(f"AXIOM EDGE — AFTERNOON PIPELINE — {today}")
    log("=" * 60)
    log("Fetching closing odds for CLV tracking (~4 PM)...")
    run("fetch_closing_odds.py", "Closing odds fetch (NBA + MLB + NHL)")
    log("=" * 60)
    log("Afternoon pipeline complete — closing lines captured")
    log("=" * 60)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AXIOM Edge Daily Automation")
    parser.add_argument("--morning",   action="store_true", help="Run morning pipeline (data + picks + Discord)")
    parser.add_argument("--afternoon", action="store_true", help="Run afternoon pipeline (closing odds for CLV)")
    parser.add_argument("--evening",   action="store_true", help="Run evening pipeline (results + ROI update)")
    parser.add_argument("--discord",   action="store_true", help="Re-send Discord alert only")
    args = parser.parse_args()

    if args.discord:
        from discord_alert import send_alert
        send_alert()
    elif args.afternoon:
        afternoon_pipeline()
    elif args.evening:
        evening_pipeline()
    else:
        # Default and --morning both run the morning pipeline
        morning_pipeline()
