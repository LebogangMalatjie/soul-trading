"""Static, lightweight trading configuration for each supported instrument."""
from __future__ import annotations

from dataclasses import dataclass

from schemas import Symbol


@dataclass(frozen=True, slots=True)
class SymbolConfig:
    broker_symbol: str
    strategy: str
    active_sessions_utc: tuple[tuple[int, int], ...]
    timeframes: tuple[str, ...]
    max_spread_points: float
    risk_percent: float
    max_open_positions: int
    trailing_exit_mode: str
    enabled_by_default: bool
    paper_mode: bool = True


_FX = ("1m", "5m", "15m", "1h", "4h")
_INDEX = ("1m", "5m", "15m", "1h")
_CONTINUOUS = ((0, 24),)

SYMBOLS: dict[Symbol, SymbolConfig] = {
    Symbol.XAUUSD: SymbolConfig("XAUUSD", "Existing metals strategy", _CONTINUOUS, _FX, 80, 0.5, 1, "profit_ladder", True, False),
    Symbol.XAGUSD: SymbolConfig("XAGUSD", "Existing metals strategy", _CONTINUOUS, _FX, 80, 0.5, 1, "profit_ladder", True, False),
    Symbol.US30: SymbolConfig("US30", "Existing US30 strategy", ((13, 21),), _INDEX, 30, 0.5, 1, "profit_ladder", True, False),
    Symbol.BTCUSD: SymbolConfig("BTCUSD", "Existing BTC squeeze strategy", _CONTINUOUS, _FX, 120, 0.5, 1, "profit_ladder", True, False),
    Symbol.EURUSD: SymbolConfig("EURUSD", "EURUSD multi-session range/breakout", ((0, 8), (13, 17)), _FX, 20, 0.25, 1, "profit_ladder", False, False),
    Symbol.USDJPY: SymbolConfig("USDJPY", "EMA trend pullback", ((0, 8), (7, 16)), _FX, 25, 0.25, 1, "profit_ladder", False, False),
    Symbol.GBPUSD: SymbolConfig("GBPUSD", "London-open range breakout", ((7, 12),), _FX, 25, 0.25, 1, "profit_ladder", False, False),
    Symbol.USDCHF: SymbolConfig("USDCHF", "Bollinger/RSI range reversion", ((7, 16),), _FX, 25, 0.2, 1, "fixed_target", False, False),
    Symbol.AUDUSD: SymbolConfig("AUDUSD", "Asian range with risk filter", ((0, 8),), _FX, 25, 0.2, 1, "profit_ladder", False, False),
    Symbol.USDCAD: SymbolConfig("USDCAD", "Trend with USOIL correlation filter", ((13, 21),), _FX, 25, 0.2, 1, "profit_ladder", False, False),
    Symbol.NZDUSD: SymbolConfig("NZDUSD", "Asian range scalping", ((0, 7),), _FX, 25, 0.15, 1, "profit_ladder", False, False),
    Symbol.EURGBP: SymbolConfig("EURGBP", "EURGBP fixed-target mean reversion", ((7, 16),), _FX, 25, 0.15, 1, "fixed_target", False, False),
    Symbol.EURJPY: SymbolConfig("EURJPY", "Trend with risk-sentiment momentum", ((0, 8), (7, 16)), _FX, 30, 0.2, 1, "profit_ladder", False, False),
    Symbol.GBPJPY: SymbolConfig("GBPJPY", "ATR/Bollinger squeeze breakout", ((7, 16),), _FX, 35, 0.2, 1, "atr", False, False),
    Symbol.US100: SymbolConfig("US100", "NY-open breakout/VWAP pullback", ((13, 21),), _INDEX, 35, 0.2, 1, "profit_ladder", False, False),
    Symbol.US500: SymbolConfig("US500", "Trend pullback/VWAP reversion", ((13, 21),), _INDEX, 25, 0.2, 1, "profit_ladder", False, False),
    Symbol.GER40: SymbolConfig("GER40", "Frankfurt/London breakout and gap fill", ((7, 16),), _INDEX, 35, 0.2, 1, "profit_ladder", False, False),
    Symbol.USOIL: SymbolConfig("USOIL", "Momentum breakout with EIA event filter", ((13, 21),), _FX, 35, 0.2, 1, "profit_ladder", False, False),
    Symbol.ETHUSD: SymbolConfig("ETHUSD", "ETH squeeze/BTC lead-lag/weekend", _CONTINUOUS, _FX, 100, 0.2, 1, "profit_ladder", False, False),
}


def config_for(symbol: Symbol) -> SymbolConfig:
    return SYMBOLS[symbol]


def default_control(symbol: Symbol) -> tuple[bool, str]:
    config = config_for(symbol)
    return config.enabled_by_default, "active" if config.enabled_by_default else "off"
