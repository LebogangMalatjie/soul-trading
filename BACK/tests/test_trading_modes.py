import unittest

from schemas import StrategyConfig, StrategyConfigUpdate


class TradingModeConfigTests(unittest.TestCase):
    def test_legacy_default_remains_scalping_only(self):
        config = StrategyConfig()

        self.assertTrue(config.scalping)
        self.assertFalse(config.day_trading_enabled)
        self.assertEqual(config.trading_mode, "scalping")

    def test_scalping_and_day_trading_can_both_be_enabled(self):
        config = StrategyConfig(scalping=True, day_trading_enabled=True)

        self.assertTrue(config.scalping)
        self.assertTrue(config.day_trading_enabled)
        self.assertEqual(config.trading_mode, "scalping + day trading")

    def test_modes_can_be_configured_independently(self):
        config = StrategyConfig(scalping=False, day_trading_enabled=True)
        update = StrategyConfigUpdate(day_trading_enabled=False)

        self.assertEqual(config.trading_mode, "day trading")
        self.assertEqual(update.model_dump(exclude_none=True), {"day_trading_enabled": False})


if __name__ == "__main__":
    unittest.main()
