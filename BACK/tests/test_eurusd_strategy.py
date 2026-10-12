import unittest
from datetime import datetime, timedelta, timezone

from strategies.eurusd import EURUSDStrategy


def bar(at, open_, high, low, close):
    return {"time": at, "open": open_, "high": high, "low": low, "close": close}


class EURUSDStrategyTests(unittest.TestCase):
    def test_fades_asian_range_upper_edge(self):
        start = datetime(2026, 10, 12, 4, 0, tzinfo=timezone.utc)
        candles = [
            bar(start + timedelta(minutes=5 * index), 1.1005, 1.1010, 1.1000, 1.1005)
            for index in range(24)
        ]
        candles.append(bar(datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc),
                           1.1005, 1.1010, 1.1004, 1.1009))

        signal = EURUSDStrategy().should_enter({
            "candles": candles, "now": datetime(2026, 10, 12, 6, 5, tzinfo=timezone.utc),
        })

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "SELL")
        self.assertGreater(signal.stop_distance, 0)

    def test_breaks_range_during_london_new_york_overlap(self):
        start = datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc)
        candles = [
            bar(start + timedelta(minutes=5 * index), 1.1002, 1.1005, 1.1000, 1.1002)
            for index in range(30)
        ]
        candles.append(bar(start + timedelta(minutes=150), 1.1004, 1.1020, 1.1003, 1.1019))

        signal = EURUSDStrategy().should_enter({
            "candles": candles, "now": start + timedelta(minutes=155),
        })

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "BUY")

    def test_reverses_after_liquidity_sweep(self):
        start = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
        candles = [
            bar(start + timedelta(minutes=5 * index), 1.1002, 1.1005, 1.1000, 1.1002)
            for index in range(22)
        ]
        candles.append(bar(start + timedelta(minutes=110), 1.1002, 1.1012, 1.1001, 1.1003))

        signal = EURUSDStrategy().should_enter({
            "candles": candles, "now": start + timedelta(minutes=115),
        })

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "SELL")


if __name__ == "__main__":
    unittest.main()
