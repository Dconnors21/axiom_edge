"""Honest, from-scratch evaluation metrics over graded (prob, label) pairs.

Computed from the stored predictions (model probability vs realized outcome),
not from training. Sparse samples are reported as-is, never dressed up.
"""
from __future__ import annotations

import math

# Below this many graded games, a reliability curve / ROC is noise — we say so
# rather than drawing a misleading line.
MIN_SAMPLE = 30


def empirical_auc(pairs: list[tuple[float, int]]) -> float | None:
    """ROC-AUC via the Mann-Whitney U statistic."""
    pos = [p for p, y in pairs if y == 1]
    neg = [p for p, y in pairs if y == 0]
    if not pos or not neg:
        return None
    # Rank all scores (average ranks for ties), sum ranks of positives.
    ordered = sorted(pairs, key=lambda t: t[0])
    ranks: list[float] = [0.0] * len(ordered)
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1][0] == ordered[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 1-based average rank
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    rank_sum_pos = sum(r for r, (_, y) in zip(ranks, ordered) if y == 1)
    n_pos, n_neg = len(pos), len(neg)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def brier(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def log_loss(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    eps = 1e-15
    total = 0.0
    for p, y in pairs:
        p = min(1 - eps, max(eps, p))
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(pairs)


def calibration(pairs: list[tuple[float, int]], bins: int = 10) -> list[dict]:
    """Reliability curve: mean predicted vs realized hit rate per probability bin."""
    out: list[dict] = []
    width = 1.0 / bins
    for b in range(bins):
        lo, hi = b * width, (b + 1) * width
        members = [(p, y) for p, y in pairs if (lo <= p < hi or (b == bins - 1 and p == 1.0))]
        if not members:
            continue
        pred = sum(p for p, _ in members) / len(members)
        act = sum(y for _, y in members) / len(members)
        out.append({
            "bucket": f"{int(lo * 100)}-{int(hi * 100)}%",
            "predicted": pred, "actual": act, "n": len(members),
        })
    return out


def roc_curve(pairs: list[tuple[float, int]], max_points: int = 60) -> list[dict]:
    """ROC points (fpr, tpr) by sweeping the decision threshold high -> low."""
    pos = sum(1 for _, y in pairs if y == 1)
    neg = sum(1 for _, y in pairs if y == 0)
    if pos == 0 or neg == 0:
        return []
    ordered = sorted(pairs, key=lambda t: t[0], reverse=True)
    pts = [{"fpr": 0.0, "tpr": 0.0}]
    tp = fp = 0
    prev = None
    for p, y in ordered:
        if prev is not None and p != prev:
            pts.append({"fpr": fp / neg, "tpr": tp / pos})
        if y == 1:
            tp += 1
        else:
            fp += 1
        prev = p
    pts.append({"fpr": fp / neg, "tpr": tp / pos})
    # Downsample for transport if dense.
    if len(pts) > max_points:
        step = len(pts) / max_points
        pts = [pts[int(i * step)] for i in range(max_points)] + [pts[-1]]
    return pts
