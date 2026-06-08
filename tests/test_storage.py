import tempfile
import unittest
import json
from datetime import date
from pathlib import Path

from finance_app.models import Dividend, Trade
from finance_app.storage import CURRENT_SCHEMA_VERSION, SQLITE_FILE, SQLiteStore, StorageBackend


class SQLiteStoreTests(unittest.TestCase):
    def test_trade_and_dividend_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteStore(temp_dir)

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

            reloaded = SQLiteStore(temp_dir)
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
            store = SQLiteStore(temp_dir)
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

    def test_update_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteStore(temp_dir)
            trade = store.add_trade(
                Trade("", date(2024, 1, 2), "MSFT", "BUY", 2, 200, 0, "", "Active", "USD")
            )
            dividend = store.add_dividend(
                Dividend("", date(2024, 2, 1), "MSFT", 10, 1, "", "Active", "USD")
            )

            updated_trade = store.update_trade(
                trade.id,
                Trade("", date(2024, 1, 3), "AAPL", "SELL", 1, 210, 2, "fixed", "DCA", "USD"),
            )
            updated_dividend = store.update_dividend(
                dividend.id,
                Dividend("", date(2024, 2, 2), "AAPL", 12, 2, "fixed dividend", "DCA", "USD"),
            )

            self.assertIsNotNone(updated_trade)
            self.assertIsNotNone(updated_dividend)
            self.assertEqual(store.list_trades()[0].id, trade.id)
            self.assertEqual(store.list_trades()[0].symbol, "AAPL")
            self.assertEqual(store.list_trades()[0].side, "SELL")
            self.assertEqual(store.list_trades()[0].portfolio, "DCA")
            self.assertEqual(store.list_dividends()[0].id, dividend.id)
            self.assertEqual(store.list_dividends()[0].gross_amount, 12)
            self.assertEqual(store.list_dividends()[0].notes, "fixed dividend")
            self.assertIsNone(store.update_trade("missing", store.list_trades()[0]))
            self.assertIsNone(store.update_dividend("missing", store.list_dividends()[0]))

    def test_existing_csv_without_portfolio_or_currency_is_imported_to_sqlite(self):
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

            store = SQLiteStore(temp_dir)

            self.assertEqual(store.list_trades()[0].portfolio, "General")
            self.assertEqual(store.list_dividends()[0].portfolio, "General")
            self.assertEqual(store.list_trades()[0].currency, "USD")
            self.assertEqual(store.list_dividends()[0].currency, "USD")
            metadata = json.loads((data_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["schema_version"], CURRENT_SCHEMA_VERSION)
            self.assertEqual(metadata["storage_backend"], "sqlite")
            self.assertEqual(metadata["files"]["database"], SQLITE_FILE)
            self.assertTrue((data_dir / SQLITE_FILE).exists())

    def test_sqlite_store_satisfies_storage_backend_protocol(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteStore(temp_dir)

            self.assertIsInstance(store, StorageBackend)
            self.assertTrue(store.price_cache_dir.exists())
            self.assertTrue(store.result_cache_dir.exists())


if __name__ == "__main__":
    unittest.main()
