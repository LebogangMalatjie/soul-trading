"""Configuration for the News Event Bias Engine.

All values are plain data so they can be overridden from the dashboard/env
later. Defaults are deliberately conservative; the whole engine is dry-run
until explicitly turned on.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Which symbols each high-impact event type may trade. Extend freely.
# Defaults per the brief: NFP and CPI on XAUUSD, US30, EURUSD.
EVENT_SYMBOL_MAP: dict[str, tuple[str, ...]] = {
    "NFP": ("XAUUSD", "US30", "EURUSD"),
    "CPI": ("XAUUSD", "US30", "EURUSD"),
    "PPI": ("XAUUSD", "EURUSD"),
    "FOMC": ("XAUUSD", "US30", "EURUSD"),
    "GDP": ("EURUSD", "US30"),
    "RETAIL_SALES": ("EURUSD", "US30"),
    "JOBLESS_CLAIMS": ("EURUSD",),
    "CB_SPEECH": ("EURUSD",),
    "GEOPOLITICAL": ("XAUUSD", "USOIL"),
}

# Event types the engine recognises (superset of the legacy 4).
KNOWN_EVENT_TYPES: tuple[str, ...] = (
    "NFP", "CPI", "PPI", "FOMC", "GDP", "RETAIL_SALES", "JOBLESS_CLAIMS",
    "CB_SPEECH", "GEOPOLITICAL",
)


@dataclass(frozen=True, slots=True)
class SymbolBiasConfig:
    # Spike buffer: min entry distance = max of the four components below.
    atr_mult: float = 1.0                 # (a) X * ATR(14) on 5m
    spread_mult: float = 10.0             # (b) Y * avg spread during prior 3 releases
    stops_level_margin_points: float = 5.0  # (c) broker SYMBOL_TRADE_STOPS_LEVEL + margin
    fakeout_mult: float = 1.0             # (d) typical fake-out size from history
    ladder_spacing_atr5: float = 0.5      # spacing after first order = 0.5 * ATR(5m)
    # Exits
    sl_points: float | None = None        # per-order SL distance in points; None -> derived
    sl_atr_mult: float = 2.0              # used when sl_points is None
    pending_expiry_minutes: int = 15      # cancel unfilled orders this long after the event
    max_hold_minutes: int = 120           # fallback if target not reached in time
    fallback: str = "trail"               # "trail" (hand to ladder trailing stop) | "close"


@dataclass(frozen=True, slots=True)
class BiasEngineConfig:
    enabled: bool = False                 # master switch (dry-run until turned on)
    dry_run: bool = True                  # global dry-run: log plan, place no orders
    target_zar: float = 15000.0           # R15,000 basket target (configurable)
    # Regeneration / lock / confirm timing (minutes relative to event time T).
    regen_offsets: tuple[int, ...] = (-30, -15, -6)
    lock_offset_minutes: int = 5          # bias locked at T-5m
    place_offset_minutes: int = 5         # orders placed at T-5m after confirm
    confirm_cutoff_seconds: int = 60      # no action by T-60s -> place nothing
    min_probability_pct: float = 55.0     # below this -> NO_TRADE
    min_history_sample: int = 5           # need >= this many past reactions to trust history
    context_lookback_hours: int = 72
    zar_fallback_rate: float = 18.0       # USD->ZAR fallback if MT5 USDZAR unavailable
    # After an event releases, record the real 1m/5m/15m reaction this many minutes later.
    outcome_capture_minutes: int = 16
    # Catch-up window: on connect/refresh, capture outcomes for events the bot missed.
    outcome_sweep_hours: int = 12
    per_symbol: dict[str, SymbolBiasConfig] = field(default_factory=dict)

    def for_symbol(self, symbol: str) -> SymbolBiasConfig:
        return self.per_symbol.get(symbol, SymbolBiasConfig())


DEFAULT_CONFIG = BiasEngineConfig()
