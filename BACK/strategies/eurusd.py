"""EURUSD Asian range fade, overlap breakout, and liquidity-sweep reversal."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from strategies.base import StrategySignal


class EURUSDStrategy:
    def describe(self) -> str:
        return "Asian-session range fade, London/NY overlap breakout, liquidity-sweep reversal"

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> None:
        return None

    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None:
        bars = data.get("candles")
        now = data.get("now")
        if not isinstance(bars, list) or not isinstance(now, datetime) or len(bars) < 22:
            return None
        if now.tzinfo is None:
            raise ValueError("strategy time must be timezone-aware")
        now = now.astimezone(timezone.utc)
        usable = [bar for bar in bars if isinstance(bar.get("time"), datetime)
                  and bar["time"].astimezone(timezone.utc) < now]
        if len(usable) < 22:
            return None
        current = usable[-1]
        ranges = [max(float(bar["high"]) - float(bar["low"]), 0.0) for bar in usable[-20:]]
        atr_value = sum(ranges) / len(ranges)
        if atr_value <= 0:
            return None
        latest = current["time"].astimezone(timezone.utc)

        asian = [bar for bar in usable
                 if bar["time"].astimezone(timezone.utc).date() == latest.date()
                 and 0 <= bar["time"].astimezone(timezone.utc).hour < 6]
        if latest.hour in range(6, 8) and len(asian) >= 4:
            high = max(float(bar["high"]) for bar in asian)
            low = min(float(bar["low"]) for bar in asian)
            close = float(current["close"])
            if close >= high - 0.15 * atr_value:
                return StrategySignal("SELL", "Asian range upper-edge fade", atr_value, 1.5 * atr_value)
            if close <= low + 0.15 * atr_value:
                return StrategySignal("BUY", "Asian range lower-edge fade", atr_value, 1.5 * atr_value)

        if 13 <= latest.hour < 17 and len(usable) >= 25:
            reference = usable[-25:-5]
            high = max(float(bar["high"]) for bar in reference)
            low = min(float(bar["low"]) for bar in reference)
            close = float(current["close"])
            body = close - float(current["open"])
            if close > high and body > 0.35 * atr_value:
                return StrategySignal("BUY", "London/NY overlap range breakout", atr_value, 1.8 * atr_value)
            if close < low and body < -0.35 * atr_value:
                return StrategySignal("SELL", "London/NY overlap range breakout", atr_value, 1.8 * atr_value)

        recent = usable[-21:-1]
        prior_high = max(float(bar["high"]) for bar in recent)
        prior_low = min(float(bar["low"]) for bar in recent)
        high, low, close = float(current["high"]), float(current["low"]), float(current["close"])
        if high > prior_high and close < prior_high:
            return StrategySignal("SELL", "Liquidity sweep above recent range", atr_value, 1.5 * atr_value)
        if low < prior_low and close > prior_low:
            return StrategySignal("BUY", "Liquidity sweep below recent range", atr_value, 1.5 * atr_value)
        return None


STRATEGY = EURUSDStrategy()
