"""Web Push: subscription store + VAPID sender (pywebpush).

Subscriptions and per-user prefs live in a local SQLite store. Sending respects
each subscriber's edge threshold, leagues, quiet hours, and daily cap, and prunes
dead subscriptions (404/410). Notifications are informational, never coercive.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from pywebpush import webpush, WebPushException
except ImportError:  # serving still works without the dep installed
    webpush = None
    WebPushException = Exception

# Load .env (VAPID_*). env_loader lives at the repo root.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

_DB = Path(__file__).resolve().parent.parent / "push.db"
_ET = ZoneInfo("America/New_York")

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_SUB = os.getenv("VAPID_SUB", "mailto:admin@axiom.edge")

DEFAULT_PREFS = {
    "threshold": 0.05,                 # min edge to notify on
    "leagues": "nba,mlb,nhl",
    "quiet_start": 23,                 # ET hour quiet window starts
    "quiet_end": 8,                    # ET hour quiet window ends
    "daily_cap": 3,
}


def _conn():
    c = sqlite3.connect(str(_DB))
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = _conn()
    c.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            endpoint    TEXT PRIMARY KEY,
            sub_json    TEXT NOT NULL,
            threshold   REAL,
            leagues     TEXT,
            quiet_start INTEGER,
            quiet_end   INTEGER,
            daily_cap   INTEGER,
            sent_today  INTEGER DEFAULT 0,
            sent_date   TEXT,
            created_at  TEXT
        )
    """)
    c.commit()
    c.close()


def upsert(subscription: dict, prefs: dict | None = None):
    p = {**DEFAULT_PREFS, **(prefs or {})}
    c = _conn()
    c.execute("""
        INSERT INTO push_subscriptions
          (endpoint, sub_json, threshold, leagues, quiet_start, quiet_end, daily_cap, created_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(endpoint) DO UPDATE SET
          sub_json=excluded.sub_json, threshold=excluded.threshold, leagues=excluded.leagues,
          quiet_start=excluded.quiet_start, quiet_end=excluded.quiet_end, daily_cap=excluded.daily_cap
    """, (subscription["endpoint"], json.dumps(subscription), p["threshold"], p["leagues"],
          p["quiet_start"], p["quiet_end"], p["daily_cap"], datetime.utcnow().isoformat()))
    c.commit()
    c.close()


def update_prefs(endpoint: str, prefs: dict) -> bool:
    fields = {k: prefs[k] for k in ("threshold", "leagues", "quiet_start", "quiet_end", "daily_cap")
              if k in prefs}
    if not fields:
        return False
    sets = ", ".join(f"{k}=?" for k in fields)
    c = _conn()
    cur = c.execute(f"UPDATE push_subscriptions SET {sets} WHERE endpoint=?",
                    (*fields.values(), endpoint))
    c.commit()
    n = cur.rowcount
    c.close()
    return n > 0


def delete(endpoint: str):
    c = _conn()
    c.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))
    c.commit()
    c.close()


def get(endpoint: str) -> dict | None:
    c = _conn()
    row = c.execute("SELECT * FROM push_subscriptions WHERE endpoint=?", (endpoint,)).fetchone()
    c.close()
    return dict(row) if row else None


def _send_raw(sub_json: dict, payload: dict) -> int:
    """Returns HTTP status; raises on hard failure. 404/410 => prune."""
    if webpush is None:
        raise RuntimeError("pywebpush not installed")
    res = webpush(
        subscription_info=sub_json,
        data=json.dumps(payload),
        vapid_private_key=VAPID_PRIVATE_KEY,
        vapid_claims={"sub": VAPID_SUB},
    )
    return res.status_code


def send_to_one(endpoint: str, payload: dict) -> bool:
    row = get(endpoint)
    if not row:
        return False
    try:
        _send_raw(json.loads(row["sub_json"]), payload)
        return True
    except WebPushException as e:
        if getattr(e, "response", None) is not None and e.response.status_code in (404, 410):
            delete(endpoint)
        return False


def send_to_eligible(payload: dict, *, league: str | None = None, edge: float | None = None) -> dict:
    """Send to every subscriber whose prefs allow it (league, threshold, quiet
    hours, daily cap). Prunes dead subscriptions. Returns a summary."""
    init_db()
    now = datetime.now(_ET)
    today = now.date().isoformat()
    hour = now.hour

    c = _conn()
    rows = c.execute("SELECT * FROM push_subscriptions").fetchall()
    sent = skipped = pruned = 0
    for row in rows:
        # League filter
        if league and league not in (row["leagues"] or "").split(","):
            skipped += 1
            continue
        # Edge threshold
        if edge is not None and edge < (row["threshold"] or 0):
            skipped += 1
            continue
        # Quiet hours (window may wrap midnight)
        qs, qe = row["quiet_start"], row["quiet_end"]
        in_quiet = (qs <= hour or hour < qe) if qs > qe else (qs <= hour < qe)
        if in_quiet:
            skipped += 1
            continue
        # Daily cap (reset on a new day)
        sent_today = row["sent_today"] if row["sent_date"] == today else 0
        if sent_today >= (row["daily_cap"] or 0):
            skipped += 1
            continue
        # Send
        try:
            _send_raw(json.loads(row["sub_json"]), payload)
            c.execute("UPDATE push_subscriptions SET sent_today=?, sent_date=? WHERE endpoint=?",
                      (sent_today + 1, today, row["endpoint"]))
            sent += 1
        except WebPushException as e:
            if getattr(e, "response", None) is not None and e.response.status_code in (404, 410):
                c.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (row["endpoint"],))
                pruned += 1
            else:
                skipped += 1
    c.commit()
    c.close()
    return {"sent": sent, "skipped": skipped, "pruned": pruned}
