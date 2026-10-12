import unittest
from types import SimpleNamespace
from unittest.mock import patch

from engine import Direction, TradingEngine
from schemas import Symbol, SymbolControlMode


class SymbolControlTests(unittest.TestCase):
    def make_engine(self, enabled=True, mode="active", available=True):
        engine = TradingEngine.__new__(TradingEngine)
        engine._symbol_controls_available = available
        engine._symbol_controls = {
            Symbol.EURUSD.value: {"enabled": enabled, "mode": mode},
        }
        return engine

    def test_active_toggle_allows_new_entry(self):
        engine = self.make_engine()

        self.assertTrue(engine.can_enter_symbol(Symbol.EURUSD))

    def test_manage_only_and_off_block_new_entries(self):
        for mode, enabled in (("manage_only", True), ("off", False)):
            with self.subTest(mode=mode):
                engine = self.make_engine(enabled=enabled, mode=mode)
                self.assertFalse(engine.can_enter_symbol(Symbol.EURUSD))

    def test_kill_switch_overrides_active_symbol_toggle(self):
        engine = self.make_engine()

        with patch("engine.is_auto_trading_enabled", return_value=False):
            self.assertFalse(engine.can_enter_symbol(Symbol.EURUSD))

    def test_database_down_fails_closed(self):
        engine = self.make_engine(available=False)

        self.assertFalse(engine.can_enter_symbol(Symbol.EURUSD))
        self.assertEqual(engine.symbol_control(Symbol.EURUSD)[1], SymbolControlMode.MANAGE_ONLY)

    def test_legacy_symbols_keep_default_enabled_state_when_database_is_available(self):
        engine = self.make_engine()
        engine._symbol_controls = {}

        self.assertTrue(engine.can_enter_symbol(Symbol.XAUUSD))
        self.assertFalse(engine.can_enter_symbol(Symbol.US100))

    def test_us100_cannot_add_same_direction_us30_exposure(self):
        session = SimpleNamespace(
            config=SimpleNamespace(broker_symbol=lambda symbol: symbol.value),
            live_positions=[{"symbol": "US30m", "side": "BUY"}],
        )

        self.assertTrue(TradingEngine._has_correlated_position(session, Symbol.US100, Direction.BUY))
        self.assertFalse(TradingEngine._has_correlated_position(session, Symbol.US100, Direction.SELL))
        self.assertFalse(TradingEngine._has_correlated_position(session, Symbol.US500, Direction.BUY))


if __name__ == "__main__":
    unittest.main()
