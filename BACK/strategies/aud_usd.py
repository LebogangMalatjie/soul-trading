from __future__ import annotations

from datetime import timezone
from typing import Any

from strategies.base import StrategySignal, atr


class AUDUSDStrategy:
    def describe(self) -> str:
        return "Asian range fade filtered by risk-on/risk-off sentiment"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        candles, now = data.get("candles", []), data.get("now")
        volatility = atr(data)
        sentiment = int(data.get("risk_sentiment", 0))
        if len(candles) < 22 or now is None or volatility <= 0 or sentiment == 0:
            return None
        now = now.astimezone(timezone.utc)
        recent = [bar for bar in candles if bar["time"].astimezone(timezone.utc).date() == now.date()
                  and bar["time"].astimezone(timezone.utc).hour < 4]
        if now.hour not in range(4, 8) or len(recent) < 4:
            return None
        high, low = max(float(bar["high"]) for bar in recent), min(float(bar["low"]) for bar in recent)
        close = float(candles[-1]["close"])
        if sentiment > 0 and close <= low + 0.15 * volatility:
            return StrategySignal("BUY", "AUDUSD Asian range lower entry with risk-on filter",
                                  volatility, 1.5 * volatility)
        if sentiment < 0 and close >= high - 0.15 * volatility:
            return StrategySignal("SELL", "AUDUSD Asian range upper entry with risk-off filter",
                                  volatility, 1.5 * volatility)
        return None


STRATEGY = AUDUSDStrategy()
