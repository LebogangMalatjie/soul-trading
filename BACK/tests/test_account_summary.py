import unittest

from engine import account_summary
from schemas import AccountInfo


class AccountSummaryTests(unittest.TestCase):
    def test_balance_and_floating_profit_loss_are_aggregated(self):
        account = AccountInfo(login=123, currency="USD", balance=1000, equity=1008,
                              free_margin=900, leverage=100)
        positions = [
            {"floating_profit": 12.345},
            {"floating_profit": -4.125},
            {"floating_profit": 0.0},
        ]

        summary = account_summary(account, positions, realized_today=21.75)

        self.assertEqual(summary.balance, 1000)
        self.assertEqual(summary.equity, 1008)
        self.assertEqual(summary.floating_profit, 12.35)
        self.assertEqual(summary.floating_loss, -4.12)
        self.assertEqual(summary.net_floating_pnl, 8.22)
        self.assertEqual(summary.realized_today, 21.75)
        self.assertEqual(summary.open_positions, 3)

    def test_account_with_no_positions_has_zero_open_pnl(self):
        account = AccountInfo(login=123, balance=500, equity=500, free_margin=500)

        summary = account_summary(account, [])

        self.assertEqual(summary.floating_profit, 0)
        self.assertEqual(summary.floating_loss, 0)
        self.assertEqual(summary.net_floating_pnl, 0)
        self.assertEqual(summary.realized_today, 0)
        self.assertEqual(summary.open_positions, 0)


if __name__ == "__main__":
    unittest.main()
