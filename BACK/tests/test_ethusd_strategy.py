import unittest
from datetime import datetime, timedelta, timezone

from strategies.eth_usd import ETHUSDStrategy


def bar(at, open_, high, low, close):
    return {"time": at, "open": open_, "high": high, "low": low, "close": close}


class ETHUSDStrategyTests(unittest.TestCase):
    def _breakout_candles(self):
        # 25 prior bars with a contained range so volatility/price stays above the
        # low-volatility threshold (avoids the range-fade branch).
        start = datetime(2026, 10, 17, 6, 0, tzinfo=timezone.utc)  # a Saturday
        candles = [
            bar(start + timedelta(minutes=5 * i), 1000.0, 1002.0, 998.0, 1000.0)
            for i in range(25)
        ]
        # Breakout bar: closes above the prior 20-bar high (~1002).
        candles.append(bar(start + timedelta(minutes=5 * 25),
                           1005.0, 1012.0, 1004.0, 1010.0))
        return candles

    def test_weekend_breakout_fires_without_btc_lead(self):
        # Weekend + no BTC context (lead == 0): the breakout must still fire.
        # The old tautological condition required lead > 0 and never traded here.
        signal = ETHUSDStrategy().should_enter({
            "candles": self._breakout_candles(),
            "now": datetime(2026, 10, 17, 8, 10, tzinfo=timezone.utc),
        })

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "BUY")

    def test_weekday_breakout_still_requires_btc_lead(self):
        # Same setup on a weekday with no BTC lead: entries remain blocked, proving
        # the BTC lead-lag filter is intact outside weekends.
        weekday = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)  # a Monday
        candles = [
            bar(weekday + timedelta(minutes=5 * i), 1000.0, 1002.0, 998.0, 1000.0)
            for i in range(25)
        ]
        candles.append(bar(weekday + timedelta(minutes=5 * 25),
                           1005.0, 1012.0, 1004.0, 1010.0))

        signal = ETHUSDStrategy().should_enter({
            "candles": candles,
            "now": datetime(2026, 10, 12, 8, 10, tzinfo=timezone.utc),
        })

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
