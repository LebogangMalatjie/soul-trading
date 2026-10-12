import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from engine import Candle, Signal, TradingEngine, fx_execution_window
from schemas import Direction, Symbol
from strategies import fx_anchor_bias, fx_usd_candidate, run


def trend_candles(up: bool, count: int = 70, minutes: int = 15) -> list[Candle]:
    start = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)
    candles = []
    for index in range(count):
        close = 100.0 + (0.1 * index if up else -0.1 * index)
        candles.append(Candle(
            start + timedelta(minutes=minutes * index),
            close - 0.02 if up else close + 0.02,
            close + 0.08,
            close - 0.08,
            close,
            100.0,
        ))
    return candles


def entry_candles(up: bool) -> list[Candle]:
    candles = trend_candles(True, minutes=15)
    if not up:
        candles = [
            Candle(c.time, 200 - (c.open - 100), 200 - (c.low - 100),
                   200 - (c.high - 100), 200 - (c.close - 100), c.volume)
            for c in candles
        ]
    last_index = len(candles) - 1
    impulse_index = last_index - 3
    impulse_base = candles[impulse_index].close
    breakout = 0.25 if up else -0.25
    candles[impulse_index] = Candle(
        candles[impulse_index].time,
        impulse_base,
        impulse_base + (0.28 if up else 0.04),
        impulse_base - (0.04 if up else 0.28),
        impulse_base + breakout,
        300.0,
    )
    pullback_close = impulse_base + (0.04 if up else -0.04)
    candles[last_index - 2] = Candle(
        candles[last_index - 2].time,
        impulse_base + breakout,
        impulse_base + (0.27 if up else 0.03),
        impulse_base - (0.02 if up else 0.27),
        pullback_close,
        10.0,
    )
    candles[last_index - 1] = Candle(
        candles[last_index - 1].time,
        pullback_close,
        pullback_close + (0.08 if up else 0.27),
        pullback_close - (0.08 if up else 0.03),
        pullback_close - (0.01 if up else -0.01),
        15.0,
    )
    confirm_open = candles[last_index - 1].close
    candles[last_index] = Candle(
        candles[last_index].time,
        confirm_open,
        confirm_open + (0.25 if up else 0.03),
        confirm_open - (0.03 if up else 0.25),
        confirm_open + (0.22 if up else -0.22),
        120.0,
    )
    return candles


