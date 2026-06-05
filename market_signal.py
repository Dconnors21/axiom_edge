# ── market_signal.py ──────────────────────────────────────────────────────────
# Serve-time market signals derived from the odds snapshots we already collect
# (every odds pull is appended with its own pulled_at, so each game accumulates
# a small line-movement history during the day).
#
# These are NOT model features — the historical snapshot depth is far too thin
# to train on, and the closing line would leak outcome information. Instead they
# are computed for *today's* games and used to (a) annotate each pick and
# (b) apply a soft gate: down-weight a bet when the market is moving against our
# pick, and confirm one when it is steaming toward it.
#
# Per (game_id) we compute a side-A-oriented consensus, where side A is the
# home team (h2h / spread) or the Over (totals):
#   • kind="h2h"    → metric is the de-vigged side-A fair probability (prob space)
#   • kind="spread" → metric is the side-A point spread          (point space)
#   • kind="total"  → metric is the total points line            (point space)
# Movement = latest consensus − earliest consensus across today's snapshots,
# oriented so that POSITIVE always means "toward side A" (home / over).
# Dispersion = std of the latest metric across books.
# Sharp value = the metric at the sharpest available book (SHARP_BOOKS order).
#
# The schema varies by sport, so callers pass explicit column names:
#   NBA   moneyline : odds, market_filter='h2h',  price_a='home_price', price_b='away_price', kind='h2h'
#   NBA   spread    : odds, market_filter='spreads', point_col='home_point', kind='spread'
#   NBA   totals    : odds, market_filter='totals',  point_col='home_point', kind='total'
#   MLB   moneyline : mlb_odds, market_filter='h2h', price_a/b='home_price'/'away_price', kind='h2h'
#   MLB   run line  : mlb_spread_odds (no market col), point_col='home_point', kind='spread'
#   MLB   totals    : mlb_totals_odds (no market col), point_col='total_line', kind='total'
#   NHL   analogous to MLB.

import pandas as pd

DEFAULT_SHARP_BOOKS = ["pinnacle", "draftkings", "fanduel", "betmgm", "caesars"]

# Thresholds for "meaningful" movement, by metric type.
_MOVE_THRESHOLD = {"prob": 0.03, "point": 0.5}
_AGAINST_KELLY_MULT = 0.6   # soft-gate haircut when line moves against our pick


def _amer_to_imp(o):
    if o is None or pd.isna(o):
        return None
    o = float(o)
    return 100.0 / (o + 100.0) if o > 0 else abs(o) / (abs(o) + 100.0)


def _devig_a(pa, pb):
    """De-vigged side-A (home / over) fair probability from the two prices."""
    ia, ib = _amer_to_imp(pa), _amer_to_imp(pb)
    if ia is None or ib is None or (ia + ib) == 0:
        return None
    return ia / (ia + ib)


