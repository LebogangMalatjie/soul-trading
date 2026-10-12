from __future__ import annotations

from typing import Any

from strategies.base import StrategySignal, atr, closes, ema, direction_from_momentum


class USDCADStrategy:
    def describe(self) -> str:
        return "Trend-following pullback filtered by inverse USOIL momentum"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        values = closes(data)
        oil = data.get("usoil")
        fast, slow, volatility = ema(values, 20), ema(values, 50), atr(data)
        oil_momentum = direction_from_momentum(oil) if oil else 0
        if not fast or not slow or volatility <= 0 or oil_momentum == 0:
            return None
        last = data["candles"][-1]
        if fast[-1] > slow[-1] and oil_momentum < 0 and float(last["low"]) <= fast[-1] \
                and float(last["close"]) > fast[-1]:
            return StrategySignal("BUY", "USDCAD pullback with inverse USOIL confirmation",
                                  volatility, 1.8 * volatility)
        if fast[-1] < slow[-1] and oil_momentum > 0 and float(last["high"]) >= fast[-1] \
                and float(last["close"]) < fast[-1]:
            return StrategySignal("SELL", "USDCAD pullback with inverse USOIL confirmation",
                                  volatility, 1.8 * volatility)
        return None


STRATEGY = USDCADStrategy()
