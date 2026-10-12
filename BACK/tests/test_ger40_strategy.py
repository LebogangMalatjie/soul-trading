import unittest
from datetime import datetime, timedelta, timezone

from strategies.ger40 import GER40Strategy


def bar(at, open_, high, low, close):
    return {"time": at, "open": open_, "high": high, "low": low, "close": close}


class GER40StrategyTests(unittest.TestCase):
    def test_gap_fill_uses_prior_session_close_not_fixed_offset(self):
        # Monday session (prior day) closes at 19000.
        monday = [
            bar(datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i),
                19000.0, 19005.0, 18995.0, 19000.0)
            for i in range(16)
        ]
        # Tuesday opens with a gap up (open well above prior close) then fades back
        # down below the prior close -> bearish gap-fill SELL.
        tuesday_open = [
            bar(datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i),
                19060.0, 19065.0, 19055.0, 19060.0)
            for i in range(3)
        ]
        # A filler gap between the two sessions so a fixed -25 offset would land in
        # the wrong place; the strategy must still resolve the prior day's close.
        filler = [
            bar(datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i),
                19000.0, 19001.0, 18999.0, 19000.0)
            for i in range(6)
        ]
        candles = monday + filler + tuesday_open
        # Final bar gaps up then sells off back below the prior close (19000).
        candles.append(bar(datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc),
                           19040.0, 19045.0, 18980.0, 18990.0))

        signal = GER40Strategy().should_enter({
            "candles": candles,
            "now": datetime(2026, 10, 13, 8, 5, tzinfo=timezone.utc),
        })

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "SELL")
        self.assertIn("gap-fill", signal.reason)

    def test_no_gap_fill_without_prior_session(self):
        # Only today's bars exist -> no prior session close, so no gap-fill signal.
        today = [
            bar(datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i),
                19000.0, 19005.0, 18995.0, 19000.0)
            for i in range(4)
        ]
        today.append(bar(datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc),
                         19000.0, 19001.0, 18999.0, 19000.0))

        signal = GER40Strategy().should_enter({
            "candles": today,
            "now": datetime(2026, 10, 13, 8, 5, tzinfo=timezone.utc),
        })

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
