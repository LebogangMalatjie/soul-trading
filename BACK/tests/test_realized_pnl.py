import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import engine


class RealizedPnlTests(unittest.TestCase):
    def test_counts_only_closed_trade_deals(self):
        mt5 = SimpleNamespace(
            DEAL_ENTRY_OUT=1,
            DEAL_ENTRY_OUT_BY=2,
            DEAL_ENTRY_INOUT=3,
            DEAL_TYPE_BUY=0,
            DEAL_TYPE_SELL=1,
            terminal_info=lambda: object(),
            history_deals_get=lambda start, end: [
                SimpleNamespace(entry=0, type=0, profit=0.0, commission=-1.0, swap=0.0, fee=0.0),
                SimpleNamespace(entry=1, type=0, profit=20.0, commission=-1.0, swap=-0.5, fee=-0.1),
                SimpleNamespace(entry=1, type=2, profit=100.0, commission=0.0, swap=0.0, fee=0.0),
                SimpleNamespace(entry=3, type=1, profit=-5.0, commission=-0.5, swap=0.0, fee=0.0),
            ],
        )
        broker = engine.MT5LocalBroker(123, "TestServer")
        broker._ready = True

        with patch.object(engine, "_mt5", return_value=mt5):
            realized = broker._realized_pnl_today()

        self.assertAlmostEqual(realized, 12.9)

    def test_empty_trade_history_reports_zero(self):
        mt5 = SimpleNamespace(
            DEAL_ENTRY_OUT=1,
            DEAL_ENTRY_OUT_BY=2,
            DEAL_ENTRY_INOUT=3,
            DEAL_TYPE_BUY=0,
            DEAL_TYPE_SELL=1,
            terminal_info=lambda: object(),
            history_deals_get=lambda start, end: [],
        )
        broker = engine.MT5LocalBroker(123, "TestServer")
        broker._ready = True

        with patch.object(engine, "_mt5", return_value=mt5):
            realized = broker._realized_pnl_today()

        self.assertEqual(realized, 0.0)


if __name__ == "__main__":
    unittest.main()
