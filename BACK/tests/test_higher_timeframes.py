import unittest
from datetime import datetime, timedelta, timezone

from engine import Candle, HIGHER_TIMEFRAME_BONUS, higher_timeframe_context
from schemas import Direction, Timeframe


def candles_with_trend(up: bool) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = [100 + index if up else 200 - index for index in range(60)]
    return [
        Candle(start + timedelta(minutes=30 * index), close, close + 1, close - 1, close)
        for index, close in enumerate(closes)
    ]


class HigherTimeframeContextTests(unittest.TestCase):
    def test_aligned_trends_add_optional_score_bonus(self):
        candles = {
            Timeframe.M30: candles_with_trend(True),
            Timeframe.H1: candles_with_trend(True),
            Timeframe.H4: candles_with_trend(True),
        }

        bonus, votes = higher_timeframe_context(candles, Direction.BUY)

        self.assertEqual(bonus, 3 * HIGHER_TIMEFRAME_BONUS)
        self.assertTrue(all(vote["aligned"] for vote in votes))
        self.assertEqual([vote["trend"] for vote in votes], ["BUY", "BUY", "BUY"])

    def test_opposing_or_missing_trends_do_not_block_or_add_bonus(self):
        candles = {
            Timeframe.M30: candles_with_trend(False),
            Timeframe.H1: None,
            Timeframe.H4: candles_with_trend(True),
        }

        bonus, votes = higher_timeframe_context(candles, Direction.BUY)

        self.assertEqual(bonus, HIGHER_TIMEFRAME_BONUS)
        self.assertEqual([vote["trend"] for vote in votes], ["SELL", "UNAVAILABLE", "BUY"])
        self.assertEqual([vote["aligned"] for vote in votes], [False, False, True])

    def test_insufficient_history_is_unavailable_not_misaligned(self):
        short_history = candles_with_trend(True)[:49]

        bonus, votes = higher_timeframe_context({Timeframe.M30: short_history}, Direction.BUY)

        self.assertEqual(bonus, 0)
        self.assertEqual(votes[0]["trend"], "UNAVAILABLE")
        self.assertFalse(votes[0]["aligned"])


if __name__ == "__main__":
    unittest.main()
