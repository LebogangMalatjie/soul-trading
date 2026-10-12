import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from strategies.gbp_usd import GBPUSDStrategy

_LONDON = ZoneInfo("Europe/London")


def bar(at, open_, high, low, close):
    return {"time": at, "open": open_, "high": high, "low": low, "close": close}


class GBPUSDStrategyTests(unittest.TestCase):
    def test_breakout_uses_london_open_hour(self):
        # Build a London 08:00-09:00 opening range, then a breakout bar after 09:00
        # London time. Uses local London wall-clock hours so it is DST-agnostic.
        open_start = datetime(2026, 6, 15, 8, 0, tzinfo=_LONDON)  # a Monday, summer (BST)
        candles = [
            bar(open_start + timedelta(minutes=5 * i), 1.2700, 1.2705, 1.2698, 1.2700)
            for i in range(12)
        ]
        # Padding before the range so len(candles) >= 25.
        padding = [
            bar(open_start - timedelta(minutes=5 * (i + 1)), 1.2690, 1.2695, 1.2688, 1.2690)
            for i in range(15)
        ]
        candles = padding + candles
        # Breakout bar at 09:05 London, closing above the 08:00-hour high.
        breakout_at = datetime(2026, 6, 15, 9, 5, tzinfo=_LONDON)
        candles.append(bar(breakout_at, 1.2700, 1.2720, 1.2699, 1.2715))

        signal = GBPUSDStrategy().should_enter({
            "candles": candles,
            "now": breakout_at + timedelta(minutes=1),
        })

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "BUY")

    def test_no_signal_before_london_open_completes(self):
        # Only 08:00-hour bars exist and it is still 08:xx London -> no entry yet.
        open_start = datetime(2026, 6, 15, 8, 0, tzinfo=_LONDON)
        candles = [
            bar(open_start + timedelta(minutes=5 * i), 1.2700, 1.2705, 1.2698, 1.2700)
            for i in range(6)
        ]
        padding = [
            bar(open_start - timedelta(minutes=5 * (i + 1)), 1.2690, 1.2695, 1.2688, 1.2690)
            for i in range(20)
        ]
        candles = padding + candles

        signal = GBPUSDStrategy().should_enter({
            "candles": candles,
            "now": datetime(2026, 6, 15, 8, 30, tzinfo=_LONDON),
        })

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
