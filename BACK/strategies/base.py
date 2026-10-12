"""Small synchronous strategy plug-in contract; implementations must not do I/O."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class StrategySignal:
    direction: str
    reason: str
    atr_value: float
    stop_distance: float
    take_profit: float | None = None
    target_distance: float | None = None


class StrategyPlugin(Protocol):
    def should_enter(self, data: dict[str, Any]) -> StrategySignal | None: ...

    def manage_position(self, position: dict[str, Any], data: dict[str, Any]) -> dict[str, Any] | None: ...

    def describe(self) -> str: ...


def closes(data: dict[str, Any]) -> list[float]:
    return [float(bar["close"]) for bar in data.get("candles", [])]


def ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    result = [sum(values[:period]) / period]
    alpha = 2 / (period + 1)
    for value in values[period:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def atr(data: dict[str, Any], period: int = 14) -> float:
    candles = data.get("candles", [])
    if len(candles) < period + 1:
        return 0.0
    ranges = []
    for previous, current in zip(candles[-period - 1:-1], candles[-period:]):
        ranges.append(max(
            float(current["high"]) - float(current["low"]),
            abs(float(current["high"]) - float(previous["close"])),
            abs(float(current["low"]) - float(previous["close"])),
        ))
    return sum(ranges) / len(ranges)


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    changes = [current - previous for previous, current in zip(values[-period - 1:-1], values[-period:])]
    gains = sum(max(value, 0.0) for value in changes) / period
    losses = sum(max(-value, 0.0) for value in changes) / period
    return 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)


def bands(values: list[float], period: int = 20, deviation: float = 2.0) -> tuple[float, float, float]:
    if len(values) < period:
        return 0.0, 0.0, 0.0
    sample = values[-period:]
    mean = sum(sample) / period
    variance = sum((value - mean) ** 2 for value in sample) / period
    width = deviation * variance ** 0.5
    return mean - width, mean, mean + width


def direction_from_momentum(data: dict[str, Any]) -> int:
    values = closes(data)
    if len(values) < 2:
        return 0
    return 1 if values[-1] > values[-2] else -1 if values[-1] < values[-2] else 0
