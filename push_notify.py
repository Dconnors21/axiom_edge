# ── push_notify.py ────────────────────────────────────────────────────────────
# Sends the day's top edge as a web-push alert to eligible subscribers.
# Informational only (no "bet now" / urgency). Run after morning predictions;
# per-subscriber threshold, leagues, quiet hours, and daily cap are enforced by
# api.push.send_to_eligible.
#
# Usage: python push_notify.py

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api.main import insight
from api.push import send_to_eligible, init_db


def _odds(n) -> str:
    if n is None:
        return ""
    return f"+{n}" if n > 0 else str(n)


def main():
    init_db()
    ins = insight()
    if not ins.available or ins.edge is None:
        print("No qualifying edge today — no push sent.")
        return

    body = (f"{ins.pick} {_odds(ins.price)}: {ins.edge:+.1%} edge on {ins.matchup}. "
            f"Tap to review the read.")
    payload = {
        "title": f"AXIOM · {(ins.league or '').upper()} edge",
        "body": body,
        "url": "/",
        "tag": f"axiom-edge-{ins.slate_date or 'today'}",
    }
    res = send_to_eligible(payload, league=ins.league, edge=ins.edge)
    print(f"Push: sent {res['sent']}, skipped {res['skipped']}, pruned {res['pruned']}")


if __name__ == "__main__":
    main()
