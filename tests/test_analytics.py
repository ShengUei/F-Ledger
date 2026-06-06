import unittest
from datetime import date

from finance_app.analytics import PortfolioAnalytics
from finance_app.models import Dividend, Trade


class FakePriceProvider:
    def __init__(self, prices):
        self.prices = prices

    def get_prices(self, symbol, start, end):
        return self.prices.get(symbol, {})


class PortfolioAnalyticsTests(unittest.TestCase):
    def test_summary_uses_average_cost_realized_gain_and_dividends(self):
        trades = [
            Trade("", date(2024, 1, 2), "AAPL", "BUY", 100, 10, 1, ""),
            Trade("", date(2024, 6, 2), "AAPL", "SELL", 40, 12, 1, ""),
        ]
        dividends = [
            Dividend("", date(2024, 5, 1), "AAPL", 50, 5, ""),
        ]
        prices = {"AAPL": {date(2024, 12, 31): 15}}

        analytics = PortfolioAnalytics(FakePriceProvider(prices))
        summary = analytics.summary(trades, dividends, date(2024, 12, 31))

        self.assertAlmostEqual(summary["market_value"], 900.0, places=2)
        self.assertAlmostEqual(summary["realized_gain"], 78.6, places=2)
        self.assertAlmostEqual(summary["dividends"], 45.0, places=2)
        self.assertAlmostEqual(summary["total_gain"], 423.0, places=2)
        self.assertAlmostEqual(summary["positions"][0]["quantity"], 60.0, places=2)

    def test_performance_series_can_be_grouped_monthly_and_yearly(self):
        trades = [
            Trade("", date(2023, 1, 2), "AAPL", "BUY", 10, 10, 0, ""),
            Trade("", date(2024, 1, 2), "AAPL", "BUY", 10, 20, 0, ""),
        ]
        dividends = [
            Dividend("", date(2024, 6, 1), "AAPL", 10, 0, ""),
        ]
        prices = {
            "AAPL": {
                date(2023, 12, 31): 15,
                date(2024, 1, 31): 21,
                date(2024, 6, 30): 25,
                date(2024, 12, 31): 30,
            }
        }

        analytics = PortfolioAnalytics(FakePriceProvider(prices))
        result = analytics.performance(
            trades,
            dividends,
            start=date(2023, 12, 1),
            end=date(2024, 12, 31),
            interval="yearly",
        )

        self.assertEqual([point["date"] for point in result["points"]], ["2023-12-31", "2024-12-31"])
        self.assertEqual([item["year"] for item in result["annual"]], [2023, 2024])
        self.assertAlmostEqual(result["annual"][0]["ending_market_value"], 150.0, places=2)
        self.assertAlmostEqual(result["annual"][1]["ending_market_value"], 600.0, places=2)


if __name__ == "__main__":
    unittest.main()
