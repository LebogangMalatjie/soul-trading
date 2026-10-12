from __future__ import annotations

from typing import Any

from strategies.base import StrategySignal, atr, bands, closes


class GBPJPYStrategy:
    def describe(self) -> str:
        return "Bollinger volatility-squeeze breakout with wide ATR stop"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        values, candles, volatility = closes(data), data.get("candles", []), atr(data)
        lower, middle, upper = bands(values)
        previous_lower, _, previous_upper = bands(values[:-1])
        if len(values) < 45 or volatility <= 0 or not previous_upper:
            return None
        prior_width = (previous_upper - previous_lower) / max(abs(values[-2]), 1e-9)
        current_width = (upper - lower) / max(abs(values[-1]), 1e-9)
        if prior_width > 0.012 or current_width <= prior_width:
            return None
        last = candles[-1]
        if float(last["close"]) > upper and float(last["close"]) > middle:
            return StrategySignal("BUY", "GBPJPY Bollinger squeeze upside breakout", volatility,
                                  2.8 * volatility)
        if float(last["close"]) < lower and float(last["close"]) < middle:
            return StrategySignal("SELL", "GBPJPY Bollinger squeeze downside breakout", volatility,
                                  2.8 * volatility)
        return None


STRATEGY = GBPJPYStrategy()
