from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from .models import Dividend, Trade


class PriceProvider(Protocol):
    def get_prices(self, symbol: str, start: date, end: date) -> dict[date, float]:
        ...


@dataclass
class PositionState:
    symbol: str
    quantity: float = 0.0
    cost_basis: float = 0.0
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


class PortfolioAnalytics:
    def __init__(self, price_provider: PriceProvider) -> None:
        self.price_provider = price_provider

    def summary(
        self,
        trades: list[Trade],
        dividends: list[Dividend],
        as_of: date,
    ) -> dict:
        relevant_trades = sorted(
            [trade for trade in trades if trade.date <= as_of],
            key=lambda item: (item.date, 0 if item.side == "BUY" else 1, item.symbol, item.id),
        )
        relevant_dividends = [dividend for dividend in dividends if dividend.date <= as_of]
        states = self._build_positions(relevant_trades)
        dividend_totals = self._dividend_totals(relevant_dividends)
        start = self._first_activity_date(relevant_trades, relevant_dividends, as_of)
        warnings: list[str] = []

        market_value = 0.0
        positions = []
        for symbol, state in sorted(states.items()):
            if abs(state.quantity) < 1e-9:
                continue
            price, source = self._latest_price(symbol, start, as_of)
            if price is None:
                price = state.last_trade_price or state.average_cost
                source = "latest_trade"
                warnings.append(f"{symbol}: no Yahoo price available; using latest trade price.")
            value = state.quantity * price
            market_value += value
            positions.append(
                {
                    "symbol": symbol,
                    "quantity": round_number(state.quantity),
                    "average_cost": round_money(state.average_cost),
                    "cost_basis": round_money(state.cost_basis),
                    "last_price": round_money(price),
                    "price_source": source,
                    "market_value": round_money(value),
                    "unrealized_gain": round_money(value - state.cost_basis),
                    "dividends": round_money(dividend_totals.get(symbol, 0.0)),
                }
            )

        buy_cost = sum(state.buy_cost for state in states.values())
        sell_proceeds = sum(state.sell_proceeds for state in states.values())
        realized_gain = sum(state.realized_gain for state in states.values())
        dividends_total = sum(dividend_totals.values())
        cash_flow = -buy_cost + sell_proceeds + dividends_total
        total_gain = market_value + cash_flow
        return_pct = total_gain / buy_cost if buy_cost else 0.0

        return {
            "as_of": as_of.isoformat(),
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
    ) -> dict:
        if end < start:
            raise ValueError("end must be on or after start")
        points = [self._point_from_summary(self.summary(trades, dividends, point)) for point in date_points(start, end, interval)]
        annual = self._annual_points(trades, dividends, start, end)
        return {"points": points, "annual": annual}

    def _annual_points(
        self,
        trades: list[Trade],
        dividends: list[Dividend],
        start: date,
        end: date,
    ) -> list[dict]:
        rows = []
        for year in range(start.year, end.year + 1):
            year_start = max(start, date(year, 1, 1))
            year_end = min(end, date(year, 12, 31))
            if year_end < year_start:
                continue
            previous_day = year_start - timedelta(days=1)
            baseline = self.summary(trades, dividends, previous_day) if previous_day >= date(1900, 1, 1) else None
            ending = self.summary(trades, dividends, year_end)
            baseline_gain = baseline["total_gain"] if baseline else 0.0
            annual_gain = ending["total_gain"] - baseline_gain
            annual_buy_cost = sum(
                trade.quantity * trade.price + trade.fees
                for trade in trades
                if year_start <= trade.date <= year_end and trade.side == "BUY"
            )
            return_base = annual_buy_cost if annual_buy_cost else max(ending["buy_cost"], 1.0)
            rows.append(
                {
                    "year": year,
                    "gain": round_money(annual_gain),
                    "dividends": round_money(
                        sum(dividend.net_amount for dividend in dividends if year_start <= dividend.date <= year_end)
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

    @staticmethod
    def _build_positions(trades: list[Trade]) -> dict[str, PositionState]:
        states: dict[str, PositionState] = {}
        for trade in trades:
            state = states.setdefault(trade.symbol, PositionState(symbol=trade.symbol))
            state.last_trade_price = trade.price
            if trade.side == "BUY":
                cost = trade.quantity * trade.price + trade.fees
                state.quantity += trade.quantity
                state.cost_basis += cost
                state.buy_cost += cost
                continue

            proceeds = trade.quantity * trade.price - trade.fees
            state.sell_proceeds += proceeds
            if state.quantity <= 1e-9:
                state.warnings.append(f"{trade.symbol}: sell on {trade.date.isoformat()} has no open shares.")
                continue
            avg_cost = state.average_cost
            sold_quantity = min(trade.quantity, state.quantity)
            removed_cost = avg_cost * sold_quantity
            state.realized_gain += proceeds - removed_cost
            state.quantity -= sold_quantity
            state.cost_basis -= removed_cost
            if trade.quantity > sold_quantity:
                state.warnings.append(f"{trade.symbol}: sell quantity exceeds open shares on {trade.date.isoformat()}.")
            if state.quantity <= 1e-9:
                state.quantity = 0.0
                state.cost_basis = 0.0
        return states

    @staticmethod
    def _dividend_totals(dividends: list[Dividend]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for dividend in dividends:
            totals[dividend.symbol] = totals.get(dividend.symbol, 0.0) + dividend.net_amount
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
