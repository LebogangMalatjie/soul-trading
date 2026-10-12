import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from engine import TradingEngine
from schemas import AccountInfo, Direction, Symbol, SymbolSpec, TradeSource


class SymbolTradingTests(unittest.TestCase):
    def test_open_position_for_another_symbol_does_not_block_this_symbol(self):
        session = SimpleNamespace(
            open_trades={"btc-position": SimpleNamespace(symbol=Symbol.BTCUSD)},
            live_positions=[{"symbol": "BTCUSDm"}],
            config=SimpleNamespace(broker_symbol=lambda symbol: symbol.value),
        )

        self.assertFalse(TradingEngine._has_open_position(session, Symbol.XAUUSD))

    def test_open_position_for_same_symbol_is_detected(self):
        session = SimpleNamespace(
            open_trades={},
            live_positions=[{"symbol": "XAUUSDm"}],
            config=SimpleNamespace(broker_symbol=lambda symbol: symbol.value),
        )

        self.assertTrue(TradingEngine._has_open_position(session, Symbol.XAUUSD))

    def test_xag_order_path_submits_silver_order(self):
        broker = SimpleNamespace(
            price=AsyncMock(return_value=SimpleNamespace(ask=30.1, bid=30.0)),
            account_info=AsyncMock(return_value=AccountInfo(
                login=1, balance=10_000, equity=10_000, free_margin=50_000, leverage=100,
            )),
            market_order=AsyncMock(return_value="silver-position"),
        )
        spec = SymbolSpec(
            symbol="XAGUSD", contract_size=5000, min_lot=0.01, max_lot=100,
            lot_step=0.01, digits=2,
        )
        config = SimpleNamespace(
            scalping=True,
            risk_percent=0.5,
            min_lot_risk_tolerance=2.0,
            params=SimpleNamespace(sl_atr_mult=1.5, tp_rr=1.5),
            broker_symbol=lambda symbol: symbol.value,
        )
        session = SimpleNamespace(
            user_id="test-user",
            config=config,
            broker=broker,
            spec=AsyncMock(return_value=spec),
            quote_to_account=AsyncMock(return_value=1.0),
            order_lock=asyncio.Lock(),
            open_trades={},
            note=unittest.mock.Mock(),
        )
        engine = TradingEngine.__new__(TradingEngine)
        engine.ai_meta = None
        engine.db = SimpleNamespace(insert_trade=AsyncMock(return_value=1))

        with patch("engine.is_auto_trading_enabled", return_value=True):
            asyncio.run(engine._open_trade(
                session, Symbol.XAGUSD, Direction.BUY, 2.0, TradeSource.TECHNICAL, 80.0,
                stop_loss=29.0, take_profit=32.0, entry_price=30.0,
            ))

        broker.market_order.assert_awaited_once()
        self.assertEqual(broker.market_order.await_args.args[0], "XAGUSD")
        self.assertEqual(session.open_trades["silver-position"].symbol, Symbol.XAGUSD)


if __name__ == "__main__":
    unittest.main()
