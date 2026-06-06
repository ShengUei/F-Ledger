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


class ServerAPITests(unittest.TestCase):
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
            self.assertEqual([item["portfolio"] for item in payload["portfolios"]], ["Active", "DCA"])


if __name__ == "__main__":
    unittest.main()
