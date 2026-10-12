from __future__ import annotations

from typing import Any

from strategies.base import StrategySignal, atr, bands, closes, rsi


class EURGBPStrategy:
    def describe(self) -> str:
        return "EURGBP range mean reversion with fixed target"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        values, volatility = closes(data), atr(data)
        lower, mean, upper = bands(values, 20, 2.0)
        if len(values) < 25 or volatility <= 0:
            return None
        if values[-1] < lower and rsi(values) < 32:
            return StrategySignal("BUY", "EURGBP lower-band mean reversion", volatility,
                                  1.3 * volatility, target_distance=max(mean - values[-1], volatility))
        if values[-1] > upper and rsi(values) > 68:
            return StrategySignal("SELL", "EURGBP upper-band mean reversion", volatility,
                                  1.3 * volatility, target_distance=max(values[-1] - mean, volatility))
        return None


STRATEGY = EURGBPStrategy()
