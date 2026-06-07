import json
import tempfile
import unittest
from datetime import date

from finance_app.server import AppContext, handle_api_request
from finance_app.storage import CSVStore


class NoopPriceProvider:
    def get_prices(self, symbol, start, end):
        return {}

    def get_fx_rate(self, from_currency, to_currency, as_of):
        return 1.0


class FixedPriceProvider(NoopPriceProvider):
    def __init__(self, prices):
        self.prices = prices

    def get_prices(self, symbol, start, end):
        return {item_date: price for item_date, price in self.prices.get(symbol, {}).items() if start <= item_date <= end}


class ServerAPITests(unittest.TestCase):
    def test_default_dates_use_latest_market_day_and_current_year_start(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = AppContext(
                CSVStore(temp_dir),
                FixedPriceProvider({"^TWII": {date(2026, 6, 5): 100.0}}),
                today=date(2026, 6, 7),
            )

            status, payload = handle_api_request(context, "GET", "/api/defaults", {}, b"")

            self.assertEqual(status, 200)
            self.assertEqual(payload["today"], "2026-06-07")
            self.assertEqual(payload["as_of"], "2026-06-05")
            self.assertEqual(payload["start"], "2026-01-01")
            self.assertEqual(payload["end"], "2026-06-07")

    def test_create_trade_and_get_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = AppContext(CSVStore(temp_dir), NoopPriceProvider())

            status, payload = handle_api_request(
                context,
                "POST",
                "/api/trades",
                {},
                json.dumps(
                    {
                        "date": "2024-01-02",
                        "symbol": "2330.TW",
                        "side": "BUY",
                        "quantity": 10,
                        "price": 500,
                        "fees": 20,
                        "portfolio": "Active",
                        "currency": "TWD",
                    }
                ).encode("utf-8"),
            )

            self.assertEqual(status, 201)
            self.assertEqual(payload["trade"]["symbol"], "2330.TW")
            self.assertEqual(payload["trade"]["portfolio"], "Active")
            self.assertEqual(payload["trade"]["currency"], "TWD")

            status, payload = handle_api_request(
                context,
                "GET",
                "/api/summary",
                {"as_of": ["2024-01-03"], "portfolio": ["Active"], "currency": ["TWD"]},
                b"",
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["as_of"], "2024-01-03")
            self.assertEqual(payload["portfolio"], "Active")
            self.assertEqual(payload["currency"], "TWD")
            self.assertEqual(payload["positions"][0]["symbol"], "2330.TW")
            self.assertTrue(payload["warnings"])

            status, payload = handle_api_request(
                context,
                "GET",
                "/api/period-summary",
                {"start": ["2024-01-01"], "end": ["2024-01-03"], "portfolio": ["Active"], "currency": ["TWD"]},
                b"",
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["start"], "2024-01-01")
            self.assertEqual(payload["end"], "2024-01-03")
            self.assertEqual(payload["portfolio"], "Active")
            self.assertEqual(payload["positions"][0]["symbol"], "2330.TW")

    def test_period_summary_and_allocation_ignore_trades_after_end_date(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = AppContext(CSVStore(temp_dir), NoopPriceProvider())

            for trade in [
                {
                    "date": "2026-01-01",
                    "symbol": "STOCKA",
                    "side": "BUY",
                    "quantity": 1,
                    "price": 230,
                    "currency": "TWD",
                    "portfolio": "Active",
                },
                {
                    "date": "2026-02-01",
                    "symbol": "STOCKB",
                    "side": "BUY",
                    "quantity": 1,
                    "price": 180,
                    "currency": "TWD",
                    "portfolio": "Active",
                },
            ]:
                handle_api_request(
                    context,
                    "POST",
                    "/api/trades",
                    {},
                    json.dumps(trade).encode("utf-8"),
                )

            status, payload = handle_api_request(
                context,
                "GET",
                "/api/period-summary",
                {"start": ["2026-01-01"], "end": ["2026-01-31"], "portfolio": ["Active"], "currency": ["TWD"]},
                b"",
            )

            self.assertEqual(status, 200)
            self.assertEqual([position["symbol"] for position in payload["positions"]], ["STOCKA"])
            self.assertAlmostEqual(payload["market_value"], 230.0, places=2)

            status, payload = handle_api_request(
                context,
                "GET",
                "/api/allocation",
                {"as_of": ["2026-01-31"], "portfolio": ["Active"], "currency": ["TWD"]},
                b"",
            )

            self.assertEqual(status, 200)
            self.assertEqual([position["symbol"] for position in payload["selected"]["positions"]], ["STOCKA"])

    def test_period_summary_ignores_trades_before_start_date(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = AppContext(CSVStore(temp_dir), NoopPriceProvider())

            for trade in [
                {
                    "date": "2025-06-01",
                    "symbol": "OLD",
                    "side": "BUY",
                    "quantity": 1,
                    "price": 999,
                    "currency": "TWD",
                    "portfolio": "Active",
                },
                {
                    "date": "2026-01-10",
                    "symbol": "NEW",
                    "side": "BUY",
                    "quantity": 1,
                    "price": 180,
                    "currency": "TWD",
                    "portfolio": "Active",
                },
            ]:
                handle_api_request(
                    context,
                    "POST",
                    "/api/trades",
                    {},
                    json.dumps(trade).encode("utf-8"),
                )

            status, payload = handle_api_request(
                context,
                "GET",
                "/api/period-summary",
                {"start": ["2026-01-01"], "end": ["2026-01-31"], "portfolio": ["Active"], "currency": ["TWD"]},
                b"",
            )

            self.assertEqual(status, 200)
            self.assertEqual([position["symbol"] for position in payload["positions"]], ["NEW"])
            self.assertAlmostEqual(payload["market_value"], 180.0, places=2)
            self.assertAlmostEqual(payload["buy_cost"], 180.0, places=2)

    def test_allocation_endpoint_returns_overall_and_portfolios(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = AppContext(CSVStore(temp_dir), NoopPriceProvider())

            for portfolio, quantity in [("Active", 10), ("DCA", 5)]:
                handle_api_request(
                    context,
                    "POST",
                    "/api/trades",
                    {},
                    json.dumps(
                        {
                            "date": "2024-01-02",
                            "symbol": "GOOG",
                            "side": "BUY",
                            "quantity": quantity,
                            "price": 100,
                            "fees": 0,
                            "portfolio": portfolio,
                            "currency": "USD",
                        }
                    ).encode("utf-8"),
                )

            status, payload = handle_api_request(
                context,
                "GET",
                "/api/allocation",
                {"as_of": ["2024-01-03"], "currency": ["USD"]},
                b"",
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["currency"], "USD")
            self.assertEqual(payload["overall"]["positions"][0]["symbol"], "GOOG")
            self.assertEqual(payload["portfolio"], "All")
            self.assertEqual(payload["selected"]["market_value"], payload["overall"]["market_value"])
            self.assertEqual([item["portfolio"] for item in payload["portfolios"]], ["Active", "DCA"])

            status, payload = handle_api_request(
                context,
                "GET",
                "/api/allocation",
                {"as_of": ["2024-01-03"], "portfolio": ["Active"], "currency": ["USD"]},
                b"",
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["portfolio"], "Active")
            self.assertEqual(payload["selected"]["positions"][0]["symbol"], "GOOG")
            self.assertAlmostEqual(payload["selected"]["market_value"], 1000.0, places=2)

    def test_trade_import_template_and_batch_import(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = AppContext(CSVStore(temp_dir), NoopPriceProvider())

            status, payload = handle_api_request(
                context,
                "GET",
                "/api/templates/trades",
                {},
                b"",
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["filename"], "trade-import-template.csv")
            self.assertIn("date,symbol,side,quantity,price,fees,currency,portfolio,notes", payload["content"])

            status, payload = handle_api_request(
                context,
                "POST",
                "/api/import/trades",
                {},
                json.dumps(
                    {
                        "records": [
                            {
                                "date": "2024-01-02",
                                "symbol": "GOOG",
                                "side": "BUY",
                                "quantity": "10",
                                "price": "100",
                                "fees": "1",
                                "currency": "USD",
                                "portfolio": "美股",
                                "notes": "batch one",
                            },
                            {
                                "date": "2024-01-03",
                                "symbol": "2330.TW",
                                "side": "BUY",
                                "quantity": "5",
                                "price": "500",
                                "fees": "20",
                                "currency": "TWD",
                                "portfolio": "臺股",
                                "notes": "batch two",
                            },
                        ]
                    }
                ).encode("utf-8"),
            )

            self.assertEqual(status, 201)
            self.assertEqual(payload["imported_count"], 2)
            self.assertEqual([trade["symbol"] for trade in payload["trades"]], ["GOOG", "2330.TW"])
            self.assertEqual(len(context.store.list_trades()), 2)

    def test_dividend_import_template_and_batch_import(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = AppContext(CSVStore(temp_dir), NoopPriceProvider())

            status, payload = handle_api_request(
                context,
                "GET",
                "/api/templates/dividends",
                {},
                b"",
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["filename"], "dividend-import-template.csv")
            self.assertIn("date,symbol,gross_amount,tax,currency,portfolio,notes", payload["content"])

            status, payload = handle_api_request(
                context,
                "POST",
                "/api/import/dividends",
                {},
                json.dumps(
                    {
                        "records": [
                            {
                                "date": "2024-02-01",
                                "symbol": "GOOG",
                                "gross_amount": "10",
                                "tax": "3",
                                "currency": "USD",
                                "portfolio": "Active",
                                "notes": "batch dividend",
                            },
                            {
                                "date": "2024-03-01",
                                "symbol": "2330.TW",
                                "gross_amount": "20",
                                "tax": "0",
                                "currency": "TWD",
                                "portfolio": "DCA",
                                "notes": "",
                            },
                        ]
                    }
                ).encode("utf-8"),
            )

            self.assertEqual(status, 201)
            self.assertEqual(payload["imported_count"], 2)
            self.assertEqual([dividend["symbol"] for dividend in payload["dividends"]], ["GOOG", "2330.TW"])
            self.assertEqual(len(context.store.list_dividends()), 2)

    def test_records_endpoint_filters_and_paginates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = AppContext(CSVStore(temp_dir), NoopPriceProvider())
            for portfolio, symbol in [("Active", "GOOG"), ("DCA", "MSFT")]:
                handle_api_request(
                    context,
                    "POST",
                    "/api/trades",
                    {},
                    json.dumps(
                        {
                            "date": "2024-01-02",
                            "symbol": symbol,
                            "side": "BUY",
                            "quantity": 1,
                            "price": 100,
                            "portfolio": portfolio,
                            "currency": "USD",
                        }
                    ).encode("utf-8"),
                )
            handle_api_request(
                context,
                "POST",
                "/api/dividends",
                {},
                json.dumps(
                    {
                        "date": "2024-02-01",
                        "symbol": "GOOG",
                        "gross_amount": 10,
                        "tax": 0,
                        "portfolio": "Active",
                        "currency": "USD",
                    }
                ).encode("utf-8"),
            )

            status, payload = handle_api_request(
                context,
                "GET",
                "/api/records",
                {"kind": ["trade"], "portfolio": ["Active"], "symbol": ["goo"], "page": ["1"], "page_size": ["1"]},
                b"",
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["page"], 1)
            self.assertEqual(payload["page_size"], 1)
            self.assertEqual(payload["total"], 1)
            self.assertEqual(payload["total_pages"], 1)
            self.assertEqual(payload["records"][0]["kind"], "trade")
            self.assertEqual(payload["records"][0]["symbol"], "GOOG")

    def test_trade_import_rejects_invalid_batch_without_partial_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = AppContext(CSVStore(temp_dir), NoopPriceProvider())

            status, payload = handle_api_request(
                context,
                "POST",
                "/api/import/trades",
                {},
                json.dumps(
                    {
                        "records": [
                            {
                                "date": "2024-01-02",
                                "symbol": "GOOG",
                                "side": "BUY",
                                "quantity": "10",
                                "price": "100",
                            },
                            {
                                "date": "2024-01-03",
                                "symbol": "MSFT",
                                "side": "BUY",
                                "quantity": "0",
                                "price": "100",
                            },
                        ]
                    }
                ).encode("utf-8"),
            )

            self.assertEqual(status, 400)
            self.assertIn("row 2", payload["error"])
            self.assertEqual(context.store.list_trades(), [])


if __name__ == "__main__":
    unittest.main()
