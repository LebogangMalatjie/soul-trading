from __future__ import annotations

from datetime import timezone
from typing import Any

from strategies.base import StrategySignal, atr


class NZDUSDStrategy:
    def describe(self) -> str:
        return "Asian-session range-edge scalping"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        candles, now = data.get("candles", []), data.get("now")
        volatility = atr(data)
        if len(candles) < 22 or now is None or volatility <= 0:
            return None
        now = now.astimezone(timezone.utc)
        range_bars = [bar for bar in candles if bar["time"].astimezone(timezone.utc).date() == now.date()
                      and bar["time"].astimezone(timezone.utc).hour < 3]
        if now.hour not in range(3, 7) or len(range_bars) < 4:
            return None
        high, low = max(float(bar["high"]) for bar in range_bars), min(
            float(bar["low"]) for bar in range_bars)
        close = float(candles[-1]["close"])
        if close >= high - 0.1 * volatility:
            return StrategySignal("SELL", "NZDUSD Asian range upper-edge scalp", volatility, volatility)
        if close <= low + 0.1 * volatility:
            return StrategySignal("BUY", "NZDUSD Asian range lower-edge scalp", volatility, volatility)
        return None


STRATEGY = NZDUSDStrategy()