class FxPairSelectionTests(unittest.TestCase):
    def test_new_york_execution_window_tracks_daylight_saving_time(self):
        self.assertTrue(fx_execution_window(datetime(2026, 10, 9, 12, 30, tzinfo=timezone.utc)))
        self.assertTrue(fx_execution_window(datetime(2026, 1, 15, 13, 30, tzinfo=timezone.utc)))
        self.assertFalse(fx_execution_window(datetime(2026, 10, 9, 11, 59, tzinfo=timezone.utc)))
        self.assertFalse(fx_execution_window(datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)))

    def test_standalone_fx_strategy_cannot_trade_without_anchor_selection(self):
        diag: dict = {}
        signal = run(
            Symbol.EURUSD, entry_candles(True), entry_candles(True), entry_candles(True),
            datetime(2026, 10, 9, 12, 30, tzinfo=timezone.utc), True, 65, diag, {},
        )

        self.assertIsNone(signal)
        self.assertIn("EUR/GBP-filtered selector", diag["why"])

    def test_eurgbp_bias_controls_allowed_usd_pair_directions(self):
        anchor = trend_candles(True, minutes=240)
        h4_up = trend_candles(True, minutes=240)
        h4_down = trend_candles(False, minutes=240)
        now = datetime(2026, 10, 9, 12, 30, tzinfo=timezone.utc)

        self.assertEqual(fx_anchor_bias(anchor), 1)

        eur_diag: dict = {}
        eur_signal = fx_usd_candidate(
            Symbol.EURUSD, h4_up, entry_candles(True), entry_candles(True),
            fx_anchor_bias(anchor), now, 65, eur_diag,
        )
        gbp_diag: dict = {}
        gbp_signal = fx_usd_candidate(
            Symbol.GBPUSD, h4_down, entry_candles(False), entry_candles(False),
            fx_anchor_bias(anchor), now, 65, gbp_diag,
        )

        self.assertIsNotNone(eur_signal, eur_diag)
        self.assertEqual(eur_signal.direction, Direction.BUY)
        self.assertIsNotNone(gbp_signal, gbp_diag)
        self.assertEqual(gbp_signal.direction, Direction.SELL)

    def test_bearish_eurgbp_bias_reverses_allowed_usd_pair_directions(self):
        anchor = trend_candles(False, minutes=240)
        now = datetime(2026, 10, 9, 12, 30, tzinfo=timezone.utc)
        eur_diag: dict = {}
        eur_signal = fx_usd_candidate(
            Symbol.EURUSD, trend_candles(False, minutes=240),
            entry_candles(False), entry_candles(False),
            fx_anchor_bias(anchor), now, 65, eur_diag,
        )
        gbp_diag: dict = {}
        gbp_signal = fx_usd_candidate(
            Symbol.GBPUSD, trend_candles(True, minutes=240),
            entry_candles(True), entry_candles(True),
            fx_anchor_bias(anchor), now, 65, gbp_diag,
        )

        self.assertEqual(fx_anchor_bias(anchor), -1)
        self.assertIsNotNone(eur_signal, eur_diag)
        self.assertEqual(eur_signal.direction, Direction.SELL)
        self.assertIsNotNone(gbp_signal, gbp_diag)
        self.assertEqual(gbp_signal.direction, Direction.BUY)

    def test_h4_pair_trend_conflicting_with_anchor_is_rejected(self):
        diag: dict = {}
        signal = fx_usd_candidate(
            Symbol.EURUSD,
            trend_candles(False, minutes=240),
            entry_candles(True),
            entry_candles(True),
            1,
            datetime(2026, 10, 9, 12, 30, tzinfo=timezone.utc),
            65,
            diag,
        )

        self.assertIsNone(signal)
        self.assertIn("conflicts", diag["why"])

    def test_low_volume_filter_fails_closed_when_volume_is_missing(self):
        no_volume = [
            Candle(c.time, c.open, c.high, c.low, c.close, 0.0)
            for c in entry_candles(True)
        ]
        diag: dict = {}
        signal = fx_usd_candidate(
            Symbol.EURUSD,
            trend_candles(True, minutes=240),
            no_volume,
            no_volume,
            1,
            datetime(2026, 10, 9, 12, 30, tzinfo=timezone.utc),
            65,
            diag,
        )

        self.assertIsNone(signal)
        self.assertIn("tick volume unavailable", diag["why"])


class FxPairOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_highest_scoring_pair_is_selected(self):
        now = datetime(2026, 10, 9, 12, 30, tzinfo=timezone.utc)
        history = [
            Candle(now - timedelta(hours=240 - 4 * index), 1.0, 1.1, 0.9, 1.0, 100.0)
            for index in range(70)
        ]

        async def candles(_symbol: Symbol, _timeframe):
            return history

        session = SimpleNamespace(
            config=SimpleNamespace(
                symbols=[Symbol.EURUSD, Symbol.GBPUSD],
                broker_symbol=lambda symbol: symbol.value,
            ),
            broker=SimpleNamespace(is_live=AsyncMock(return_value=True)),
            candles=candles,
            open_trades={},
            live_positions=[],
            strategy_states={},
        )
        engine = TradingEngine.__new__(TradingEngine)

        def candidate(symbol, _h4, _m15, _h1, _bias, _now, _threshold, diag):
            score = 80.0 if symbol == Symbol.EURUSD else 90.0
            diag.update(score=score, why="qualifying test setup")
            direction = Direction.BUY if symbol == Symbol.EURUSD else Direction.SELL
            return Signal(symbol, direction, score, 0.01, "test setup", strategy="FX 15m")

        with patch("strategies.fx_anchor_bias", return_value=1), \
                patch("strategies.fx_usd_candidate", side_effect=candidate):
            selected, signals, diagnostics = await engine._select_fx_pair(session, now, 65.0)
            repeated_selection, repeated_signals, _ = await engine._select_fx_pair(session, now, 65.0)

        self.assertEqual(selected, Symbol.GBPUSD)
        self.assertEqual(signals[Symbol.EURUSD].score, 80.0)
        self.assertEqual(signals[Symbol.GBPUSD].score, 90.0)
        self.assertIn("cleaner setup selected", diagnostics[Symbol.EURUSD]["why"])
        self.assertIsNone(repeated_selection)
        self.assertFalse(repeated_signals[Symbol.GBPUSD].new_closed_candle)


if __name__ == "__main__":
    unittest.main()
