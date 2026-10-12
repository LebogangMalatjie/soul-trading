from __future__ import annotations

from datetime import timezone
from typing import Any

from strategies.base import StrategySignal, atr


class GER40Strategy:
    def describe(self) -> str:
        return "Frankfurt/London open range breakout and gap-fill"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        candles, now = data.get("candles", []), data.get("now")
        volatility = atr(data)
        if len(candles) < 25 or now is None or volatility <= 0:
            return None
        now = now.astimezone(timezone.utc)
        opening = [bar for bar in candles if bar["time"].astimezone(timezone.utc).date() == now.date()
                   and 7 <= bar["time"].astimezone(timezone.utc).hour < 8]
        if now.hour < 8 or len(opening) < 3:
            return None
        high, low = max(float(bar["high"]) for bar in opening), min(
            float(bar["low"]) for bar in opening)
        prior_close = float(candles[-25]["close"])
        open_price = float(opening[0]["open"])
        last_close = float(candles[-1]["close"])
        if abs(open_price - prior_close) > 0.4 * volatility and \
                (last_close - prior_close) * (open_price - prior_close) < 0:
            side = "BUY" if last_close > prior_close else "SELL"
            return StrategySignal(side, "GER40 overnight gap-fill toward prior close",
                                  volatility, 1.8 * volatility)
        if last_close > high:
            return StrategySignal("BUY", "GER40 Frankfurt/London opening-range breakout",
                                  volatility, 2 * volatility)
        if last_close < low:
            return StrategySignal("SELL", "GER40 Frankfurt/London opening-range breakout",
                                  volatility, 2 * volatility)
        return None


STRATEGY = GER40Strategy()
