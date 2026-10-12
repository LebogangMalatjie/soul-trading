import unittest
from types import SimpleNamespace

from engine import calc_lot_size
from schemas import SymbolSpec
from strategies.engulfing import calculate_volume


def symbol_spec(min_lot: float = 0.01, lot_step: float = 0.01) -> SymbolSpec:
    return SymbolSpec(
        symbol="XAGUSD",
        contract_size=5000,
        min_lot=min_lot,
        max_lot=100,
        lot_step=lot_step,
        digits=3,
    )


class LotSizingTests(unittest.TestCase):
    def test_uses_point_zero_one_when_minimum_lot_exceeds_risk_tolerance(self):
        lots = calc_lot_size(
            balance=1000,
            risk_pct=0.5,
            entry=30,
            sl=29,
            spec=symbol_spec(),
            min_lot_tolerance=2,
        )

        self.assertEqual(lots, 0.01)

    def test_keeps_broker_minimum_when_within_configured_tolerance(self):
        lots = calc_lot_size(
            balance=1000,
            risk_pct=0.5,
            entry=30,
            sl=29,
            spec=symbol_spec(min_lot=0.1),
            min_lot_tolerance=1000,
        )

        self.assertEqual(lots, 0.1)

    def test_refuses_fallback_when_broker_does_not_allow_point_zero_one(self):
        lots = calc_lot_size(
            balance=1000,
            risk_pct=0.5,
            entry=30,
            sl=29,
            spec=symbol_spec(min_lot=0.1),
            min_lot_tolerance=2,
        )

        self.assertEqual(lots, 0.0)

    def test_engulfing_sizing_uses_point_zero_one_below_broker_minimum(self):
        info = SimpleNamespace(
            trade_tick_size=0.01,
            trade_tick_value=1.0,
            volume_step=0.01,
            volume_min=0.01,
            volume_max=10.0,
        )

        lots = calculate_volume(equity=1000, entry=30, sl=29, symbol_info=info,
                                risk_per_trade_pct=0.01)

        self.assertEqual(lots, 0.01)

    def test_engulfing_sizing_refuses_unsupported_point_zero_one_volume(self):
        info = SimpleNamespace(
            trade_tick_size=0.01,
            trade_tick_value=1.0,
            volume_step=0.01,
            volume_min=0.1,
            volume_max=10.0,
        )

        lots = calculate_volume(equity=1000, entry=30, sl=29, symbol_info=info,
                                risk_per_trade_pct=0.5)

        self.assertEqual(lots, 0.0)


if __name__ == "__main__":
    unittest.main()
