from __future__ import annotations

from datetime import timezone
from typing import Any

from strategies.base import StrategySignal, atr


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
        now = now.astimezone(timezone.utc)
        session_range = [bar for bar in candles if bar["time"].astimezone(timezone.utc).date() == now.date()
                        and 7 <= bar["time"].astimezone(timezone.utc).hour < 8]
        if now.hour < 8 or len(session_range) < 3:
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
