import unittest
from types import SimpleNamespace

import pandas as pd

from strategies.engulfing import build_trade_request, calculate_volume, detect_engulfing


def candles(pattern: str) -> pd.DataFrame:
    rows = [
        {"open": 100.0, "high": 100.2, "low": 99.8, "close": 100.0}
        for _ in range(13)
    ]
    if pattern == "bullish":
        rows.extend([
            {"open": 100.0, "high": 100.1, "low": 98.9, "close": 99.0},
            {"open": 99.0, "high": 100.4, "low": 98.8, "close": 100.2},
        ])
    elif pattern == "bearish":
        rows.extend([
            {"open": 99.0, "high": 100.1, "low": 98.9, "close": 100.0},
            {"open": 100.0, "high": 100.2, "low": 98.6, "close": 98.8},
        ])
    elif pattern == "equal-body":
        rows.extend([
            {"open": 100.0, "high": 100.2, "low": 98.8, "close": 99.0},
            {"open": 99.0, "high": 100.2, "low": 98.8, "close": 100.0},
        ])
    elif pattern == "doji":
        rows.extend([
            {"open": 100.0, "high": 100.1, "low": 98.9, "close": 99.0},
            {"open": 99.0, "high": 100.1, "low": 98.9, "close": 99.0},
        ])
    else:
        rows.extend([
            {"open": 100.0, "high": 100.1, "low": 98.9, "close": 99.0},
            {"open": 99.2, "high": 100.4, "low": 99.1, "close": 100.2},
        ])
    rows.append({"open": 100.2, "high": 100.3, "low": 100.0, "close": 100.1})
    return pd.DataFrame(rows)


def hourly_trend(direction: str, count: int = 60) -> pd.DataFrame:
    start = 80.0 if direction == "up" else 120.0
    step = 0.4 if direction == "up" else -0.4
    rows = []
    for index in range(count):
        close = start + step * index
        rows.append({"open": close, "high": close + 0.2, "low": close - 0.2, "close": close})
    last_close = rows[-1]["close"]
    rows.append({"open": last_close, "high": last_close + 0.1,
                 "low": last_close - 0.1, "close": last_close})
    return pd.DataFrame(rows)