def compute_signals(conn, odds_table, kind, *,
                    price_a_col=None, price_b_col=None, point_col=None,
                    market_filter=None, market_col="market",
                    game_col="game_id", book_col="bookmaker",
                    ts_col="pulled_at", sharp_books=None) -> dict:
    """Returns {game_id: signal_dict} for one market of one odds table.

    kind: 'h2h' (prob metric from price_a/price_b) or 'spread'/'total'
          (point metric from point_col).
    """
    sharp_books = sharp_books or DEFAULT_SHARP_BOOKS

    needed = [f"{game_col} AS game_id", f"{book_col} AS bookmaker",
              f"{ts_col} AS pulled_at"]
    if kind == "h2h":
        needed += [f"{price_a_col} AS pa", f"{price_b_col} AS pb"]
    else:
        needed += [f"{point_col} AS pt"]

    where, params = "", []
    if market_filter is not None:
        where = f" WHERE {market_col} = ?"
        params = [market_filter]

    try:
        df = pd.read_sql(f"SELECT {', '.join(needed)} FROM {odds_table}{where}",
                         conn, params=params or None)
    except Exception:
        return {}
    if df.empty:
        return {}

    df["pulled_at"] = pd.to_datetime(df["pulled_at"], errors="coerce")
    df = df.dropna(subset=["pulled_at"])

    if kind == "h2h":
        df["_metric"] = [_devig_a(a, b) for a, b in zip(df["pa"], df["pb"])]
        metric_type = "prob"
    else:
        df["_metric"] = pd.to_numeric(df["pt"], errors="coerce")
        metric_type = "point"
    df = df.dropna(subset=["_metric"])
    if df.empty:
        return {}

    out = {}
    for gid, g in df.groupby("game_id"):
        first_ts, last_ts = g["pulled_at"].min(), g["pulled_at"].max()
        open_consensus   = g[g["pulled_at"] == first_ts]["_metric"].median()
        latest_snap      = g[g["pulled_at"] == last_ts]
        latest_consensus = latest_snap["_metric"].median()
        dispersion = float(latest_snap["_metric"].std(ddof=0)) \
            if len(latest_snap) > 1 else 0.0

        sharp_value = None
        for b in sharp_books:
            r = latest_snap[latest_snap["bookmaker"] == b]
            if not r.empty:
                sharp_value = float(r["_metric"].iloc[0])
                break

        raw_move = float(latest_consensus - open_consensus)
        # A more-negative home spread means the home side is more favored
        # (money on home) → that is movement TOWARD side A. Flip the sign so
        # positive always means "toward side A".
        toward_a = -raw_move if kind == "spread" else raw_move

        out[str(gid)] = {
            "kind":        kind,
            "metric_type": metric_type,
            "open":        float(open_consensus),
            "latest":      float(latest_consensus),
            "move":        toward_a,     # +: toward side A (home / over)
            "dispersion":  dispersion,
            "n_books":     int(latest_snap["bookmaker"].nunique()),
            "n_snapshots": int(g["pulled_at"].nunique()),
            "sharp_value": sharp_value,
        }
    return out


def gate_pick(sig: dict, pick_is_side_a: bool):
    """Return (kelly_multiplier, flag_str, oriented_move) for a pick.

    pick_is_side_a: True if betting the home team (h2h/spread) or the Over.
    Positive oriented_move == market moving toward our pick (confirmation).
    """
    if not sig:
        return 1.0, "", 0.0
    move = sig.get("move", 0.0)
    oriented = move if pick_is_side_a else -move
    thr = _MOVE_THRESHOLD.get(sig.get("metric_type", "prob"), 0.03)

    if oriented <= -thr:
        return _AGAINST_KELLY_MULT, "⚠ line moving against pick", oriented
    if oriented >= thr:
        return 1.0, "steam toward pick ✓", oriented
    return 1.0, "", oriented


def describe(sig: dict) -> str:
    """Short human-readable summary of market state (for logs/Discord)."""
    if not sig:
        return ""
    mv = sig.get("move", 0.0)
    body = f"consensus move {mv:+.1%}" if sig.get("metric_type") == "prob" \
        else f"line move {mv:+.1f}"
    return f"{body} across {sig.get('n_books', 0)} books, " \
           f"{sig.get('n_snapshots', 0)} snapshot(s)"


def annotate_results(results, sigs, *, value_a, value_b, kelly_a, kelly_b,
                     edge_a, edge_b, id_col="game_id",
                     team_cols=("away_team", "home_team"), verbose=True):
    """Annotate a predictions DataFrame in place with market signals + soft gate.

    Side A == home/over (value_a/kelly_a/edge_a), side B == away/under.
    Adds 'market_flag' (str) and 'market_move' (signed, oriented to our pick).
    When the line is moving against our pick, the picked side's Kelly is cut.
    """
    flags, moves = [], []
    for idx, row in results.iterrows():
        sig = sigs.get(str(row[id_col]))
        if row.get(value_a):
            pick_a, kcol = True, kelly_a
        elif row.get(value_b):
            pick_a, kcol = False, kelly_b
        else:  # no value bet — annotate the stronger side for context
            pick_a = float(row.get(edge_a, 0) or 0) >= float(row.get(edge_b, 0) or 0)
            kcol = kelly_a if pick_a else kelly_b

        mult, flag, oriented = gate_pick(sig, pick_a)
        if mult < 1.0 and kcol in results.columns:
            results.at[idx, kcol] = float(results.at[idx, kcol]) * mult
        flags.append(flag)
        moves.append(float(oriented) if sig else 0.0)
        if verbose and flag:
            away = row.get(team_cols[0], "")
            home = row.get(team_cols[1], "")
            print(f"  Market: {away} @ {home} {flag} ({describe(sig)})")

    results["market_flag"] = flags
    results["market_move"] = moves
    return results
