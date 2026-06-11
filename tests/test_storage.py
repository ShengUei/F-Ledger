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
                    quantity=10.123456,
                    price=100.123456,
                    fees=1.123456,
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
                    gross_amount=12.123456,
                    tax=2.123456,
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
            self.assertAlmostEqual(reloaded.list_trades()[0].quantity, 10.123456, places=6)
            self.assertAlmostEqual(reloaded.list_trades()[0].price, 100.123456, places=6)
            self.assertAlmostEqual(reloaded.list_trades()[0].fees, 1.123456, places=6)
            self.assertEqual(reloaded.list_trades()[0].portfolio, "Active")
            self.assertEqual(reloaded.list_trades()[0].currency, "USD")
            self.assertEqual(reloaded.list_dividends()[0].id, dividend.id)
            self.assertAlmostEqual(reloaded.list_dividends()[0].gross_amount, 12.123456, places=6)
            self.assertAlmostEqual(reloaded.list_dividends()[0].tax, 2.123456, places=6)
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

    def test_delete_rejects_unknown_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteStore(temp_dir)
            with self.assertRaises(ValueError):
                store._delete_by_id("metadata", "any-id")

    def test_data_version_increments_on_writes_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteStore(temp_dir)
            self.assertEqual(store.data_version(), 0)

            trade = store.add_trade(Trade("", date(2024, 1, 2), "MSFT", "BUY", 2, 200, 0, ""))
            self.assertEqual(store.data_version(), 1)

            store.update_trade(trade.id, Trade("", date(2024, 1, 3), "MSFT", "BUY", 2, 210, 0, ""))
            self.assertEqual(store.data_version(), 2)

            store.update_trade("missing", Trade("", date(2024, 1, 3), "MSFT", "BUY", 2, 210, 0, ""))
            self.assertEqual(store.data_version(), 2)

            store.delete_trade(trade.id)
            self.assertEqual(store.data_version(), 3)

            store.delete_trade(trade.id)
            self.assertEqual(store.data_version(), 3)

    def test_portfolio_names_queries_distinct_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteStore(temp_dir)
            store.add_trade(Trade("", date(2024, 1, 2), "GOOG", "BUY", 1, 100, 0, "", "Active"))
            store.add_trade(Trade("", date(2024, 1, 3), "GOOG", "BUY", 1, 100, 0, "", "Active"))
            store.add_dividend(Dividend("", date(2024, 2, 1), "GOOG", 3, 0, "", "DCA"))

            self.assertEqual(store.portfolio_names(), ["Active", "DCA"])

    def test_query_records_filters_paginates_and_clamps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteStore(temp_dir)
            store.add_trade(Trade("", date(2024, 1, 2), "GOOG", "BUY", 1, 100, 0, "", "Active"))
            store.add_trade(Trade("", date(2024, 2, 2), "MSFT", "BUY", 1, 50, 0, "", "DCA"))
            store.add_dividend(Dividend("", date(2024, 3, 1), "GOOG", 3, 0, "", "Active"))

            rows, total, page = store.query_records()
            self.assertEqual(total, 3)
            self.assertEqual(page, 1)
            self.assertEqual([row["date"] for row in rows], ["2024-03-01", "2024-02-02", "2024-01-02"])

            rows, total, _page = store.query_records(kind="dividend")
            self.assertEqual(total, 1)
            self.assertEqual(rows[0]["kind"], "dividend")

            rows, total, _page = store.query_records(symbol_contains="goo")
            self.assertEqual(total, 2)

            rows, total, _page = store.query_records(portfolio="DCA")
            self.assertEqual(total, 1)
            self.assertEqual(rows[0]["symbol"], "MSFT")

            rows, total, _page = store.query_records(start="2024-02-02", end="2024-03-01")
            self.assertEqual(total, 2)

            rows, _total, page = store.query_records(page=99, page_size=2)
            self.assertEqual(page, 2)
            self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
