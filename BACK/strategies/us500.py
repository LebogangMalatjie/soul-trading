from __future__ import annotations

from typing import Any

from strategies.base import StrategySignal, atr, closes, ema


class US500Strategy:
    def describe(self) -> str:
        return "Trend pullback with VWAP mean-reversion confirmation"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        values, candles, volatility = closes(data), data.get("candles", []), atr(data)
        fast, slow = ema(values, 20), ema(values, 50)
        if not fast or not slow or volatility <= 0:
            return None
        sample = candles[-20:]
        volume = sum(max(float(bar.get("volume", 0)), 1.0) for bar in sample)
        vwap = sum(
            (float(bar["high"]) + float(bar["low"]) + float(bar["close"])) / 3
            * max(float(bar.get("volume", 0)), 1.0) for bar in sample
        ) / volume
        last = candles[-1]
        close = float(last["close"])
        if fast[-1] > slow[-1] and float(last["low"]) <= fast[-1] and close > fast[-1] and close >= vwap:
            return StrategySignal("BUY", "US500 uptrend pullback reclaiming EMA/VWAP",
                                  volatility, 1.8 * volatility)
        if fast[-1] < slow[-1] and float(last["high"]) >= fast[-1] and close < fast[-1] and close <= vwap:
            return StrategySignal("SELL", "US500 downtrend pullback rejecting EMA/VWAP",
                                  volatility, 1.8 * volatility)
        if close < vwap and close > fast[-1] and fast[-1] > slow[-1]:
            return StrategySignal("BUY", "US500 VWAP mean reversion aligned to trend",
                                  volatility, 1.6 * volatility)
        if close > vwap and close < fast[-1] and fast[-1] < slow[-1]:
            return StrategySignal("SELL", "US500 VWAP mean reversion aligned to trend",
                                  volatility, 1.6 * volatility)
        return None


STRATEGY = US500Strategy()
