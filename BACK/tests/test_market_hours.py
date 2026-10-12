import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from engine import TradingEngine, market_open
from schemas import Symbol


class MarketHoursTests(unittest.TestCase):
    def test_btcusd_remains_open_during_weekend_and_rollover(self):
        saturday_rollover = datetime(2026, 10, 3, 21, 30, tzinfo=timezone.utc)

        self.assertTrue(market_open(Symbol.BTCUSD, saturday_rollover))
        self.assertTrue(market_open("BTCUSD", saturday_rollover))
        self.assertTrue(market_open("BTCUSDm", saturday_rollover))

    def test_weekend_closes_non_crypto_cfds(self):
        saturday = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)

        self.assertFalse(market_open(Symbol.US30, saturday))
        self.assertFalse(market_open("XAUUSD", saturday))

    def test_gbp_usd_observes_forex_hours_including_broker_suffixes(self):
        friday_close = datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)
        normal_hours = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)

        self.assertFalse(market_open(Symbol.GBPUSD, friday_close))
        self.assertTrue(market_open("GBPUSDm", normal_hours))

    def test_market_hours_require_timezone_aware_time(self):
        with self.assertRaises(ValueError):
            market_open(Symbol.BTCUSD, datetime(2026, 10, 3, 12, 0))

    def test_stale_btc_quote_is_not_classified_as_market_closed(self):
        session = SimpleNamespace(
            setup_hysteresis={},
            setups={},
            open_trades={},
            live_positions=[],
            config=SimpleNamespace(
                broker_symbol=lambda symbol: symbol.value,
                pinned_symbols=[],
            ),
            note=lambda *args, **kwargs: None,
        )
        engine = TradingEngine.__new__(TradingEngine)
        now = datetime(2026, 10, 3, 21, 30, tzinfo=timezone.utc)

        engine._store_setup(
            session, Symbol.BTCUSD, "BTC strategy", 0, 65, None,
            "stale market data", True, "No fresh broker tick.", now,
        )

        self.assertFalse(session.setups["BTCUSD"]["market_closed"])
        self.assertEqual(session.setups["BTCUSD"]["state"], "watching")

    def test_actual_scheduled_closure_is_marked_explicitly(self):
        session = SimpleNamespace(
            setup_hysteresis={},
            setups={},
            open_trades={},
            live_positions=[],
            config=SimpleNamespace(
                broker_symbol=lambda symbol: symbol.value,
                pinned_symbols=[],
            ),
            note=lambda *args, **kwargs: None,
        )
        engine = TradingEngine.__new__(TradingEngine)
        now = datetime(2026, 10, 3, 21, 30, tzinfo=timezone.utc)

        engine._store_setup(
            session, Symbol.US30, "Index strategy", 0, 65, None,
            "market closed", False, "Market is closed.", now,
        )

        self.assertTrue(session.setups["US30"]["market_closed"])
        self.assertEqual(session.setups["US30"]["state"], "closed")


if __name__ == "__main__":
    unittest.main()
