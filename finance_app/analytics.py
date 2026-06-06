from __future__ import annotations

import calendar
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from .cache import NullResultCache, ResultCache
from .models import DEFAULT_DISPLAY_CURRENCY, Dividend, Trade, normalize_currency, normalize_portfolio


class PriceProvider(Protocol):
    def get_prices(self, symbol: str, start: date, end: date) -> dict[date, float]:
        ...

    def get_fx_rate(self, from_currency: str, to_currency: str, as_of: date) -> float:
        ...


@dataclass
class PositionState:
    symbol: str
    currency: str
    quantity: float = 0.0
    cost_basis: float = 0.0
    display_cost_basis: float = 0.0
    realized_gain: float = 0.0
    buy_cost: float = 0.0
    sell_proceeds: float = 0.0
    last_trade_price: float | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def average_cost(self) -> float:
        if self.quantity <= 0:
            return 0.0
        return self.cost_basis / self.quantity

    @property
    def display_average_cost(self) -> float:
        if self.quantity <= 0:
            return 0.0
        return self.display_cost_basis / self.quantity


class PortfolioAnalytics:
    def __init__(self, price_provider: PriceProvider, result_cache: ResultCache | None = None) -> None:
        self.price_provider = price_provider
        self.result_cache = result_cache or NullResultCache()

    def summary(
        self,
        trades: list[Trade],
        dividends: list[Dividend],
        as_of: date,
        portfolio: str | None = None,
        display_currency: str = DEFAULT_DISPLAY_CURRENCY,
    ) -> dict:
        report_currency = normalize_report_currency(display_currency)
        portfolio_filter = normalize_portfolio_filter(portfolio)
        trades, dividends = filter_records(trades, dividends, portfolio_filter)
        relevant_trades = sorted(
            [trade for trade in trades if trade.date <= as_of],
            key=lambda item: (item.date, 0 if item.side == "BUY" else 1, item.symbol, item.id),
        )
        relevant_dividends = [dividend for dividend in dividends if dividend.date <= as_of]
        warnings: list[str] = []
        states = self._build_positions(relevant_trades, report_currency, warnings)
        dividend_totals = self._dividend_totals(relevant_dividends, report_currency, warnings)
        start = self._first_activity_date(relevant_trades, relevant_dividends, as_of)

        market_value = 0.0
        positions = []
        for _key, state in sorted(states.items()):
            if abs(state.quantity) < 1e-9:
                continue
            price, source = self._latest_price(state.symbol, start, as_of)
            if price is None:
                price = state.last_trade_price or state.average_cost
                source = "latest_trade"
                warnings.append(f"{state.symbol}: no Yahoo price available; using latest trade price.")
            display_price = self._convert(price, state.currency, report_currency, as_of, warnings)
            value = state.quantity * display_price
            market_value += value
            positions.append(
                {
                    "symbol": state.symbol,
                    "currency": state.currency,
                    "quantity": round_number(state.quantity),
                    "average_cost": round_money(state.display_average_cost),
                    "source_average_cost": round_money(state.average_cost),
                    "cost_basis": round_money(state.display_cost_basis),
                    "source_cost_basis": round_money(state.cost_basis),
                    "last_price": round_money(display_price),
                    "source_last_price": round_money(price),
                    "price_source": source,
                    "market_value": round_money(value),
                    "unrealized_gain": round_money(value - state.display_cost_basis),
                    "dividends": round_money(dividend_totals.get((state.symbol, state.currency), 0.0)),
                    "allocation_pct": 0.0,
                }
            )

        for position in positions:
            position["allocation_pct"] = round_number(position["market_value"] / market_value) if market_value else 0.0

        buy_cost = sum(state.buy_cost for state in states.values())
        sell_proceeds = sum(state.sell_proceeds for state in states.values())
        realized_gain = sum(state.realized_gain for state in states.values())
        dividends_total = sum(dividend_totals.values())
        cash_flow = -buy_cost + sell_proceeds + dividends_total
        total_gain = market_value + cash_flow
        return_pct = total_gain / buy_cost if buy_cost else 0.0

        return {
            "as_of": as_of.isoformat(),
            "portfolio": portfolio_filter or "All",
            "currency": report_currency,
            "market_value": round_money(market_value),
            "buy_cost": round_money(buy_cost),
            "sell_proceeds": round_money(sell_proceeds),
            "cash_flow": round_money(cash_flow),
            "realized_gain": round_money(realized_gain),
            "dividends": round_money(dividends_total),
            "total_gain": round_money(total_gain),
            "return_pct": round_number(return_pct),
            "positions": positions,
            "warnings": warnings + [warning for state in states.values() for warning in state.warnings],
        }

    def performance(
        self,
        trades: list[Trade],
        dividends: list[Dividend],
        start: date,
        end: date,
        interval: str = "monthly",
        portfolio: str | None = None,
        display_currency: str = DEFAULT_DISPLAY_CURRENCY,
    ) -> dict:
        if end < start:
            raise ValueError("end must be on or after start")
        report_currency = normalize_report_currency(display_currency)
        cache_key = performance_cache_key(trades, dividends, start, end, interval, portfolio, report_currency)
        cached = self.result_cache.get(cache_key)
        if cached is not None:
            cached["cache"] = {"hit": True, "key": cache_key}
            return cached

        points = [
            self._point_from_summary(
                self.summary(trades, dividends, point, portfolio=portfolio, display_currency=report_currency)
            )
            for point in date_points(start, end, interval)
        ]
        annual = self._annual_points(trades, dividends, start, end, portfolio, report_currency)
        result = {
            "portfolio": normalize_portfolio_filter(portfolio) or "All",
            "currency": report_currency,
            "points": points,
            "annual": annual,
        }
        self.result_cache.set(cache_key, result)
        result["cache"] = {"hit": False, "key": cache_key}
        return result

    def allocation(
        self,
        trades: list[Trade],
        dividends: list[Dividend],
        as_of: date,
        display_currency: str = DEFAULT_DISPLAY_CURRENCY,
        portfolio: str | None = None,
    ) -> dict:
        report_currency = normalize_report_currency(display_currency)
        portfolio_filter = normalize_portfolio_filter(portfolio)
        overall = self.summary(trades, dividends, as_of, display_currency=report_currency)
        selected = (
            self.summary(trades, dividends, as_of, portfolio=portfolio_filter, display_currency=report_currency)
            if portfolio_filter
            else overall
        )
        portfolios = []
        for portfolio_name in portfolio_names(trades, dividends):
            summary = self.summary(trades, dividends, as_of, portfolio=portfolio_name, display_currency=report_currency)
            portfolios.append(
                {
                    "portfolio": portfolio_name,
                    "market_value": summary["market_value"],
                    "total_gain": summary["total_gain"],
                    "dividends": summary["dividends"],
                    "positions": summary["positions"],
                }
            )
        return {
            "as_of": as_of.isoformat(),
            "portfolio": portfolio_filter or "All",
            "currency": report_currency,
            "selected": selected,
            "overall": overall,
            "portfolios": portfolios,
        }

    def _annual_points(
        self,
        trades: list[Trade],
        dividends: list[Dividend],
        start: date,
        end: date,
        portfolio: str | None = None,
        display_currency: str = DEFAULT_DISPLAY_CURRENCY,
    ) -> list[dict]:
        report_currency = normalize_report_currency(display_currency)
        portfolio_filter = normalize_portfolio_filter(portfolio)
        filtered_trades, filtered_dividends = filter_records(trades, dividends, portfolio_filter)
        rows = []
        for year in range(start.year, end.year + 1):
            year_start = max(start, date(year, 1, 1))
            year_end = min(end, date(year, 12, 31))
            if year_end < year_start:
                continue
            previous_day = year_start - timedelta(days=1)
            baseline = (
                self.summary(filtered_trades, filtered_dividends, previous_day, display_currency=report_currency)
                if previous_day >= date(1900, 1, 1)
                else None
            )
            ending = self.summary(filtered_trades, filtered_dividends, year_end, display_currency=report_currency)
            baseline_gain = baseline["total_gain"] if baseline else 0.0
            annual_gain = ending["total_gain"] - baseline_gain
            annual_buy_cost = sum(
                self._convert(
                    trade.quantity * trade.price + trade.fees,
                    trade.currency,
                    report_currency,
                    trade.date,
                    [],
                )
                for trade in filtered_trades
                if year_start <= trade.date <= year_end and trade.side == "BUY"
            )
            return_base = annual_buy_cost if annual_buy_cost else max(ending["buy_cost"], 1.0)
            rows.append(
                {
                    "year": year,
                    "gain": round_money(annual_gain),
                    "dividends": round_money(
                        sum(
                            self._convert(
                                dividend.net_amount,
                                dividend.currency,
                                report_currency,
                                dividend.date,
                                [],
                            )
                            for dividend in filtered_dividends
                            if year_start <= dividend.date <= year_end
                        )
                    ),
                    "return_pct": round_number(annual_gain / return_base if return_base else 0.0),
                    "ending_market_value": ending["market_value"],
                    "ending_total_gain": ending["total_gain"],
                }
            )
        return rows

    @staticmethod
    def _point_from_summary(summary: dict) -> dict:
        return {
            "date": summary["as_of"],
            "market_value": summary["market_value"],
            "total_gain": summary["total_gain"],
            "dividends": summary["dividends"],
            "realized_gain": summary["realized_gain"],
            "cash_flow": summary["cash_flow"],
            "return_pct": summary["return_pct"],
        }

    def _build_positions(
        self,
        trades: list[Trade],
        display_currency: str,
        warnings: list[str],
    ) -> dict[tuple[str, str], PositionState]:
        states: dict[tuple[str, str], PositionState] = {}
        for trade in trades:
            key = (trade.symbol, trade.currency)
            state = states.setdefault(key, PositionState(symbol=trade.symbol, currency=trade.currency))
            state.last_trade_price = trade.price
            if trade.side == "BUY":
                cost = trade.quantity * trade.price + trade.fees
                display_cost = self._convert(cost, trade.currency, display_currency, trade.date, warnings)
                state.quantity += trade.quantity
                state.cost_basis += cost
                state.display_cost_basis += display_cost
                state.buy_cost += display_cost
                continue

            proceeds = trade.quantity * trade.price - trade.fees
            display_proceeds = self._convert(proceeds, trade.currency, display_currency, trade.date, warnings)
            state.sell_proceeds += display_proceeds
            if state.quantity <= 1e-9:
                state.warnings.append(f"{trade.symbol}: sell on {trade.date.isoformat()} has no open shares.")
                continue
            avg_cost = state.average_cost
            display_avg_cost = state.display_average_cost
            sold_quantity = min(trade.quantity, state.quantity)
            removed_cost = avg_cost * sold_quantity
            display_removed_cost = display_avg_cost * sold_quantity
            state.realized_gain += display_proceeds - display_removed_cost
            state.quantity -= sold_quantity
            state.cost_basis -= removed_cost
            state.display_cost_basis -= display_removed_cost
            if trade.quantity > sold_quantity:
                state.warnings.append(f"{trade.symbol}: sell quantity exceeds open shares on {trade.date.isoformat()}.")
            if state.quantity <= 1e-9:
                state.quantity = 0.0
                state.cost_basis = 0.0
                state.display_cost_basis = 0.0
        return states

    def _dividend_totals(
        self,
        dividends: list[Dividend],
        display_currency: str,
        warnings: list[str],
    ) -> dict[tuple[str, str], float]:
        totals: dict[tuple[str, str], float] = {}
        for dividend in dividends:
            key = (dividend.symbol, dividend.currency)
            display_amount = self._convert(dividend.net_amount, dividend.currency, display_currency, dividend.date, warnings)
            totals[key] = totals.get(key, 0.0) + display_amount
        return totals

    @staticmethod
    def _first_activity_date(
        trades: list[Trade],
        dividends: list[Dividend],
        default: date,
    ) -> date:
        dates = [trade.date for trade in trades] + [dividend.date for dividend in dividends]
        return min(dates) if dates else default

    def _latest_price(self, symbol: str, start: date, as_of: date) -> tuple[float | None, str]:
        price_map = self.price_provider.get_prices(symbol, start, as_of)
        candidates = [item_date for item_date in price_map if item_date <= as_of]
        if not candidates:
            return None, "missing"
        latest = max(candidates)
        return price_map[latest], "yahoo"

    def _convert(
        self,
        amount: float,
        from_currency: str,
        to_currency: str,
        as_of: date,
        warnings: list[str],
    ) -> float:
        rate = self._fx_rate(from_currency, to_currency, as_of, warnings)
        return amount * rate

    def _fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        as_of: date,
        warnings: list[str],
    ) -> float:
        source = normalize_currency(from_currency)
        target = normalize_currency(to_currency)
        if source == target:
            return 1.0
        get_fx_rate = getattr(self.price_provider, "get_fx_rate", None)
        if get_fx_rate is None:
            warnings.append(f"{source}/{target}: no FX provider available; using 1.0.")
            return 1.0
        try:
            return float(get_fx_rate(source, target, as_of))
        except Exception:
            warnings.append(f"{source}/{target}: no FX rate available on {as_of.isoformat()}; using 1.0.")
            return 1.0


