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

def run(script: str, label: str) -> bool:
    log(f"Starting {label}...")
    start  = time.time()
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True, cwd=str(Path(__file__).parent)
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


# ── Pipelines ─────────────────────────────────────────────────────────────────

def morning_pipeline():
    today = date.today().isoformat()
    log("=" * 60)
    log(f"AXIOM EDGE — MORNING PIPELINE — {today}")
    log("=" * 60)

    # ── NBA ──────────────────────────────────────────────────────────────────
    log("─── NBA ───────────────────────────────────────────────────")

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
    if odds_ok:
        _clear_stale_predictions("nba.db", "predictions", today)
        _clear_stale_predictions("nba.db", "spread_predictions", today)
        _clear_stale_predictions("nba.db", "totals_predictions", today)
        _clear_stale_predictions("nba.db", "props_predictions", today)
        run("predict.py",        "NBA: generating moneyline picks")
        run("spread_predict.py", "NBA: generating ATS picks")
        run("totals_predict.py", "NBA: generating totals picks")
        run("props_odds.py",     "NBA: fetching player props lines")
        run("props_predict.py",  "NBA: generating player points picks")
    else:
        log("NBA odds fetch failed — skipping NBA predictions today")

    # ── MLB ──────────────────────────────────────────────────────────────────
    log("─── MLB ───────────────────────────────────────────────────")

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
    if mlb_odds_ok:
        _clear_stale_predictions("mlb.db", "mlb_predictions", today)
        _clear_stale_predictions("mlb.db", "mlb_spread_predictions", today)
        _clear_stale_predictions("mlb.db", "mlb_totals_predictions", today)
        run("mlb_predict.py",        "MLB: generating moneyline picks")
        run("mlb_spread_predict.py", "MLB: generating run line picks")
        run("mlb_totals_predict.py", "MLB: generating totals picks")
    else:
        log("MLB odds/pitcher fetch failed — skipping MLB predictions today")

    # ── Discord alert ─────────────────────────────────────────────────────────
    log("─── Discord ────────────────────────────────────────────────")
    try:
        from discord_alert import send_alert
        send_alert()
    except Exception as e:
        log(f"  Discord alert error: {e}")

    log("=" * 60)
    log("Morning pipeline complete — check dashboard: streamlit run Axiom_Edge.py")
    log("=" * 60)
    return True


def evening_pipeline():
    today     = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    log("=" * 60)
    log(f"AXIOM EDGE — EVENING PIPELINE — {today}")
    log("=" * 60)

    # ── NBA results ───────────────────────────────────────────────────────────
    log("─── NBA results ────────────────────────────────────────────")
    conn = sqlite3.connect("nba.db")
    tp = conn.execute(
        "SELECT COUNT(*) FROM predictions WHERE predict_date=? AND actual_home_win IS NULL",
        (today,)
    ).fetchone()[0]
    yp = conn.execute(
        "SELECT COUNT(*) FROM predictions WHERE predict_date=? AND actual_home_win IS NULL",
        (yesterday,)
    ).fetchone()[0]
    conn.close()

    nba_target = today if tp > 0 else (yesterday if yp > 0 else None)
    if nba_target:
        log(f"Fetching NBA results for {nba_target}...")
        subprocess.run(
            [sys.executable, "results_fetcher.py", "--date", nba_target],
            cwd=str(Path(__file__).parent)
        )
        # Pull player logs for that date, then resolve props
        log(f"Resolving player props for {nba_target}...")
        subprocess.run(
            [sys.executable, "collect_props.py", "--date", nba_target],
            cwd=str(Path(__file__).parent)
        )
        subprocess.run(
            [sys.executable, "props_results_fetcher.py", "--date", nba_target],
            cwd=str(Path(__file__).parent)
        )
    else:
        log("No unresolved NBA predictions found")

    # ── MLB results ───────────────────────────────────────────────────────────
    log("─── MLB results ────────────────────────────────────────────")
    try:
        mlb_conn = sqlite3.connect("mlb.db")
        mlb_tp = mlb_conn.execute(
            "SELECT COUNT(*) FROM mlb_predictions WHERE predict_date=? AND actual_home_win IS NULL",
            (today,)
        ).fetchone()[0]
        mlb_yp = mlb_conn.execute(
            "SELECT COUNT(*) FROM mlb_predictions WHERE predict_date=? AND actual_home_win IS NULL",
            (yesterday,)
        ).fetchone()[0]
        mlb_conn.close()

        mlb_target = today if mlb_tp > 0 else (yesterday if mlb_yp > 0 else None)
        if mlb_target:
            log(f"Fetching MLB results for {mlb_target}...")
            subprocess.run(
                [sys.executable, "mlb_results_fetcher.py", "--date", mlb_target],
                cwd=str(Path(__file__).parent)
            )
        else:
            log("No unresolved MLB predictions found")
    except Exception as e:
        log(f"MLB results check failed: {e}")

    log("=" * 60)
    log("Evening pipeline complete — ROI tracker updated")
    log("=" * 60)


def afternoon_pipeline():
    today = date.today().isoformat()
    log("=" * 60)
    log(f"AXIOM EDGE — AFTERNOON PIPELINE — {today}")
    log("=" * 60)
    log("Fetching closing odds for CLV tracking (~4 PM)...")
    run("fetch_closing_odds.py", "Closing odds fetch (NBA + MLB)")
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
