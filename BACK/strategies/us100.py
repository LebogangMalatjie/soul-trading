from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from strategies.base import StrategySignal, atr


class US100Strategy:
    def describe(self) -> str:
        return "NY-open range breakout and VWAP pullback"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        candles, now = data.get("candles", []), data.get("now")
        volatility = atr(data)
        if len(candles) < 30 or now is None or volatility <= 0:
            return None
        now = now.astimezone(ZoneInfo("America/New_York"))
        today = [bar for bar in candles if bar["time"].astimezone(ZoneInfo("America/New_York")).date() == now.date()]
        opening = [
            bar for bar in today
            if 9 <= bar["time"].astimezone(ZoneInfo("America/New_York")).hour < 10
        ]
        if now.hour < 10 or len(opening) < 3:
            return None
        high, low = max(float(bar["high"]) for bar in opening), min(float(bar["low"]) for bar in opening)
        recent = candles[-12:]
        weight = sum(max(float(bar.get("volume", 0)), 1.0) for bar in recent)
        vwap = sum(
            ((float(bar["high"]) + float(bar["low"]) + float(bar["close"])) / 3)
            * max(float(bar.get("volume", 0)), 1.0) for bar in recent
        ) / weight
        last = candles[-1]
        close = float(last["close"])
        if close > high and close >= vwap:
            return StrategySignal("BUY", "US100 NY-open range breakout above VWAP",
                                  volatility, 2 * volatility)
        if close < low and close <= vwap:
            return StrategySignal("SELL", "US100 NY-open range breakout below VWAP",
                                  volatility, 2 * volatility)
        return None


STRATEGY = US100Strategy()