def date_points(start: date, end: date, interval: str) -> list[date]:
    interval = (interval or "monthly").lower()
    if interval == "daily":
        points = []
        current = start
        while current <= end:
            points.append(current)
            current += timedelta(days=1)
        return points
    if interval == "yearly":
        points = []
        for year in range(start.year, end.year + 1):
            point = min(end, date(year, 12, 31))
            if point >= start and (not points or points[-1] != point):
                points.append(point)
        return points

    if interval != "monthly":
        raise ValueError("interval must be daily, monthly, or yearly")

    points = []
    year = start.year
    month = start.month
    while date(year, month, 1) <= end:
        last_day = calendar.monthrange(year, month)[1]
        point = min(end, date(year, month, last_day))
        if point >= start and (not points or points[-1] != point):
            points.append(point)
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return points


def round_money(value: float) -> float:
    return round(float(value), 2)


def round_number(value: float) -> float:
    return round(float(value), 6)


def normalize_report_currency(currency: str | None) -> str:
    return normalize_currency(currency or DEFAULT_DISPLAY_CURRENCY)


def normalize_portfolio_filter(portfolio: str | None) -> str | None:
    if portfolio is None:
        return None
    normalized = normalize_portfolio(portfolio)
    return None if normalized.lower() == "all" else normalized


def filter_records(
    trades: list[Trade],
    dividends: list[Dividend],
    portfolio: str | None,
) -> tuple[list[Trade], list[Dividend]]:
    if not portfolio:
        return trades, dividends
    return (
        [trade for trade in trades if trade.portfolio == portfolio],
        [dividend for dividend in dividends if dividend.portfolio == portfolio],
    )


def portfolio_names(trades: list[Trade], dividends: list[Dividend]) -> list[str]:
    return sorted({trade.portfolio for trade in trades} | {dividend.portfolio for dividend in dividends})


def performance_cache_key(
    trades: list[Trade],
    dividends: list[Dividend],
    start: date,
    end: date,
    interval: str,
    portfolio: str | None,
    display_currency: str,
) -> str:
    payload = {
        "kind": "performance",
        "version": 1,
        "params": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "interval": interval,
            "portfolio": normalize_portfolio_filter(portfolio) or "All",
            "currency": normalize_report_currency(display_currency),
        },
        "trades": [trade.to_json() for trade in sorted(trades, key=lambda item: item.id)],
        "dividends": [dividend.to_json() for dividend in sorted(dividends, key=lambda item: item.id)],
    }
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()
