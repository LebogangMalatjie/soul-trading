from __future__ import annotations

from typing import Any

from strategies.base import StrategySignal, atr, closes, direction_from_momentum, ema


class EURJPYStrategy:
    def describe(self) -> str:
        return "EMA trend continuation with risk-sentiment momentum confirmation"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        values, volatility = closes(data), atr(data)
        fast, slow = ema(values, 20), ema(values, 50)
        risk = int(data.get("risk_sentiment", 0))
        if not fast or not slow or volatility <= 0 or risk == 0:
            return None
        momentum = direction_from_momentum(data)
        last = data["candles"][-1]
        if fast[-1] > slow[-1] and momentum > 0 and risk > 0 \
                and float(last["low"]) <= fast[-1] and float(last["close"]) > fast[-1]:
            return StrategySignal("BUY", "EURJPY trend pullback with risk-on momentum",
                                  volatility, 1.8 * volatility)
        if fast[-1] < slow[-1] and momentum < 0 and risk < 0 \
                and float(last["high"]) >= fast[-1] and float(last["close"]) < fast[-1]:
            return StrategySignal("SELL", "EURJPY trend pullback with risk-off momentum",
                                  volatility, 1.8 * volatility)
        return None


STRATEGY = EURJPYStrategy()
