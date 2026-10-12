from __future__ import annotations

from typing import Any

from strategies.base import StrategySignal, atr, closes, ema


class USDJPYStrategy:
    def describe(self) -> str:
        return "EMA trend filter with pullback entry"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        candles, values = data.get("candles", []), closes(data)
        fast, slow, volatility = ema(values, 20), ema(values, 50), atr(data)
        if not fast or not slow or volatility <= 0:
            return None
        last = candles[-1]
        if fast[-1] > slow[-1] and float(last["low"]) <= fast[-1] \
                and float(last["close"]) > fast[-1] and float(last["close"]) > float(last["open"]):
            return StrategySignal("BUY", "USDJPY EMA uptrend pullback reclaimed EMA20", volatility, 1.8 * volatility)
        if fast[-1] < slow[-1] and float(last["high"]) >= fast[-1] \
                and float(last["close"]) < fast[-1] and float(last["close"]) < float(last["open"]):
            return StrategySignal("SELL", "USDJPY EMA downtrend pullback rejected EMA20", volatility, 1.8 * volatility)
        return None


STRATEGY = USDJPYStrategy()
