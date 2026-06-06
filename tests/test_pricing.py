import tempfile
import unittest
from datetime import date
from pathlib import Path

from finance_app.pricing import YahooFinanceProvider


class YahooFinanceProviderCacheTests(unittest.TestCase):
    def test_price_cache_is_split_by_symbol_and_year(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = YahooFinanceProvider(temp_dir)
            provider._write_cache(
                "GOOG",
                {
                    date(2023, 12, 29): 100,
                    date(2024, 1, 2): 110,
                },
            )

            self.assertTrue((Path(temp_dir) / "GOOG" / "2023.csv").exists())
            self.assertTrue((Path(temp_dir) / "GOOG" / "2024.csv").exists())
            prices = provider.get_prices("GOOG", date(2023, 12, 29), date(2024, 1, 2))
            self.assertEqual(prices[date(2023, 12, 29)], 100)
            self.assertEqual(prices[date(2024, 1, 2)], 110)

    def test_legacy_flat_price_cache_is_migrated_to_year_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            (cache_dir / "GOOG.csv").write_text(
                "date,close\n2024-01-02,110\n",
                encoding="utf-8",
            )
            provider = YahooFinanceProvider(temp_dir)

            prices = provider.get_prices("GOOG", date(2024, 1, 2), date(2024, 1, 2))

            self.assertEqual(prices[date(2024, 1, 2)], 110)
            self.assertTrue((cache_dir / "GOOG" / "2024.csv").exists())


if __name__ == "__main__":
    unittest.main()
