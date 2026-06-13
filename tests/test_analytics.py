import unittest
import tempfile
from datetime import date

from finance_app.analytics import PortfolioAnalytics, max_drawdown_pct, xirr
from finance_app.cache import JSONResultCache
from finance_app.models import Dividend, Trade


class FakePriceProvider:
    def __init__(self, prices, fx_rates=None):
        self.prices = prices
        self.fx_rates = fx_rates or {}
        self.price_calls = 0
        self.fx_calls = 0

    def get_prices(self, symbol, start, end):
        self.price_calls += 1
        return self.prices.get(symbol, {})

    def get_fx_rate(self, from_currency, to_currency, as_of):
        self.fx_calls += 1
        if from_currency == to_currency:
            return 1.0
        return self.fx_rates.get((from_currency, to_currency, as_of), 1.0)


class FailingFxProvider(FakePriceProvider):
    def get_fx_rate(self, from_currency, to_currency, as_of):
        self.fx_calls += 1
        raise ValueError("no rate")


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
            Trade("", date(2023, 12, 2), "AAPL", "BUY", 10, 10, 0, ""),
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

    def test_period_summary_carries_forward_opening_positions_and_rebases(self):
        # A position opened before the window must stay in the holdings (market value /
        # positions), while the gain/dividends/cost figures reflect only the window,
        # rebased against the value carried in at the start (Model A / YTD).
        trades = [
            Trade("", date(2024, 1, 2), "AAPL", "BUY", 10, 10, 0, ""),  # opened before window
            Trade("", date(2025, 3, 1), "AAPL", "BUY", 10, 20, 0, ""),  # bought during window
        ]
        dividends = [
            Dividend("", date(2025, 6, 1), "AAPL", 30, 0, ""),  # paid during window
        ]
        prices = {
            "AAPL": {
                date(2024, 12, 31): 15,  # opening baseline (day before window start)
                date(2025, 12, 31): 25,  # window end
            }
        }

        analytics = PortfolioAnalytics(FakePriceProvider(prices))
        result = analytics.period_summary(trades, dividends, date(2025, 1, 1), date(2025, 12, 31))

        # Carry-forward: the pre-window lot is still held at window end.
        self.assertEqual([position["symbol"] for position in result["positions"]], ["AAPL"])
        self.assertAlmostEqual(result["positions"][0]["quantity"], 20.0, places=2)
        self.assertAlmostEqual(result["market_value"], 500.0, places=2)
        # Rebased to the window: only the window's buy, dividend and value change count.
        self.assertAlmostEqual(result["buy_cost"], 200.0, places=2)
        self.assertAlmostEqual(result["dividends"], 30.0, places=2)
        self.assertAlmostEqual(result["market_value_change"], 350.0, places=2)
        self.assertAlmostEqual(result["total_gain"], 180.0, places=2)

    def test_performance_carries_forward_prior_positions_and_rebases(self):
        # OLD is bought the prior year and still held; the window view must include it
        # (carry-forward) and rebase the gain to the start of the window.
        trades = [
            Trade("", date(2025, 6, 1), "OLD", "BUY", 2, 100, 0, ""),
            Trade("", date(2026, 1, 10), "NEW", "BUY", 1, 50, 0, ""),
        ]
        prices = {
            "OLD": {date(2025, 12, 31): 100, date(2026, 1, 31): 200},
            "NEW": {date(2026, 1, 31): 60},
        }

        analytics = PortfolioAnalytics(FakePriceProvider(prices))
        result = analytics.performance(
            trades,
            [],
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
            interval="monthly",
        )

        self.assertEqual([point["date"] for point in result["points"]], ["2026-01-31"])
        # OLD (2 * 200 = 400) is carried forward alongside NEW (1 * 60 = 60).
        self.assertAlmostEqual(result["points"][0]["market_value"], 460.0, places=2)
        # Gain rebased to the 2025-12-31 opening value (OLD flat at 100 -> only the
        # January appreciation and the new buy contribute): (460 - 250) - 0 = 210.
        self.assertAlmostEqual(result["points"][0]["total_gain"], 210.0, places=2)
        self.assertEqual([item["year"] for item in result["annual"]], [2026])
        self.assertAlmostEqual(result["annual"][0]["ending_market_value"], 460.0, places=2)

    def test_performance_all_time_view_matches_cumulative_summary(self):
        # When the window starts at the first activity ("全部"), the baseline is empty so
        # rebasing is a no-op and the final point equals the cumulative summary.
        trades = [
            Trade("", date(2024, 3, 1), "AAPL", "BUY", 10, 10, 0, ""),
            Trade("", date(2025, 2, 1), "AAPL", "BUY", 10, 20, 0, ""),
        ]
        prices = {"AAPL": {date(2024, 12, 31): 15, date(2025, 12, 31): 30}}

        analytics = PortfolioAnalytics(FakePriceProvider(prices))
        result = analytics.performance(
            trades, [], start=date(2024, 3, 1), end=date(2025, 12, 31), interval="yearly"
        )
        cumulative = analytics.summary(trades, [], date(2025, 12, 31))

        last_point = result["points"][-1]
        self.assertEqual(last_point["date"], "2025-12-31")
        self.assertAlmostEqual(last_point["market_value"], cumulative["market_value"], places=2)
        self.assertAlmostEqual(last_point["total_gain"], cumulative["total_gain"], places=2)
        self.assertAlmostEqual(last_point["return_pct"], cumulative["return_pct"], places=6)

    def test_overview_reports_all_time_total_return_and_current_year_figures(self):
        # Total return is all-time; YTD growth and realized P&L are the current calendar year.
        trades = [
            Trade("", date(2024, 1, 2), "AAPL", "BUY", 10, 10, 0, ""),  # opened a prior year
            Trade("", date(2026, 3, 1), "AAPL", "SELL", 4, 30, 0, ""),  # realized this year
        ]
        prices = {
            "AAPL": {
                date(2025, 12, 31): 20,  # value carried into the current year
                date(2026, 6, 1): 30,
            }
        }

        analytics = PortfolioAnalytics(FakePriceProvider(prices))
        result = analytics.overview(trades, [], date(2026, 6, 1))

        self.assertEqual(result["year"], 2026)
        # All-time: bought at 10, now worth 30 plus an 80 realized gain -> doubled cost.
        self.assertAlmostEqual(result["total_return_pct"], 2.0, places=6)
        self.assertAlmostEqual(result["total_gain"], 200.0, places=2)
        self.assertAlmostEqual(result["market_value"], 180.0, places=2)
        # YTD: only the move from the 2025-12-31 value (200) counts this year.
        self.assertAlmostEqual(result["ytd_gain"], 100.0, places=2)
        self.assertAlmostEqual(result["ytd_return_pct"], 0.5, places=6)
        self.assertAlmostEqual(result["ytd_realized_gain"], 80.0, places=2)

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

    def test_price_and_fx_lookups_are_memoized_per_instance(self):
        trades = [
            Trade("", date(2024, 1, 2), "GOOG", "BUY", 10, 100, 0, "", currency="USD"),
            Trade("", date(2024, 1, 2), "GOOG", "BUY", 5, 100, 0, "", currency="USD"),
            Trade("", date(2024, 1, 2), "GOOG", "BUY", 2, 100, 0, "", currency="USD"),
        ]
        prices = {"GOOG": {date(2024, 12, 31): 120}}
        fx_rates = {("USD", "TWD", date(2024, 1, 2)): 30, ("USD", "TWD", date(2024, 12, 31)): 31}
        provider = FakePriceProvider(prices, fx_rates)
        analytics = PortfolioAnalytics(provider)

        analytics.summary(trades, [], date(2024, 12, 31), display_currency="TWD")
        # Three same-day trades plus the position price conversion: one FX call per unique date.
        self.assertEqual(provider.fx_calls, 2)
        self.assertEqual(provider.price_calls, 1)

        analytics.summary(trades, [], date(2024, 12, 31), display_currency="TWD")
        self.assertEqual(provider.fx_calls, 2)
        self.assertEqual(provider.price_calls, 1)

    def test_fx_failure_warns_once_per_pair_and_date(self):
        trades = [
            Trade("", date(2024, 1, 2), "GOOG", "BUY", 10, 100, 0, "", currency="USD"),
            Trade("", date(2024, 1, 2), "GOOG", "BUY", 5, 100, 0, "", currency="USD"),
        ]
        prices = {"GOOG": {date(2024, 1, 2): 120}}
        provider = FailingFxProvider(prices)
        analytics = PortfolioAnalytics(provider)

        summary = analytics.summary(trades, [], date(2024, 1, 2), display_currency="TWD")

        fx_warnings = [warning for warning in summary["warnings"] if "USD/TWD" in warning]
        self.assertEqual(len(fx_warnings), 1)
        self.assertEqual(provider.fx_calls, 1)

    def test_allocation_shares_price_lookups_across_portfolios(self):
        trades = [
            Trade("", date(2024, 1, 2), "GOOG", "BUY", 10, 100, 0, "", "Active"),
            Trade("", date(2024, 1, 2), "GOOG", "BUY", 5, 80, 0, "", "DCA"),
        ]
        prices = {"GOOG": {date(2024, 12, 31): 120}}
        provider = FakePriceProvider(prices)
        analytics = PortfolioAnalytics(provider)

        result = analytics.allocation(trades, [], date(2024, 12, 31))

        self.assertEqual([item["portfolio"] for item in result["portfolios"]], ["Active", "DCA"])
        self.assertLessEqual(provider.price_calls, 3)

    def test_period_summary_reports_annualized_return(self):
        trades = [
            Trade("", date(2024, 1, 2), "AAPL", "BUY", 10, 100, 0, ""),
        ]
        prices = {"AAPL": {date(2024, 12, 31): 110}}

        analytics = PortfolioAnalytics(FakePriceProvider(prices))
        result = analytics.period_summary(trades, [], date(2024, 1, 1), date(2024, 12, 31))

        self.assertAlmostEqual(result["annualized_return_pct"], 0.10, places=2)

    def test_period_summary_annualized_return_is_null_when_undefined(self):
        analytics = PortfolioAnalytics(FakePriceProvider({}))
        result = analytics.period_summary([], [], date(2024, 1, 1), date(2024, 12, 31))
        self.assertIsNone(result["annualized_return_pct"])

    def test_xirr_known_value_and_undefined_cases(self):
        rate = xirr([(date(2024, 1, 1), -1000.0), (date(2024, 12, 31), 1100.0)])
        self.assertAlmostEqual(rate, 0.10, places=2)

        self.assertIsNone(xirr([]))
        self.assertIsNone(xirr([(date(2024, 1, 1), -1000.0)]))
        self.assertIsNone(xirr([(date(2024, 1, 1), -1000.0), (date(2024, 6, 1), -500.0)]))
        self.assertIsNone(xirr([(date(2024, 1, 1), -1000.0), (date(2024, 1, 1), 1100.0)]))

    def test_max_drawdown_from_return_series(self):
        points = [
            {"return_pct": 0.0},
            {"return_pct": 0.5},
            {"return_pct": 0.2},
            {"return_pct": 0.8},
        ]
        self.assertAlmostEqual(max_drawdown_pct(points), 1 - 1.2 / 1.5, places=6)
        self.assertEqual(max_drawdown_pct([]), 0.0)
        self.assertEqual(max_drawdown_pct([{"return_pct": 0.3}]), 0.0)

    def test_performance_includes_max_drawdown(self):
        trades = [
            Trade("", date(2024, 1, 2), "AAPL", "BUY", 10, 10, 0, ""),
        ]
        prices = {
            "AAPL": {
                date(2024, 1, 31): 12,
                date(2024, 2, 29): 9,
                date(2024, 3, 31): 13,
            }
        }

        analytics = PortfolioAnalytics(FakePriceProvider(prices))
        result = analytics.performance(trades, [], date(2024, 1, 1), date(2024, 3, 31), "monthly")

        self.assertIn("max_drawdown_pct", result)
        self.assertGreater(result["max_drawdown_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
