import json
import tempfile
import unittest
from datetime import date

from finance_app.server import AppContext, handle_api_request
from finance_app.storage import CSVStore


class NoopPriceProvider:
    def get_prices(self, symbol, start, end):
        return {}


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
                    }
                ).encode("utf-8"),
            )

            self.assertEqual(status, 201)
            self.assertEqual(payload["trade"]["symbol"], "2330.TW")

            status, payload = handle_api_request(
                context,
                "GET",
                "/api/summary",
                {"as_of": ["2024-01-03"]},
                b"",
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["as_of"], "2024-01-03")
            self.assertEqual(payload["positions"][0]["symbol"], "2330.TW")
            self.assertTrue(payload["warnings"])


if __name__ == "__main__":
    unittest.main()
