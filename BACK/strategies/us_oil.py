from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from strategies.base import StrategySignal, atr


class USOILStrategy:
    def describe(self) -> str:
        return "Momentum breakout with Wednesday EIA inventory-event blackout"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        now = data.get("now")
        candles, volatility = data.get("candles", []), atr(data)
        if not isinstance(now, datetime) or now.tzinfo is None or len(candles) < 25 or volatility <= 0:
            return None
        eastern = now.astimezone(ZoneInfo("America/New_York"))
        if data.get("eia_blackout") or (eastern.weekday() == 2 and 10 <= eastern.hour <= 11):
            return None
        prior = candles[-21:-1]
        high, low = max(float(bar["high"]) for bar in prior), min(
            float(bar["low"]) for bar in prior)
        last = candles[-1]
        body = float(last["close"]) - float(last["open"])
        if float(last["close"]) > high and body > 0.25 * volatility:
            return StrategySignal("BUY", "USOIL momentum breakout outside EIA event window",
                                  volatility, 2 * volatility)
        if float(last["close"]) < low and body < -0.25 * volatility:
            return StrategySignal("SELL", "USOIL momentum breakout outside EIA event window",
                                  volatility, 2 * volatility)
        return None


STRATEGY = USOILStrategy()
