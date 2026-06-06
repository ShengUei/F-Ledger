import tempfile
import unittest
from datetime import date

from finance_app.models import Dividend, Trade
from finance_app.storage import CSVStore


class CSVStoreTests(unittest.TestCase):
    def test_trade_and_dividend_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CSVStore(temp_dir)

            trade = store.add_trade(
                Trade(
                    id="",
                    date=date(2024, 1, 2),
                    symbol="aapl",
                    side="buy",
                    quantity=10,
                    price=100,
                    fees=1.5,
                    notes="first lot",
                )
            )
            dividend = store.add_dividend(
                Dividend(
                    id="",
                    date=date(2024, 3, 1),
                    symbol="aapl",
                    gross_amount=12,
                    tax=2,
                    notes="cash dividend",
                )
            )

            reloaded = CSVStore(temp_dir)
            self.assertEqual(len(reloaded.list_trades()), 1)
            self.assertEqual(len(reloaded.list_dividends()), 1)
            self.assertEqual(reloaded.list_trades()[0].id, trade.id)
            self.assertEqual(reloaded.list_trades()[0].symbol, "AAPL")
            self.assertEqual(reloaded.list_dividends()[0].id, dividend.id)
            self.assertEqual(reloaded.list_dividends()[0].gross_amount, 12)

    def test_delete_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CSVStore(temp_dir)
            trade = store.add_trade(
                Trade(
                    id="",
                    date=date(2024, 1, 2),
                    symbol="MSFT",
                    side="BUY",
                    quantity=2,
                    price=200,
                    fees=0,
                    notes="",
                )
            )

            self.assertTrue(store.delete_trade(trade.id))
            self.assertFalse(store.delete_trade(trade.id))
            self.assertEqual(store.list_trades(), [])


if __name__ == "__main__":
    unittest.main()
