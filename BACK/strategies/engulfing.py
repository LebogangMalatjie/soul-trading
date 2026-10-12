"""Pure detection and request-building helpers for engulfing candles.

Input frames follow MT5's ``copy_rates_from_pos`` layout: oldest first, with the
still-forming candle at ``iloc[-1]``. Detection therefore uses ``iloc[-3]`` and
``iloc[-2]`` only.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Mapping, Optional

DEFAULT_CONFIG: dict[str, Any] = {
    "paper_mode": True,
    "timeframes": ("1h", "30m"),
    "atr_period": 14,
    "min_body_atr_mult": 0.5,
    "min_engulf_ratio": 1.2,
    "use_min_body_filter": True,
    "use_engulf_strength_filter": True,
    "use_trend_filter": True,
    "ema_period": 50,
    "use_location_filter": True,
    "swing_lookback": 10,
    "swing_tolerance_atr_mult": 0.25,
    "use_higher_timeframe_confirmation": True,
    "use_session_filter": True,
    "use_news_filter": True,
    "use_spread_filter": True,
    "max_spread_points": 100.0,
    "use_cooldown": True,
    "cooldown_candles": 3,
    "sl_atr_buffer": 0.2,
    "rr_ratio": 2.0,
    "max_sl_atr_mult": 2.5,
    "risk_per_trade_pct": 1.0,
    "symbol_overrides": {
        "XAUUSD": {"max_spread_points": 80.0, "min_body_atr_mult": 0.55},
        "XAGUSD": {
            "max_spread_points": 100.0, "min_body_atr_mult": 0.6,
            "swing_lookback": 12, "sl_atr_buffer": 0.25,
        },
        "BTCUSD": {
            "max_spread_points": 2500.0, "min_body_atr_mult": 0.7,
            "min_engulf_ratio": 1.3, "cooldown_candles": 4,
        },
        "US30": {
            "max_spread_points": 100.0, "min_body_atr_mult": 0.6,
            "swing_lookback": 12,
        },
    },
}

_OHLC = ("open", "high", "low", "close")


def _records(frame: Any) -> list[dict[str, float]]:
    if frame is None or len(frame) < 3:
        return []
    try:
        missing = [column for column in _OHLC if column not in frame.columns]
        if missing:
            raise ValueError(f"OHLC data is missing columns: {', '.join(missing)}")
        rows = frame.loc[:, list(_OHLC)].to_dict("records")
        result = [{key: float(row[key]) for key in _OHLC} for row in rows]
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("OHLC data is missing"):
            raise
        raise ValueError("OHLC data must be a pandas DataFrame with numeric prices") from exc
    if any(not math.isfinite(value) for row in result for value in row.values()):
        raise ValueError("OHLC data contains non-finite prices")
    if any(row["high"] < row["low"] for row in result):
        raise ValueError("OHLC data contains a high below its low")
    return result


def _atr(rows: list[dict[str, float]], period: int) -> float:
    closed = rows[:-1]
    if len(closed) < period + 1:
        return 0.0
    ranges = []
    for previous, current in zip(closed, closed[1:]):
        ranges.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        ))
    if len(ranges) < period:
        return 0.0
    value = sum(ranges[:period]) / period
    for current in ranges[period:]:
        value = (value * (period - 1) + current) / period
    return value


def _ema(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    alpha = 2 / (period + 1)
    value = values[0]
    for current in values[1:]:
        value = current * alpha + value * (1 - alpha)
    return value


def _merge_config(symbol: str, config: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    merged = {key: value for key, value in DEFAULT_CONFIG.items() if key != "symbol_overrides"}
    merged.update(DEFAULT_CONFIG["symbol_overrides"].get(symbol, {}))
    if config:
        merged.update({key: value for key, value in config.items() if key != "symbol_overrides"})
        overrides = config.get("symbol_overrides", {})
        if isinstance(overrides, Mapping) and isinstance(overrides.get(symbol), Mapping):
            merged.update(overrides[symbol])
    return merged


def detect_engulfing(df: Any) -> Optional[dict[str, Any]]:
    """Return a raw engulfing setup from closed candles, without broker side effects.

    The last row is the forming candle and is never used as signal data. The
    previous closed candle is at ``-3`` and the engulfing candle at ``-2``.
    """
    rows = _records(df)
    if len(rows) < 16:
        return None
    c1, c2, next_candle = rows[-3], rows[-2], rows[-1]
    atr_value = _atr(rows, 14)
    if atr_value <= 0:
        return None

    direction: Optional[str] = None
    if (c1["close"] < c1["open"] and c2["close"] > c2["open"]
            and c2["open"] <= c1["close"] and c2["close"] >= c1["open"]):
        direction = "BUY"
    elif (c1["close"] > c1["open"] and c2["close"] < c2["open"]
            and c2["open"] >= c1["close"] and c2["close"] <= c1["open"]):
        direction = "SELL"
    if direction is None:
        return None

    sign = 1 if direction == "BUY" else -1
    entry = next_candle["open"]
    buffer = 0.2 * atr_value
    sl = c2["low"] - buffer if sign > 0 else c2["high"] + buffer
    risk = abs(entry - sl)
    if not math.isfinite(risk) or risk <= 0:
        return None
    return {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": entry + sign * risk * 2.0,
        "reason": f"{direction.lower()} engulfing candle",
    }


def calculate_volume(equity: float, entry: float, sl: float, symbol_info: Any,
                     risk_per_trade_pct: float = 1.0) -> float:
    """Size volume with broker tick values, then round down and clamp to broker limits."""
    tick_size = float(getattr(symbol_info, "trade_tick_size", getattr(symbol_info, "tick_size", 0.0)))
    tick_value = float(getattr(symbol_info, "trade_tick_value", getattr(symbol_info, "tick_value", 0.0)))
    volume_step = float(getattr(symbol_info, "volume_step", 0.0))
    volume_min = float(getattr(symbol_info, "volume_min", 0.0))
    volume_max = float(getattr(symbol_info, "volume_max", 0.0))
    risk_amount = equity * risk_per_trade_pct / 100.0
    values = (equity, entry, sl, risk_per_trade_pct, tick_size, tick_value,
              volume_step, volume_min, volume_max, risk_amount)
    if any(not math.isfinite(value) for value in values) or \
            min(tick_size, tick_value, volume_step, volume_min, volume_max, risk_amount) <= 0:
        return 0.0
    loss_per_lot = abs(entry - sl) / tick_size * tick_value
    if loss_per_lot <= 0:
        return 0.0
    raw = risk_amount / loss_per_lot
    decimals = max(0, min(8, -Decimal(str(volume_step)).normalize().as_tuple().exponent))
    rounded = math.floor(raw / volume_step + 1e-9) * volume_step
    if rounded < volume_min:
        fallback_volume = 0.01
        fallback_steps = (fallback_volume - volume_min) / volume_step
        if fallback_volume < volume_min or fallback_volume > volume_max or \
                not math.isclose(fallback_steps, round(fallback_steps), rel_tol=0.0, abs_tol=1e-8):
            return 0.0
        return round(fallback_volume, decimals)
    return round(min(rounded, volume_max), decimals)


def build_trade_request(
    df: Any,
    *,
    symbol: str,
    timeframe: str,
    config: Optional[Mapping[str, Any]] = None,
    higher_timeframe_df: Any = None,
    spread_points: Optional[float] = None,
    allowed_session: bool = True,
    in_news_blackout: bool = False,
    cooldown_remaining: int = 0,
    open_position_directions: tuple[str, ...] = (),
    equity: Optional[float] = None,
    symbol_info: Any = None,
) -> Optional[dict[str, Any]]:
    """Apply configurable quality/risk gates and return an accepted or rejected request."""
    base = detect_engulfing(df)
    if base is None:
        return None
    cfg = _merge_config(symbol, config)
    rows = _records(df)
    c1, c2 = rows[-3], rows[-2]
    base.update({
        "atr": _atr(rows, 14),
        "c1_body": abs(c1["close"] - c1["open"]),
        "c2_body": abs(c2["close"] - c2["open"]),
        "c1_low": c1["low"],
        "c1_high": c1["high"],
        "c2_close": c2["close"],
    })
    buffer = float(cfg["sl_atr_buffer"]) * base["atr"]
    if base["direction"] == "BUY":
        base["sl"] = c2["low"] - buffer
        sign = 1
    else:
        base["sl"] = c2["high"] + buffer
        sign = -1
    risk = abs(base["entry"] - base["sl"])
    base["tp"] = base["entry"] + sign * risk * float(cfg["rr_ratio"])
    reason: Optional[str] = None

    if cfg["use_min_body_filter"] and base["c2_body"] < cfg["min_body_atr_mult"] * base["atr"]:
        reason = "candle body below minimum ATR threshold"
    elif cfg["use_engulf_strength_filter"] and (
        base["c2_body"] < cfg["min_engulf_ratio"] * base["c1_body"]
    ):
        reason = "engulf body below minimum strength ratio"
    elif cfg["use_trend_filter"]:
        closes = [row["close"] for row in rows[:-1]]
        trend_ema = _ema(closes, int(cfg["ema_period"]))
        if trend_ema is None:
            reason = f"not enough candles for EMA{cfg['ema_period']}"
        elif (base["direction"] == "BUY" and base["c2_close"] <= trend_ema) or (
            base["direction"] == "SELL" and base["c2_close"] >= trend_ema
        ):
            reason = f"engulf rejected by EMA{cfg['ema_period']} trend filter"
    if reason is None and cfg["use_location_filter"]:
        lookback = int(cfg["swing_lookback"])
        look = rows[-(lookback + 3):-3]
        if len(look) < lookback:
            reason = "not enough candles for swing-location filter"
        else:
            tolerance = float(cfg["swing_tolerance_atr_mult"]) * base["atr"]
            if (base["direction"] == "BUY"
                    and base["c1_low"] - min(row["low"] for row in look) > tolerance):
                reason = f"engulf rejected: c1 is not near a {lookback}-candle swing low"
            elif (base["direction"] == "SELL"
                    and max(row["high"] for row in look) - base["c1_high"] > tolerance):
                reason = f"engulf rejected: c1 is not near a {lookback}-candle swing high"
    confirmation_timeframe = {"30m": "1h", "1h": "4h"}.get(timeframe)
    if reason is None and cfg["use_higher_timeframe_confirmation"] and confirmation_timeframe:
        higher = _records(higher_timeframe_df)
        period = int(cfg["ema_period"])
        trend_ema = _ema([row["close"] for row in higher[:-1]], period) if higher else None
        if trend_ema is None:
            reason = f"{confirmation_timeframe} trend data unavailable"
        elif ((base["direction"] == "BUY" and higher[-2]["close"] <= trend_ema)
              or (base["direction"] == "SELL" and higher[-2]["close"] >= trend_ema)):
            reason = f"{confirmation_timeframe} trend does not confirm engulf direction"
    if reason is None and cfg["use_session_filter"] and not allowed_session:
        reason = "outside allowed trading session for symbol"
    if reason is None and cfg["use_news_filter"] and in_news_blackout:
        reason = "high-impact news blackout"
    if reason is None and cfg["use_spread_filter"]:
        if spread_points is None:
            reason = "spread data unavailable"
        elif spread_points > float(cfg["max_spread_points"]):
            reason = f"spread {spread_points:.1f} points exceeds limit {cfg['max_spread_points']}"
    if reason is None and cfg["use_cooldown"] and cooldown_remaining > 0:
        reason = f"cooldown active for {cooldown_remaining} more candle(s)"
    if reason is None and base["direction"] in open_position_directions:
        reason = f"position already open in {base['direction']} direction"

    sl_distance = abs(base["entry"] - base["sl"])
    if reason is None and sl_distance > float(cfg["max_sl_atr_mult"]) * base["atr"]:
        reason = "stop distance exceeds maximum ATR multiple"

    request: dict[str, Any] = {
        **base,
        "symbol": symbol,
        "timeframe": timeframe,
        "accepted": reason is None,
        "reason": reason or base["reason"],
        "order_type": "market",
        "comment": f"ENGULF_{timeframe}",
        "paper_mode": bool(cfg["paper_mode"]),
        "risk_per_trade_pct": float(cfg["risk_per_trade_pct"]),
        "max_sl_atr_mult": float(cfg["max_sl_atr_mult"]),
    }

    if request["accepted"] and equity is not None and symbol_info is not None:
        request["volume"] = calculate_volume(
            equity, float(request["entry"]), float(request["sl"]), symbol_info,
            float(cfg["risk_per_trade_pct"]))
        if request["volume"] <= 0:
            request["accepted"] = False
            request["reason"] = "cannot size position within broker volume and risk limits"
    return request
