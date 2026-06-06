import unittest
import tempfile
from datetime import date

from finance_app.analytics import PortfolioAnalytics
from finance_app.cache import JSONResultCache
from finance_app.models import Dividend, Trade


class FakePriceProvider:
    def __init__(self, prices, fx_rates=None):
        self.prices = prices
        self.fx_rates = fx_rates or {}

    def get_prices(self, symbol, start, end):
        return self.prices.get(symbol, {})

    def get_fx_rate(self, from_currency, to_currency, as_of):
        if from_currency == to_currency:
            return 1.0
        return self.fx_rates.get((from_currency, to_currency, as_of), 1.0)


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

    def test_summary_can_filter_portfolio_and_reports_position_weight(self):
        trades = [
            Trade("", date(2024, 1, 2), "GOOG", "BUY", 10, 100, 0, "", "Active"),
            Trade("", date(2024, 1, 3), "GOOG", "BUY", 5, 80, 0, "", "DCA"),
            Trade("", date(2024, 1, 4), "MSFT", "BUY", 5, 50, 0, "", "Active"),
        ]
        dividends = [
            Dividend("", date(2024, 2, 1), "GOOG", 10, 0, "", "DCA"),
        ]
        prices = {
            "GOOG": {date(2024, 12, 31): 120},
            "MSFT": {date(2024, 12, 31): 100},
        }

        analytics = PortfolioAnalytics(FakePriceProvider(prices))
        all_summary = analytics.summary(trades, dividends, date(2024, 12, 31))
        active_summary = analytics.summary(trades, dividends, date(2024, 12, 31), portfolio="Active")

        self.assertAlmostEqual(all_summary["market_value"], 2300.0, places=2)
        self.assertAlmostEqual(active_summary["market_value"], 1700.0, places=2)
        self.assertEqual(active_summary["portfolio"], "Active")
        self.assertEqual([position["symbol"] for position in active_summary["positions"]], ["GOOG", "MSFT"])
        self.assertAlmostEqual(active_summary["positions"][0]["allocation_pct"], 1200 / 1700, places=6)

    def test_allocation_returns_overall_and_each_portfolio(self):
        trades = [
            Trade("", date(2024, 1, 2), "GOOG", "BUY", 10, 100, 0, "", "Active"),
            Trade("", date(2024, 1, 3), "GOOG", "BUY", 5, 80, 0, "", "DCA"),
            Trade("", date(2024, 1, 4), "MSFT", "BUY", 5, 50, 0, "", "Active"),
        ]
        prices = {
            "GOOG": {date(2024, 12, 31): 120},
            "MSFT": {date(2024, 12, 31): 100},
        }

        analytics = PortfolioAnalytics(FakePriceProvider(prices))
        result = analytics.allocation(trades, [], date(2024, 12, 31))

        self.assertEqual(result["portfolio"], "All")
        self.assertEqual(result["selected"], result["overall"])
        self.assertEqual([item["portfolio"] for item in result["portfolios"]], ["Active", "DCA"])
        self.assertAlmostEqual(result["overall"]["positions"][0]["allocation_pct"], 1800 / 2300, places=6)
        self.assertAlmostEqual(result["portfolios"][0]["positions"][0]["allocation_pct"], 1200 / 1700, places=6)

        active_result = analytics.allocation(trades, [], date(2024, 12, 31), portfolio="Active")
        self.assertEqual(active_result["portfolio"], "Active")
        self.assertEqual([position["symbol"] for position in active_result["selected"]["positions"]], ["GOOG", "MSFT"])
        self.assertAlmostEqual(active_result["selected"]["positions"][0]["allocation_pct"], 1200 / 1700, places=6)

    def test_period_summary_reports_values_for_selected_date_range(self):
        trades = [
            Trade("", date(2024, 1, 2), "AAPL", "BUY", 10, 10, 0, ""),
            Trade("", date(2024, 3, 1), "AAPL", "BUY", 5, 20, 0, ""),
            Trade("", date(2024, 7, 1), "AAPL", "SELL", 4, 30, 0, ""),
        ]
        dividends = [
            Dividend("", date(2024, 8, 1), "AAPL", 20, 0, ""),
        ]
        prices = {
            "AAPL": {
                date(2024, 5, 31): 15,
                date(2024, 9, 30): 25,
            }
        }

        analytics = PortfolioAnalytics(FakePriceProvider(prices))
        result = analytics.period_summary(trades, dividends, date(2024, 6, 1), date(2024, 9, 30))

        self.assertEqual(result["start"], "2024-06-01")
        self.assertEqual(result["end"], "2024-09-30")
        self.assertAlmostEqual(result["market_value"], 275.0, places=2)
        self.assertAlmostEqual(result["market_value_change"], 50.0, places=2)
        self.assertAlmostEqual(result["sell_proceeds"], 120.0, places=2)
        self.assertAlmostEqual(result["realized_gain"], 66.67, places=2)
        self.assertAlmostEqual(result["sell_gain"], 66.67, places=2)
        self.assertAlmostEqual(result["dividends"], 20.0, places=2)
        self.assertAlmostEqual(result["total_gain"], 190.0, places=2)

    def test_summary_converts_us_and_taiwan_holdings_to_display_currency(self):
        trades = [
            Trade("", date(2024, 1, 2), "GOOG", "BUY", 10, 100, 0, "", "Active", currency="USD"),
            Trade("", date(2024, 1, 2), "2330.TW", "BUY", 10, 500, 0, "", "Active", currency="TWD"),
        ]
        dividends = [
            Dividend("", date(2024, 2, 1), "GOOG", 10, 0, "", "Active", currency="USD"),
        ]
        prices = {
            "GOOG": {date(2024, 12, 31): 120},
            "2330.TW": {date(2024, 12, 31): 600},
        }
        fx_rates = {
            ("USD", "TWD", date(2024, 1, 2)): 30,
            ("USD", "TWD", date(2024, 2, 1)): 30.5,
            ("USD", "TWD", date(2024, 12, 31)): 31,
        }

        analytics = PortfolioAnalytics(FakePriceProvider(prices, fx_rates))
        summary = analytics.summary(trades, dividends, date(2024, 12, 31), display_currency="TWD")

        self.assertEqual(summary["currency"], "TWD")
        self.assertAlmostEqual(summary["buy_cost"], 35000.0, places=2)
        self.assertAlmostEqual(summary["market_value"], 43200.0, places=2)
        self.assertAlmostEqual(summary["dividends"], 305.0, places=2)
        self.assertAlmostEqual(summary["total_gain"], 8505.0, places=2)
        self.assertEqual({position["currency"] for position in summary["positions"]}, {"USD", "TWD"})

    def test_performance_result_is_cached_by_records_and_query(self):
        trades = [
            Trade("", date(2024, 1, 2), "AAPL", "BUY", 10, 10, 0, ""),
        ]
        prices = {
            "AAPL": {
                date(2024, 1, 31): 11,
                date(2024, 2, 29): 12,
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            analytics = PortfolioAnalytics(FakePriceProvider(prices), result_cache=JSONResultCache(temp_dir))
            first = analytics.performance(trades, [], date(2024, 1, 1), date(2024, 2, 29), "monthly")
            second = analytics.performance(trades, [], date(2024, 1, 1), date(2024, 2, 29), "monthly")

            self.assertFalse(first["cache"]["hit"])
            self.assertTrue(second["cache"]["hit"])
            self.assertEqual(first["points"], second["points"])


if __name__ == "__main__":
    unittest.main()
