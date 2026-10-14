"""Bias output + probability formula (Part 3).

Transparent, documented combination of the news score and the historical hit
rate. Pure functions -> unit-tested directly.

probability_pct = clamp( BASE
                         + W_NEWS   * news_strength      (0..1)
                         + W_HIST   * hist_hit_rate      (0..1)
                         - PENALTY  * data_gaps          (0..1),
                         0, 100 )

where news_strength = |news_score| in [-1, 1] mapped to [0, 1], and hist_hit_rate
is the first-candle hit rate from ReactionStats. If there is not enough data
(no news, or history sample below the minimum) the confidence is lowered and the
result is NO_TRADE.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .history import ReactionStats

# Documented weights (kept as named constants so the formula is auditable).
BASE = 50.0
W_NEWS = 30.0        # up to +30 from news
W_HIST = 20.0        # up to +20 from historical support
W_PRIOR = 22.0       # up to +22 from the consensus prior (only when news is split)
PENALTY_PER_GAP = 15.0  # -15 per missing data source (news / history)


@dataclass(slots=True)
class BiasResult:
    event_key: str
    event_type: str
    symbol: str
    direction: str                 # BUY | SELL | NO_TRADE
    probability_pct: float
    news_score: float
    reasons: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    historical_support: dict = field(default_factory=dict)
    formula: str = ""


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def build_bias(
    *,
    event_key: str,
    event_type: str,
    symbol: str,
    news_score: float,             # -1 (bearish) .. +1 (bullish) for THIS symbol
    news_reasons: list[str],
    news_sources: list[str],
    stats: ReactionStats,
    min_probability_pct: float,
    min_history_sample: int,
    news_available: bool = True,
    prior_direction: str | None = None,   # "BUY" | "SELL" | None  (consensus lean)
    prior_strength: float = 0.0,          # 0..1 confidence in that prior
    prior_reason: str = "",               # human explanation of the prior
) -> BiasResult:
    """Combine news + history into a single bias decision for one symbol.

    When the news score is split (no directional edge) and there is not yet
    enough real history (``sample_size < min_history_sample``), a transparent
    *consensus prior* (from forecast vs previous) is used as a lean. It retires
    automatically once history can speak for itself, and is always labelled in
    ``reasons`` so the call is auditable.
    """
    reasons: list[str] = list(news_reasons)
    sources: list[str] = list(news_sources)

    have_history = stats.sample_size >= min_history_sample

    # Direction from the sign of the news score (already mapped to this symbol).
    if news_score > 0:
        direction = "BUY"
    elif news_score < 0:
        direction = "SELL"
    else:
        direction = "NO_TRADE"
        reasons.append("News score is neutral; no directional edge.")

    # -- consensus prior: bridge the gap until real history exists ------------ #
    used_prior = False
    if (direction == "NO_TRADE" and not have_history
            and prior_direction in ("BUY", "SELL") and prior_strength > 0):
        direction = prior_direction
        used_prior = True
        reasons.append(
            (prior_reason or
             f"Consensus prior leans {prior_direction} for {symbol}.")
            + " Used only until real history builds; will be corrected by it."
        )

    # Data gaps: news and history each count as one when missing/unavailable.
    data_gaps = 0
    if not news_available or not news_sources:
        data_gaps += 1
        reasons.append("News context unavailable or empty; confidence lowered.")
    if not have_history:
        data_gaps += 1
        reasons.append(
            f"Only {stats.sample_size} historical sample(s); need >= {min_history_sample}; "
            "confidence lowered."
        )
    # The prior is a stand-in for the missing history signal, so when it is in
    # play we do not also charge the history penalty (no double-counting).
    effective_gaps = data_gaps - (1 if (used_prior and not have_history) else 0)

    news_strength = _clamp(abs(news_score), 0.0, 1.0)
    hist_hit = _clamp(stats.first_candle_hit_rate, 0.0, 1.0) if have_history else 0.0

    if used_prior:
        directional_component = W_PRIOR * _clamp(prior_strength, 0.0, 1.0)
        component_label = f"{W_PRIOR}*prior({prior_strength:.2f})"
    else:
        directional_component = W_NEWS * news_strength
        component_label = f"{W_NEWS}*news({news_strength:.3f})"

    raw = BASE + directional_component + W_HIST * hist_hit - PENALTY_PER_GAP * effective_gaps
    probability = _clamp(raw, 0.0, 100.0)

    # Not enough data anywhere -> NO_TRADE regardless of the raw number.
    if effective_gaps >= 2 or direction == "NO_TRADE":
        direction = "NO_TRADE"
    elif probability < min_probability_pct:
        direction = "NO_TRADE"
        reasons.append(
            f"Probability {probability:.0f}% below the {min_probability_pct:.0f}% threshold."
        )

    hist_support = {
        "sample_size": stats.sample_size,
        "hit_rate": round(stats.first_candle_hit_rate, 4),
        "avg_move": round(stats.avg_move_points, 4),
        "p80_move": round(stats.p80_move_points, 4),
        "avg_fakeout": round(stats.avg_fakeout_points, 4),
        "avg_spread": round(stats.avg_spread_points, 4),
    }
    formula = (
        f"probability = clamp({BASE} + {component_label} "
        f"+ {W_HIST}*{hist_hit:.3f} - {PENALTY_PER_GAP}*{effective_gaps}, 0, 100) = {probability:.1f}"
    )

    return BiasResult(
        event_key=event_key,
        event_type=event_type,
        symbol=symbol,
        direction=direction,
        probability_pct=round(probability, 1),
        news_score=round(news_score, 4),
        reasons=reasons,
        sources=sources,
        historical_support=hist_support,
        formula=formula,
    )


def result_to_json(r: BiasResult, generated_at_iso: str) -> dict:
    """The exact JSON shape required by Part 3."""
    return {
        "event": r.event_key,
        "symbol": r.symbol,
        "direction": r.direction,
        "probability_pct": r.probability_pct,
        "reasons": r.reasons,
        "sources": r.sources,
        "historical_support": r.historical_support,
        "generated_at": generated_at_iso,
    }
