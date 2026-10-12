"""Swappable data-source adapters with caching (Part 1).

Small, dependency-free adapters behind a common interface so the calendar and
news providers can be swapped without touching the engine. Results are cached
in-memory with a TTL to stay friendly to free sources and 1GB RAM.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(slots=True)
class CalendarEvent:
    event_type: str            # NFP | CPI | ... (normalised upper)
    title: str
    time: datetime             # UTC
    currency: str
    impact: str
    forecast: Optional[float]
    previous: Optional[float]

    @property
    def key(self) -> str:
        return f"{self.event_type}:{int(self.time.timestamp())}"


@dataclass(slots=True)
class ContextItem:
    title: str
    source: str
    url: str
    published_at: Optional[datetime]
    summary: str = ""


class CalendarSource:
    """Interface: return upcoming high-impact events from ``since`` onward."""

    async def high_impact_events(self, since: datetime) -> list[CalendarEvent]:  # pragma: no cover
        raise NotImplementedError


class NewsSource:
    """Interface: return context headlines for a query within a time window."""

    async def headlines(self, query: str, since: datetime, until: datetime,
                        max_items: int = 25) -> list[ContextItem]:  # pragma: no cover
        raise NotImplementedError


class _TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str, ttl: float) -> Optional[Any]:
        hit = self._store.get(key)
        if not hit:
            return None
        expires, value = hit
        if time.monotonic() > expires:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        self._store[key] = (time.monotonic() + ttl, value)


# Title -> event type normalisation (superset of the legacy four).
_EVENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = (
    ("NFP", ("non-farm", "nonfarm", "non-farm payrolls", "nfp")),
    ("CPI", ("cpi", "consumer price")),
    ("PPI", ("ppi", "producer price")),
    ("FOMC", ("fomc", "federal funds rate", "fed interest rate", "interest rate decision")),
    ("GDP", ("gdp", "gross domestic product")),
    ("RETAIL_SALES", ("retail sales",)),
    ("JOBLESS_CLAIMS", ("jobless claims", "unemployment claims", "initial claims")),
    ("CB_SPEECH", ("speaks", "speech", "testifies", "press conference")),
    ("GEOPOLITICAL", ("war", "strike", "invasion", "sanctions", "missile", "ceasefire")),
)


def classify_event(title: str) -> Optional[str]:
    t = title.casefold()
    for etype, words in _EVENT_KEYWORDS:
        if any(w in t for w in words):
            return etype
    return None


class SharedCalendarSource(CalendarSource):
    """Reads events from the engine's already-fetched EconomicCalendar.

    Avoids a second HTTP fetch of the same feed (which can 429) by adapting the
    engine's EconEvent list. ``engine_calendar`` is the engine.EconomicCalendar.
    """

    def __init__(self, engine_calendar) -> None:
        self._cal = engine_calendar

    async def high_impact_events(self, since: datetime) -> list[CalendarEvent]:
        out: list[CalendarEvent] = []
        for e in getattr(self._cal, "events", []) or []:
            try:
                if e.time < since:
                    continue
                etype = getattr(e.event_type, "value", str(e.event_type)).upper()
                out.append(CalendarEvent(
                    event_type=etype, title=e.title, time=e.time,
                    currency=getattr(e, "country", "USD") or "USD", impact="High",
                    forecast=getattr(e, "forecast", None), previous=getattr(e, "previous", None),
                ))
            except Exception:  # noqa: BLE001
                continue
        out.sort(key=lambda e: e.time)
        return out


class FallbackCalendarSource(CalendarSource):
    """Tries the shared calendar first; falls back to a live fetch on empty/error."""

    def __init__(self, primary: CalendarSource, fallback: CalendarSource) -> None:
        self._primary = primary
        self._fallback = fallback

    async def high_impact_events(self, since: datetime) -> list[CalendarEvent]:
        try:
            events = await self._primary.high_impact_events(since)
            if events:
                return events
        except Exception:  # noqa: BLE001
            pass
        return await self._fallback.high_impact_events(since)


def _num(s: Any) -> Optional[float]:
    import re

    if not s:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(s))
    try:
        return float(cleaned)
    except ValueError:
        return None


class ForexFactoryCalendar(CalendarSource):
    """Wraps the forex-factory JSON feed into CalendarEvent objects."""

    URLS = (
        "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
    )

    def __init__(self, cache_ttl: float = 300.0) -> None:
        self._cache = _TTLCache()
        self._ttl = cache_ttl

    async def high_impact_events(self, since: datetime) -> list[CalendarEvent]:
        import httpx

        cached = self._cache.get("ff", self._ttl)
        if cached is None:
            events: list[CalendarEvent] = []
            async with httpx.AsyncClient(timeout=15) as http:
                for url in self.URLS:
                    try:
                        r = await http.get(url)
                        r.raise_for_status()
                        rows = r.json()
                    except Exception:  # noqa: BLE001
                        continue
                    for row in rows:
                        if row.get("impact") != "High":
                            continue
                        etype = classify_event(row.get("title", ""))
                        if not etype:
                            continue
                        try:
                            when = datetime.fromisoformat(row["date"]).astimezone(timezone.utc)
                        except (KeyError, ValueError):
                            continue
                        events.append(CalendarEvent(
                            event_type=etype, title=row.get("title", ""), time=when,
                            currency=row.get("country", ""), impact=row.get("impact", ""),
                            forecast=_num(row.get("forecast")), previous=_num(row.get("previous")),
                        ))
            events.sort(key=lambda e: e.time)
            self._cache.set("ff", events, self._ttl)
            cached = events
        return [e for e in cached if e.time >= since]


class GoogleNewsSource(NewsSource):
    """Wraps the Google News RSS approach into ContextItem objects."""

    URL = "https://news.google.com/rss/search"

    def __init__(self, cache_ttl: float = 600.0) -> None:
        self._cache = _TTLCache()
        self._ttl = cache_ttl

    async def headlines(self, query: str, since: datetime, until: datetime,
                        max_items: int = 25) -> list[ContextItem]:
        import xml.etree.ElementTree as ET
        from datetime import timedelta
        from email.utils import parsedate_to_datetime

        import httpx

        key = f"{query}|{since.date()}|{until.date()}|{max_items}"
        cached = self._cache.get(key, self._ttl)
        if cached is not None:
            return cached
        q = (f"{query} after:{(since - timedelta(days=1)).date()} "
             f"before:{(until + timedelta(days=1)).date()}")
        out: list[ContextItem] = []
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                r = await http.get(self.URL, params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
                r.raise_for_status()
                root = ET.fromstring(r.content)
        except Exception:  # noqa: BLE001
            return []
        for item in root.iterfind(".//item"):
            title = item.findtext("title")
            pub = item.findtext("pubDate")
            if not title or not pub:
                continue
            try:
                ts = parsedate_to_datetime(pub).astimezone(timezone.utc)
            except Exception:  # noqa: BLE001
                continue
            if since <= ts <= until:
                out.append(ContextItem(
                    title=title.strip(), source=item.findtext("source") or "",
                    url=item.findtext("link") or "", published_at=ts,
                ))
        out.sort(key=lambda h: h.published_at or datetime.min.replace(tzinfo=timezone.utc),
                 reverse=True)
        out = out[:max_items]
        self._cache.set(key, out, self._ttl)
        return out

