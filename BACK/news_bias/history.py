"""Historical reaction statistics (Part 2).

Pure functions over rows of EventHistory so they are trivially unit-testable
without a database. The DB layer (engine) loads rows and calls these.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile (pct in 0..100). Returns 0.0 if empty."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[int(rank)])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (rank - low))


@dataclass(frozen=True, slots=True)
class ReactionStats:
    sample_size: int
    # Hit rate: first 1m candle direction matches the surprise direction.
    first_candle_hit_rate: float
    # Hit rate: 15m outcome direction matches the surprise direction.
    m15_hit_rate: float
    avg_move_points: float
    p80_move_points: float
    avg_fakeout_points: float
    avg_spread_points: float


def _surprise_dir(surprise: float | None) -> str | None:
    if surprise is None or surprise == 0:
        return None
    # Sign convention: a positive surprise (actual > forecast) is USD-positive
    # for the affected USD instrument. Direction is resolved per-symbol by the
    # caller via the mapping; here we only normalise the surprise's own sign.
    return "UP" if surprise > 0 else "DOWN"


def compute_stats(rows: Iterable[dict[str, Any]]) -> ReactionStats:
    """Compute aggregate reaction stats for one (event_type, symbol).

    Each row is expected to carry: surprise, first_1m_dir, first_1m_points,
    m15_dir, m15_points, fakeout_points, spread_points. Direction strings are
    "BUY"/"SELL"/"FLAT". The surprise direction is mapped to BUY/SELL through
    ``dir_of_surprise`` so hit rates are comparable to a bias direction.
    """
    rows = list(rows)
    n = len(rows)
    if n == 0:
        return ReactionStats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    first_hits = 0
    first_total = 0
    m15_hits = 0
    m15_total = 0
    moves: list[float] = []
    fakeouts: list[float] = []
    spreads: list[float] = []

    for r in rows:
        surprise = r.get("surprise")
        sdir = _surprise_dir(surprise)
        # Map surprise sign to a trade direction using the caller-provided
        # mapping (BUY if surprise up for this symbol, else SELL). We accept an
        # optional precomputed "expected_dir" to stay pure.
        expected = r.get("expected_dir") or _default_expected(sdir)
        f1 = r.get("first_1m_dir")
        m15 = r.get("m15_dir")
        if expected and f1 in ("BUY", "SELL"):
            first_total += 1
            if f1 == expected:
                first_hits += 1
        if expected and m15 in ("BUY", "SELL"):
            m15_total += 1
            if m15 == expected:
                m15_hits += 1
        for key, bucket in (("first_1m_points", moves),
                            ("fakeout_points", fakeouts),
                            ("spread_points", spreads)):
            v = r.get(key)
            if isinstance(v, (int, float)) and math.isfinite(float(v)):
                bucket.append(abs(float(v)))

    return ReactionStats(
        sample_size=n,
        first_candle_hit_rate=(first_hits / first_total) if first_total else 0.0,
        m15_hit_rate=(m15_hits / m15_total) if m15_total else 0.0,
        avg_move_points=(sum(moves) / len(moves)) if moves else 0.0,
        p80_move_points=_percentile(moves, 80.0),
        avg_fakeout_points=(sum(fakeouts) / len(fakeouts)) if fakeouts else 0.0,
        avg_spread_points=(sum(spreads) / len(spreads)) if spreads else 0.0,
    )


def _default_expected(sdir: str | None) -> str | None:
    # Default identity mapping used when a caller does not supply expected_dir.
    if sdir == "UP":
        return "BUY"
    if sdir == "DOWN":
        return "SELL"
    return None
