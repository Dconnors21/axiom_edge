# ── env_loader.py ─────────────────────────────────────────────────────────────
# Minimal .env loader (no python-dotenv dependency). Reads KEY=VALUE lines from
# the project's .env file and populates os.environ for any keys not already set
# in the real environment. Safe to call repeatedly.
#
# Real environment variables always win over .env, so CI / production can set
# ODDS_API_KEY directly without a .env file present.

import os
from pathlib import Path

_LOADED = False


def load_env(env_path: Path | None = None) -> None:
    global _LOADED
    if _LOADED:
        return
    path = env_path or (Path(__file__).parent / ".env")
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            # Don't override variables already set in the real environment.
            if key and key not in os.environ:
                os.environ[key] = val
    _LOADED = True


def require(key: str) -> str:
    """Return an env var, raising a clear error if it is missing/blank."""
    load_env()
    val = os.getenv(key, "").strip()
    if not val:
        raise RuntimeError(
            f"{key} is not set. Add it to your .env file "
            f"(e.g. {key}=your_value_here) or export it in your shell."
        )
    return val
