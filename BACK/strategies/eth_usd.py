from __future__ import annotations

from typing import Any

from strategies.base import StrategySignal, atr, bands, closes, direction_from_momentum


class ETHUSDStrategy:
    def describe(self) -> str:
        return "Bollinger squeeze breakout, BTC lead-lag, weekend momentum and low-volatility range fade"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        values, candles, volatility = closes(data), data.get("candles", []), atr(data)
        lower, middle, upper = bands(values)
        if len(values) < 25 or volatility <= 0:
            return None
        btc = data.get("btc")
        lead = direction_from_momentum(btc) if btc else 0
        last = candles[-1]
        close = float(last["close"])
        now = data.get("now")
        weekend = bool(now and now.weekday() >= 5)
        if volatility / max(close, 1e-9) < 0.0015:
            if close < lower:
                return StrategySignal("BUY", "ETHUSD low-volatility lower-band range entry",
                                      volatility, 1.5 * volatility, target_distance=max(middle - close, volatility))
            if close > upper:
                return StrategySignal("SELL", "ETHUSD low-volatility upper-band range entry",
                                      volatility, 1.5 * volatility, target_distance=max(close - middle, volatility))
            return None
        prior_high = max(float(bar["high"]) for bar in candles[-21:-1])
        prior_low = min(float(bar["low"]) for bar in candles[-21:-1])
        if close > prior_high and lead > 0 and (weekend or lead > 0):
            return StrategySignal("BUY", "ETHUSD squeeze breakout confirmed by BTC lead",
                                  volatility, 2.2 * volatility)
        if close < prior_low and lead < 0 and (weekend or lead < 0):
            return StrategySignal("SELL", "ETHUSD squeeze breakdown confirmed by BTC lead",
                                  volatility, 2.2 * volatility)
        return None


STRATEGY = ETHUSDStrategy()
