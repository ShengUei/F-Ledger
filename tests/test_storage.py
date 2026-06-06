import tempfile
import unittest
from datetime import date
from pathlib import Path

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
                    portfolio="Active",
                    currency="USD",
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
                    portfolio="Active",
                    currency="USD",
                )
            )

            reloaded = CSVStore(temp_dir)
            self.assertEqual(len(reloaded.list_trades()), 1)
            self.assertEqual(len(reloaded.list_dividends()), 1)
            self.assertEqual(reloaded.list_trades()[0].id, trade.id)
            self.assertEqual(reloaded.list_trades()[0].symbol, "AAPL")
            self.assertEqual(reloaded.list_trades()[0].portfolio, "Active")
            self.assertEqual(reloaded.list_trades()[0].currency, "USD")
            self.assertEqual(reloaded.list_dividends()[0].id, dividend.id)
            self.assertEqual(reloaded.list_dividends()[0].gross_amount, 12)
            self.assertEqual(reloaded.list_dividends()[0].portfolio, "Active")
            self.assertEqual(reloaded.list_dividends()[0].currency, "USD")

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

    def test_existing_csv_without_portfolio_or_currency_is_migrated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            data_dir.mkdir(exist_ok=True)
            (data_dir / "trades.csv").write_text(
                "id,date,symbol,side,quantity,price,fees,notes\n"
                "t1,2024-01-02,GOOG,BUY,1,100,0,old row\n",
                encoding="utf-8",
            )
            (data_dir / "dividends.csv").write_text(
                "id,date,symbol,gross_amount,tax,notes\n"
                "d1,2024-02-01,GOOG,3,0,old dividend\n",
                encoding="utf-8",
            )

            store = CSVStore(temp_dir)

            self.assertEqual(store.list_trades()[0].portfolio, "General")
            self.assertEqual(store.list_dividends()[0].portfolio, "General")
            self.assertEqual(store.list_trades()[0].currency, "USD")
            self.assertEqual(store.list_dividends()[0].currency, "USD")
            trades_header = (data_dir / "trades.csv").read_text(encoding="utf-8").splitlines()[0]
            dividends_header = (data_dir / "dividends.csv").read_text(encoding="utf-8").splitlines()[0]
            self.assertIn("portfolio", trades_header)
            self.assertIn("currency", trades_header)
            self.assertIn("portfolio", dividends_header)
            self.assertIn("currency", dividends_header)


if __name__ == "__main__":
    unittest.main()
