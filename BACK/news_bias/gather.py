"""News gathering + per-symbol scoring (Part 1).

Collects context items for an event across the lookback window and derives a
per-symbol news score in [-1, 1] by reusing the engine's hawkish/dovish keyword
lexicon (so the new engine agrees with the existing sentiment module).
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import EVENT_SYMBOL_MAP
from .sources import CalendarEvent, ContextItem, NewsSource

# Per-event extra queries (broad market context around the release).
EVENT_CONTEXT_QUERIES: dict[str, str] = {
    "NFP": "US jobs report nonfarm payrolls dollar Fed",
    "CPI": "US CPI inflation report dollar Fed",
    "PPI": "US producer prices inflation dollar",
    "FOMC": "Federal Reserve FOMC rate decision dollar",
    "GDP": "US GDP growth report dollar",
    "RETAIL_SALES": "US retail sales consumer spending dollar",
    "JOBLESS_CLAIMS": "US jobless claims unemployment dollar",
    "CB_SPEECH": "central bank speech Fed dollar",
    "GEOPOLITICAL": "geopolitical risk war sanctions safe haven gold oil",
}

# Per-symbol query fragments to fetch instrument-specific context.
SYMBOL_CONTEXT_QUERIES: dict[str, str] = {
    "XAUUSD": "gold price dollar Fed",
    "XAGUSD": "silver price dollar",
    "US30": "Dow Jones Wall Street Fed",
    "EURUSD": "EUR USD euro dollar exchange rate",
    "GBPUSD": "GBP USD pound dollar",
    "USDJPY": "USD JPY yen",
    "USOIL": "oil price crude",
    "BTCUSD": "Bitcoin price",
    "ETHUSD": "Ethereum price",
}


def symbols_for_event(event_type: str) -> tuple[str, ...]:
    return EVENT_SYMBOL_MAP.get(event_type.upper(), ())


@dataclass(slots=True)
class GatherResult:
    items: list[ContextItem]
    per_symbol_score: dict[str, float]      # -1..1
    per_symbol_reasons: dict[str, list[str]]
    per_symbol_sources: dict[str, list[str]]
    available: bool                          # False if no context could be fetched


async def gather_context(
    event: CalendarEvent,
    news: NewsSource,
    *,
    lookback_hours: int = 72,
    llm_summarize=None,                      # optional callable(items)->{title:summary}
) -> GatherResult:
    """Fetch 24-72h context for the event and score each affected symbol.

    ``llm_summarize`` is an optional async callable that takes the list of
    ContextItem and returns a {title: summary} mapping. When omitted, the raw
    titles double as summaries (keyword scoring still runs).
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=lookback_hours)
    syms = symbols_for_event(event.event_type)
    if not syms:
        return GatherResult([], {}, {}, {}, available=False)

    queries = [EVENT_CONTEXT_QUERIES.get(event.event_type, event.event_type)]
    for sym in syms:
        frag = SYMBOL_CONTEXT_QUERIES.get(sym)
        if frag:
            queries.append(frag)

    # Deduplicate queries, gather, merge (title-keyed).
    seen: dict[str, ContextItem] = {}
    for q in dict.fromkeys(queries):
        try:
            for item in await news.headlines(q, since, now, max_items=25):
                seen.setdefault(item.title, item)
        except Exception:  # noqa: BLE001 - one bad source must not abort gathering
            continue
    items = list(seen.values())

    available = bool(items)
    summaries: dict[str, str] = {}
    if items and llm_summarize is not None:
        try:
            summaries = await llm_summarize(items) or {}
        except Exception:  # noqa: BLE001
            summaries = {}
    for it in items:
        if it.title in summaries and summaries[it.title]:
            it.summary = summaries[it.title]

    per_score: dict[str, float] = {}
    per_reasons: dict[str, list[str]] = {}
    per_sources: dict[str, list[str]] = {}
    for sym in syms:
        score, reasons, sources = _score_symbol(items, sym)
        per_score[sym] = score
        per_reasons[sym] = reasons
        per_sources[sym] = sources
    return GatherResult(items, per_score, per_reasons, per_sources, available)


def _score_symbol(items: list[ContextItem], symbol: str) -> tuple[float, list[str], list[str]]:
    """Reuse the engine hawkish/dovish lexicon, mapped to this symbol's direction."""
    # Import the engine lexicon lazily to avoid a circular import at load time.
    try:
        from engine import DOVISH, HAWKISH
    except Exception:  # noqa: BLE001
        HAWKISH = DOVISH = None

    frag = SYMBOL_CONTEXT_QUERIES.get(symbol)
    relevant = [it for it in items if _mentions(it, symbol, frag)]

    hawk = dove = 0
    reasons: list[str] = []
    sources: list[str] = []
    for it in relevant[:12]:
        text = f"{it.title} {it.summary}"
        h = bool(HAWKISH.search(text)) if HAWKISH else False
        d = bool(DOVISH.search(text)) if DOVISH else False
        if h and not d:
            hawk += 1
        elif d and not h:
            dove += 1
        if it.url:
            sources.append(it.url)
        if it.title:
            reasons.append(it.title)
    n = hawk + dove
    usd_score = (hawk - dove) / n if n else 0.0

    # Map USD-strength score to this symbol's trade direction.
    # USD-quoted pairs (EURUSD, XAUUSD...) move inversely to USD strength.
    inverse = symbol in {"XAUUSD", "XAGUSD", "USOIL", "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"}
    mapped = -usd_score if inverse else usd_score
    if n == 0:
        reasons.append("No clearly directional headlines in the lookback window.")
    return mapped, reasons[:8], sources[:8]


def _mentions(item: ContextItem, symbol: str, frag: str | None) -> bool:
    text = f"{item.title} {item.summary}".casefold()
    if symbol.casefold() in text:
        return True
    if frag:
        # match if any significant keyword from the fragment appears
        for word in frag.replace(" OR ", " ").split():
            w = word.strip().casefold()
            if len(w) > 3 and w in text:
                return True
    return False