class DetectEngulfingTests(unittest.TestCase):
    def test_valid_bullish_engulfing(self):
        result = detect_engulfing(candles("bullish"))
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "BUY")
        self.assertEqual(set(result), {"direction", "entry", "sl", "tp", "reason"})

    def test_valid_bearish_engulfing(self):
        result = detect_engulfing(candles("bearish"))
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "SELL")

    def test_doji_is_not_an_engulfing(self):
        self.assertIsNone(detect_engulfing(candles("doji")))

    def test_equal_body_boundaries_are_inclusive(self):
        result = detect_engulfing(candles("equal-body"))
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "BUY")

    def test_non_engulfing_pattern_is_rejected(self):
        self.assertIsNone(detect_engulfing(candles("non-engulfing")))

    def test_forming_candle_does_not_define_the_signal(self):
        frame = candles("bullish")
        frame.loc[len(frame) - 2, ["open", "close"]] = [100.0, 99.0]
        self.assertIsNone(detect_engulfing(frame))

    def test_quality_filters_and_trade_request(self):
        toggles_off = {
            "use_min_body_filter": False,
            "use_engulf_strength_filter": False,
            "use_trend_filter": False,
            "use_location_filter": False,
            "use_higher_timeframe_confirmation": False,
            "use_session_filter": False,
            "use_news_filter": False,
            "use_spread_filter": False,
            "use_cooldown": False,
            "max_sl_atr_mult": 10.0,
        }
        request = build_trade_request(candles("bullish"), symbol="XAUUSD", timeframe="1m",
                                      config=toggles_off)
        self.assertIsNotNone(request)
        self.assertTrue(request["accepted"], request["reason"])
        self.assertEqual(request["comment"], "ENGULF_1m")

    def test_swing_filter_accepts_c1_near_recent_extreme(self):
        frame = candles("bullish")
        frame.loc[len(frame) - 4, "low"] = 98.85
        request = build_trade_request(
            frame, symbol="XAUUSD", timeframe="1m",
            config={
                "use_min_body_filter": False,
                "use_engulf_strength_filter": False,
                "use_trend_filter": False,
                "use_higher_timeframe_confirmation": False,
                "use_session_filter": False,
                "use_news_filter": False,
                "use_spread_filter": False,
                "use_cooldown": False,
                "max_sl_atr_mult": 10.0,
            },
        )
        self.assertTrue(request["accepted"], request["reason"])

    def test_swing_filter_still_rejects_c1_far_from_recent_extreme(self):
        frame = candles("bullish")
        frame.loc[len(frame) - 4, "low"] = 98.0
        request = build_trade_request(
            frame, symbol="XAUUSD", timeframe="1m",
            config={
                "use_min_body_filter": False,
                "use_engulf_strength_filter": False,
                "use_trend_filter": False,
                "use_higher_timeframe_confirmation": False,
                "use_session_filter": False,
                "use_news_filter": False,
                "use_spread_filter": False,
                "use_cooldown": False,
                "max_sl_atr_mult": 10.0,
            },
        )
        self.assertFalse(request["accepted"])
        self.assertIn("not near a 10-candle swing low", request["reason"])

    def test_swing_filter_accepts_bearish_c1_near_recent_extreme(self):
        request = build_trade_request(
            candles("bearish"), symbol="XAUUSD", timeframe="1m",
            config={
                "use_min_body_filter": False,
                "use_engulf_strength_filter": False,
                "use_trend_filter": False,
                "use_higher_timeframe_confirmation": False,
                "use_session_filter": False,
                "use_news_filter": False,
                "use_spread_filter": False,
                "use_cooldown": False,
                "max_sl_atr_mult": 10.0,
            },
        )
        self.assertTrue(request["accepted"], request["reason"])

    def test_default_engulfing_signal_timeframes_are_1h_and_30m(self):
        from strategies.engulfing import DEFAULT_CONFIG

        self.assertEqual(DEFAULT_CONFIG["timeframes"], ("1h", "30m"))

    def test_30m_engulf_requires_matching_closed_1h_trend(self):
        toggles_off = {
            "use_min_body_filter": False,
            "use_engulf_strength_filter": False,
            "use_trend_filter": False,
            "use_location_filter": False,
            "use_session_filter": False,
            "use_news_filter": False,
            "use_spread_filter": False,
            "use_cooldown": False,
            "max_sl_atr_mult": 10.0,
        }
        for pattern, aligned_trend, opposing_trend in (
            ("bullish", "up", "down"),
            ("bearish", "down", "up"),
        ):
            with self.subTest(pattern=pattern, trend=aligned_trend):
                accepted = build_trade_request(
                    candles(pattern), symbol="XAUUSD", timeframe="30m",
                    config=toggles_off, higher_timeframe_df=hourly_trend(aligned_trend))
                rejected = build_trade_request(
                    candles(pattern), symbol="XAUUSD", timeframe="30m",
                    config=toggles_off, higher_timeframe_df=hourly_trend(opposing_trend))
                self.assertTrue(accepted["accepted"], accepted["reason"])
                self.assertFalse(rejected["accepted"])
                self.assertIn("1h trend does not confirm", rejected["reason"])

    def test_1h_engulf_requires_matching_closed_4h_trend(self):
        toggles_off = {
            "use_min_body_filter": False,
            "use_engulf_strength_filter": False,
            "use_trend_filter": False,
            "use_location_filter": False,
            "use_session_filter": False,
            "use_news_filter": False,
            "use_spread_filter": False,
            "use_cooldown": False,
            "max_sl_atr_mult": 10.0,
        }
        accepted = build_trade_request(
            candles("bullish"), symbol="XAUUSD", timeframe="1h",
            config=toggles_off, higher_timeframe_df=hourly_trend("up"))
        rejected = build_trade_request(
            candles("bullish"), symbol="XAUUSD", timeframe="1h",
            config=toggles_off, higher_timeframe_df=hourly_trend("down"))
        self.assertTrue(accepted["accepted"], accepted["reason"])
        self.assertFalse(rejected["accepted"])
        self.assertIn("4h trend does not confirm", rejected["reason"])

    def test_30m_engulf_rejects_missing_or_insufficient_1h_history(self):
        toggles_off = {
            "use_min_body_filter": False,
            "use_engulf_strength_filter": False,
            "use_trend_filter": False,
            "use_location_filter": False,
            "use_session_filter": False,
            "use_news_filter": False,
            "use_spread_filter": False,
            "use_cooldown": False,
            "max_sl_atr_mult": 10.0,
        }
        for hourly in (None, hourly_trend("up", count=10)):
            with self.subTest(hourly_history_available=hourly is not None):
                request = build_trade_request(
                    candles("bullish"), symbol="XAUUSD", timeframe="30m",
                    config=toggles_off, higher_timeframe_df=hourly)
                self.assertFalse(request["accepted"])
                self.assertEqual(request["reason"], "1h trend data unavailable")

    def test_volume_uses_tick_value_and_broker_step(self):
        info = SimpleNamespace(trade_tick_size=0.1, trade_tick_value=1.0,
                               volume_step=0.01, volume_min=0.01, volume_max=10.0)
        self.assertEqual(calculate_volume(1000, 100, 99, info, 1.0), 1.0)

    def test_volume_rounds_non_decimal_steps_down(self):
        info = SimpleNamespace(trade_tick_size=1.0, trade_tick_value=1.0,
                               volume_step=0.25, volume_min=0.25, volume_max=10.0)
        self.assertEqual(calculate_volume(99, 100, 99, info, 1.0), 0.75)


if __name__ == "__main__":
    unittest.main()
