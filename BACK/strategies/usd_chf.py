from __future__ import annotations

from typing import Any

from strategies.base import StrategySignal, atr, bands, closes, ema, rsi


class USDCHFStrategy:
    def describe(self) -> str:
        return "Range-filtered Bollinger/RSI mean reversion with fixed target"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        values = closes(data)
        candles = data.get("candles", [])
        volatility = atr(data)
        lower, mean, upper = bands(values)
        average = ema(values, 50)
        if len(values) < 60 or not average or volatility <= 0:
            return None
        # Trend guard: skip when the 50-EMA slope over the last 5 bars is strong
        # (a trending market is a poor mean-reversion candidate). 1.0x ATR keeps the
        # filter from suppressing genuine Bollinger+RSI reversion in mild drift.
        if abs(average[-1] - average[-6]) > volatility * 1.0:
            return None
        close = values[-1]
        if close < lower and rsi(values) < 30:
            return StrategySignal("BUY", "USDCHF oversold Bollinger range reversion", volatility,
                                  1.4 * volatility, target_distance=max(mean - close, volatility))
        if close > upper and rsi(values) > 70:
            return StrategySignal("SELL", "USDCHF overbought Bollinger range reversion", volatility,
                                  1.4 * volatility, target_distance=max(close - mean, volatility))
        return None


STRATEGY = USDCHFStrategy()
