from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from strategies.base import StrategySignal, atr

_LONDON = ZoneInfo("Europe/London")


class GBPUSDStrategy:
    def describe(self) -> str:
        return "London-open range breakout with momentum continuation"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        candles, now = data.get("candles", []), data.get("now")
        volatility = atr(data)
        if len(candles) < 25 or volatility <= 0 or now is None:
            return None
        if now.tzinfo is None:
            return None
        london = now.astimezone(_LONDON)
        # Opening range = the first London hour (08:00-09:00 local, DST-aware), so the
        # range tracks the actual London open year-round instead of a fixed UTC hour.
        session_range = [bar for bar in candles
                         if bar["time"].astimezone(_LONDON).date() == london.date()
                         and 8 <= bar["time"].astimezone(_LONDON).hour < 9]
        if london.hour < 9 or len(session_range) < 3:
            return None
        high, low = max(float(bar["high"]) for bar in session_range), min(
            float(bar["low"]) for bar in session_range)
        last = candles[-1]
        body = float(last["close"]) - float(last["open"])
        if float(last["close"]) > high and body > 0.3 * volatility:
            return StrategySignal("BUY", "GBPUSD London-open range breakout", volatility, 1.8 * volatility)
        if float(last["close"]) < low and body < -0.3 * volatility:
            return StrategySignal("SELL", "GBPUSD London-open range breakout", volatility, 1.8 * volatility)
        return None


STRATEGY = GBPUSDStrategy()
