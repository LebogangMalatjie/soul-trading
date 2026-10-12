"""Soul Trading - technical strategies and FX pair selection.

Each strategy is a pure function of closed candles (oldest -> newest, UTC) and returns a
Signal or None. They fill `diag` (why / partial score) so the dashboard can explain skips,
and use `state` (a per-symbol dict kept by the session) to cap attempts per day.
Signal.stop_distance lets a strategy set a structural stop; Signal.risk_mult scales risk.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Callable, Optional

from engine import Candle, Signal, _diag, analyze, atr, ema, fx_execution_window
from schemas import Direction, Symbol
from strategies.engulfing import DEFAULT_CONFIG as ENGULFING_DEFAULT_CONFIG
from strategies.engulfing import build_trade_request
from strategies.eurusd import STRATEGY as EURUSD_PLUGIN
from strategies.aud_usd import STRATEGY as AUDUSD_PLUGIN
from strategies.eth_usd import STRATEGY as ETHUSD_PLUGIN
from strategies.eur_gbp import STRATEGY as EURGBP_PLUGIN
from strategies.eur_jpy import STRATEGY as EURJPY_PLUGIN
from strategies.gbp_jpy import STRATEGY as GBPJPY_PLUGIN
from strategies.gbp_usd import STRATEGY as GBPUSD_PLUGIN
from strategies.ger40 import STRATEGY as GER40_PLUGIN
from strategies.nzd_usd import STRATEGY as NZDUSD_PLUGIN
from strategies.us100 import STRATEGY as US100_PLUGIN
from strategies.us500 import STRATEGY as US500_PLUGIN
from strategies.usd_chf import STRATEGY as USDCHF_PLUGIN
from strategies.usd_jpy import STRATEGY as USDJPY_PLUGIN
from strategies.usd_cad import STRATEGY as USDCAD_PLUGIN
from strategies.us_oil import STRATEGY as USOIL_PLUGIN


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def bollinger_bandwidth(closes: list[float], period: int = 20, k: float = 2.0) -> list[float]:
    out = []
    for i in range(period - 1, len(closes)):
        w = closes[i - period + 1: i + 1]
        m = sum(w) / period
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / period)
        out.append(0.0 if m == 0 else 2 * k * sd / m)
    return out


def body_ratio(c: Candle) -> float:
    rng = c.high - c.low
    return abs(c.close - c.open) / rng if rng > 0 else 0.0


def attempts_left(state: dict, now: datetime, limit: int) -> bool:
    day = now.strftime("%Y-%m-%d")
    if state.get("day") != day:
        state["day"], state["n"] = day, 0
    return state["n"] < limit


def count_attempt(state: dict, bar: datetime) -> None:
    if state.get("last_counted_bar") != bar:
        state["n"] = state.get("n", 0) + 1
        state["last_counted_bar"] = bar


def _trend15(c15: list[Candle]) -> int:
    cl = [c.close for c in c15]
    e20, e50 = ema(cl, 20)[-1], ema(cl, 50)[-1]
    return 1 if e20 > e50 else -1 if e20 < e50 else 0


def _sma(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    return [sum(values[index - period + 1:index + 1]) / period
            for index in range(period - 1, len(values))]


def fx_anchor_bias(h4: list[Candle]) -> Optional[int]:
    """Return EUR/GBP relative strength only when the H4 SMA stack is unambiguous."""
    closes = [candle.close for candle in h4]
    sma21, sma50 = _sma(closes, 21), _sma(closes, 50)
    if not sma50:
        return None
    fast, slow = sma21[-1], sma50[-1]
    if fast > slow and closes[-1] > fast:
        return 1
    if fast < slow and closes[-1] < fast:
        return -1
    return 0


def _fx_entry_candidate(
    symbol: Symbol, candles: list[Candle], direction: int, timeframe: str,
) -> tuple[Optional[Signal], str]:
    if len(candles) < 55:
        return None, f"not enough {timeframe} history for the 21/50 SMA and structure filters"
    closes = [candle.close for candle in candles]
    sma21, sma50 = _sma(closes, 21), _sma(closes, 50)
    fast_offset = len(candles) - len(sma21)
    slow_offset = len(candles) - len(sma50)
    atr_value = atr(candles)
    if atr_value <= 0:
        return None, f"{timeframe} volatility data unavailable"
    last, previous = candles[-1], candles[-2]
    fast, slow = sma21[-1], sma50[-1]
    stacked = fast > slow and last.close > fast if direction > 0 else fast < slow and last.close < fast
    if not stacked:
        return None, f"{timeframe} price is not aligned with the 21/50 SMA stack"
    if any(candle.volume <= 0 for candle in candles[-25:]):
        return None, f"{timeframe} tick volume unavailable; cannot verify a low-volume pullback"

    body = abs(last.close - last.open)
    candle_range = last.high - last.low
    bullish_confirmation = direction > 0 and last.close > last.open and last.close > previous.close and (
        (last.open <= previous.close and last.close >= previous.open)
        or (last.close - last.low >= 0.68 * candle_range and last.low < min(last.open, last.close) - body)
    )
    bearish_confirmation = direction < 0 and last.close < last.open and last.close < previous.close and (
        (last.open >= previous.close and last.close <= previous.open)
        or (last.high - last.close >= 0.68 * candle_range and last.high > max(last.open, last.close) + body)
    )
    if not (bullish_confirmation or bearish_confirmation):
        return None, f"{timeframe} is waiting for a directional engulfing candle or rejection wick"

    volume_base = sum(candle.volume for candle in candles[-25:-5]) / 20
    first_impulse = max(20, len(candles) - 10)
    for impulse_index in range(len(candles) - 3, first_impulse - 1, -1):
        impulse = candles[impulse_index]
        impulse_body = direction * (impulse.close - impulse.open)
        if impulse_body < 0.8 * atr_value or impulse_body < 0.6 * (impulse.high - impulse.low):
            continue
        structure = candles[impulse_index - 20:impulse_index]
        level = max(candle.high for candle in structure) if direction > 0 else \
            min(candle.low for candle in structure)
        if direction * (impulse.close - level) <= 0:
            continue
        pullbacks = candles[impulse_index + 1:-1]
        if not pullbacks or len(pullbacks) > 4:
            continue
        pullback = pullbacks[-1]
        pullback_index = len(candles) - len(pullbacks) - 1
        fast_index, slow_index = pullback_index - fast_offset, pullback_index - slow_offset
        if not (0 <= fast_index < len(sma21) and 0 <= slow_index < len(sma50)):
            continue
        zone_low, zone_high = sorted((sma21[fast_index], sma50[slow_index]))
        zone_low -= 0.1 * atr_value
        zone_high += 0.1 * atr_value
        ma_retest = pullback.low <= zone_high and pullback.high >= zone_low
        structure_retest = direction * (pullback.low - level) <= 0.15 * atr_value if direction > 0 else \
            direction * (pullback.high - level) <= 0.15 * atr_value
        if not (ma_retest or structure_retest):
            continue
        if pullback.volume >= min(impulse.volume, volume_base) * 0.8:
            continue
        if direction * (pullback.close - impulse.close) >= 0:
            continue

        confirmation = last.close
        pullback_extreme = min(pullback.low, previous.low) if direction > 0 else \
            max(pullback.high, previous.high)
        stop_distance = max(abs(confirmation - pullback_extreme) + 0.15 * atr_value, 0.8 * atr_value)
        strength = min(1.0, impulse_body / (1.5 * atr_value))
        score = 75.0 + 12.0 * strength + (4.0 if ma_retest else 0.0)
        side = Direction.BUY if direction > 0 else Direction.SELL
        reason = (
            f"{timeframe} impulse broke structure, low-volume pullback retested "
            f"{'the SMA zone' if ma_retest else 'structure'}, and confirmation aligned with H4"
        )
        return Signal(symbol, side, round(score, 1), atr_value, reason,
                      stop_distance=stop_distance, strategy=f"FX {timeframe}"), ""
    return None, f"{timeframe} has no confirmed impulse / low-volume pullback structure"


def fx_usd_candidate(
    symbol: Symbol, h4: list[Candle], m15: list[Candle], h1: list[Candle],
    anchor_bias: Optional[int], now: datetime, min_score: float, diag: dict,
) -> Optional[Signal]:
    if symbol not in {Symbol.EURUSD, Symbol.GBPUSD}:
        _diag(diag, "symbol is not an FX/USD execution pair", 0)
        return None
    if not fx_execution_window(now):
        _diag(diag, "FX entries are restricted to 08:00-12:00 New York time", 0)
        return None
    if anchor_bias is None:
        _diag(diag, "EUR/GBP H4 relative-strength anchor is unavailable", 0)
        return None
    if anchor_bias == 0:
        _diag(diag, "EUR/GBP H4 SMA stack is neutral; no USD pair selected", 0)
        return None

    direction = anchor_bias if symbol == Symbol.EURUSD else -anchor_bias
    expected = Direction.BUY if direction > 0 else Direction.SELL
    macro = fx_anchor_bias(h4)
    if macro is None:
        _diag(diag, "not enough H4 history to establish the USD-pair macro trend", 0)
        return None
    if macro != direction:
        _diag(diag, f"H4 macro trend conflicts with the EUR/GBP-filtered {expected.value} bias", 0)
        return None

    candidates: list[Signal] = []
    reasons: list[str] = []
    for timeframe, candles in (("15m", m15), ("1h", h1)):
        signal, reason = _fx_entry_candidate(symbol, candles, direction, timeframe)
        if signal:
            if signal.score >= min_score:
                candidates.append(signal)
            else:
                reasons.append(f"{timeframe} score {signal.score:.0f} is below {min_score:.0f}")
        else:
            reasons.append(reason)
    if candidates:
        chosen = max(candidates, key=lambda signal: signal.score + (4 if "1h" in signal.reason else 0))
        _diag(diag, chosen.reason, chosen.score)
        return chosen
    _diag(diag, "; ".join(reasons), 0)
    return None


# --------------------------------------------------------------------------- #
# BTCUSD - volatility-squeeze breakout (24/7)
# --------------------------------------------------------------------------- #
def btc_squeeze_breakout(symbol, c15, c5, c1, now, scalping, min_score, diag, state) -> Optional[Signal]:
    if len(c15) < 100 or len(c5) < 40 or len(c1) < 5:
        _diag(diag, "not enough candle history yet", 0)
        return None
    if now.weekday() >= 5:
        min_score += 5  # thinner weekend liquidity -> pickier
    if not attempts_left(state, now, 2):
        _diag(diag, "daily attempt limit reached for the BTC breakout", 0)
        return None

    cl15 = [c.close for c in c15]
    bw = bollinger_bandwidth(cl15)
    if len(bw) < 81:
        _diag(diag, "not enough 15m history for a squeeze reading", 0)
        return None
    squeeze, hist = min(bw[-9:-1]), bw[-81:-9]
    pct = sum(1 for v in hist if v <= squeeze) / len(hist)   # low = unusually tight
    tight = max(0.0, 1.0 - pct / 0.25)
    if tight <= 0:
        _diag(diag, "no volatility squeeze on the 15m (bands not unusually tight)", 0)
        return None
    a5 = atr(c5)
    if a5 <= 0:
        _diag(diag, "5m volatility data unavailable", 0)
        return None

    window = c5[-26:-2]                      # ~2h consolidation before the latest two bars
    hi, lo = max(c.high for c in window), min(c.low for c in window)
    buf, last, prev = 0.15 * a5, c5[-1], c5[-2]
    up = last.close > hi + buf and prev.close <= hi
    dn = last.close < lo - buf and prev.close >= lo
    base = 35 * tight
    if not (up or dn):
        _diag(diag, f"squeeze present ({tight * 100:.0f}% tight); waiting for a 5m close beyond the range", base)
        return None
    br = body_ratio(last)
    if br < 0.4:
        _diag(diag, "breakout candle is wick-heavy; not trusting it", base)
        return None
    if (up and c1[-1].close <= hi) or (dn and c1[-1].close >= lo):
        _diag(diag, "1m closed back inside the range (possible fakeout)", base)
        return None

    dist = (last.close - hi) if up else (lo - last.close)
    mom = 0.5 * br + 0.5 * min(1.0, dist / (0.8 * a5))
    trend = _trend15(c15)
    align = 1.0 if trend == (1 if up else -1) else 0.5 if trend == 0 else 0.0
    score = base + 35 * mom + 30 * align
    if score < min_score:
        _diag(diag, f"breakout score {score:.0f} is below the {min_score:.0f} threshold", score)
        return None

    side = Direction.BUY if up else Direction.SELL
    stop = min(max(abs(c1[-1].close - (hi + lo) / 2), 1.2 * a5), 3.0 * a5)   # range midpoint, clamped
    count_attempt(state, c1[-1].time)
    return Signal(symbol, side, round(score, 1), a5,
                  f"BTC squeeze breakout {side.value} ({tight * 100:.0f}% tight, body {br:.2f})",
                  stop_distance=stop)


# --------------------------------------------------------------------------- #
# EURGBP - tradeable via its PLUGIN; also the relative-strength anchor
# --------------------------------------------------------------------------- #
def eurgbp_range_fade(symbol, c15, c5, c1, now, scalping, min_score, diag, state) -> Optional[Signal]:
    _diag(diag, "EUR/GBP is evaluated by its dedicated plug-in; it also guides EUR/USD and GBP/USD", 0)
    return None


# --------------------------------------------------------------------------- #
def trend_pullback(symbol, c15, c5, c1, now, scalping, min_score, diag, state) -> Optional[Signal]:
    return analyze(symbol, c15, c5, c1, scalping, min_score, diag)


def fx_selector_only(symbol, c15, c5, c1, now, scalping, min_score, diag, state) -> Optional[Signal]:
    _diag(diag, "FX/USD pairs must be evaluated through the EUR/GBP-filtered selector", 0)
    return None


STRATEGIES: dict[Symbol, Callable[..., Optional[Signal]]] = {
    Symbol.US30: trend_pullback,
    Symbol.XAUUSD: trend_pullback,
    Symbol.XAGUSD: trend_pullback,
    Symbol.BTCUSD: btc_squeeze_breakout,
    Symbol.EURUSD: fx_selector_only,
    Symbol.GBPUSD: fx_selector_only,
    Symbol.EURGBP: eurgbp_range_fade,
}

PLUGINS = {
    Symbol.EURUSD: EURUSD_PLUGIN,
    Symbol.USDJPY: USDJPY_PLUGIN,
    Symbol.GBPUSD: GBPUSD_PLUGIN,
    Symbol.USDCHF: USDCHF_PLUGIN,
    Symbol.AUDUSD: AUDUSD_PLUGIN,
    Symbol.USDCAD: USDCAD_PLUGIN,
    Symbol.NZDUSD: NZDUSD_PLUGIN,
    Symbol.EURGBP: EURGBP_PLUGIN,
    Symbol.EURJPY: EURJPY_PLUGIN,
    Symbol.GBPJPY: GBPJPY_PLUGIN,
    Symbol.US100: US100_PLUGIN,
    Symbol.US500: US500_PLUGIN,
    Symbol.GER40: GER40_PLUGIN,
    Symbol.USOIL: USOIL_PLUGIN,
    Symbol.ETHUSD: ETHUSD_PLUGIN,
}


def run(symbol, c15, c5, c1, now, scalping, min_score, diag, state) -> Optional[Signal]:
    strategy = STRATEGIES[symbol]
    signal = strategy(symbol, c15, c5, c1, now, scalping, min_score, diag, state)
    if symbol != Symbol.BTCUSD:
        return signal

    pullback_diag: dict = {}
    pullback = analyze(symbol, c15, c5, c1, scalping, min_score, pullback_diag)
    candidates = [candidate for candidate in (signal, pullback) if candidate is not None]
    if candidates:
        chosen = max(candidates, key=lambda item: item.score)
        _diag(diag, chosen.reason, chosen.score)
        return chosen
    if float(pullback_diag.get("score", 0)) > float(diag.get("score", 0)):
        diag.update(pullback_diag)
    return None
