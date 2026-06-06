from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import uuid4


DATE_FORMAT = "%Y-%m-%d"


def make_id() -> str:
    return uuid4().hex


def parse_date(value: Any, field: str = "date") -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), DATE_FORMAT).date()
        except ValueError as exc:
            raise ValueError(f"{field} must use YYYY-MM-DD") from exc
    raise ValueError(f"{field} must use YYYY-MM-DD")


def parse_float(value: Any, field: str) -> float:
    if value is None or value == "":
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if parsed != parsed:
        raise ValueError(f"{field} must be a number")
    return parsed


def normalize_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    return symbol


def money_to_text(value: float) -> str:
    return f"{value:.10g}"


@dataclass
class Trade:
    id: str
    date: date
    symbol: str
    side: str
    quantity: float
    price: float
    fees: float = 0.0
    notes: str = ""

    def __post_init__(self) -> None:
        self.id = str(self.id or "")
        self.date = parse_date(self.date)
        self.symbol = normalize_symbol(self.symbol)
        self.side = str(self.side or "").strip().upper()
        self.quantity = parse_float(self.quantity, "quantity")
        self.price = parse_float(self.price, "price")
        self.fees = parse_float(self.fees, "fees")
        self.notes = str(self.notes or "")
        self.validate()

    def validate(self) -> None:
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if self.quantity <= 0:
            raise ValueError("quantity must be greater than 0")
        if self.price <= 0:
            raise ValueError("price must be greater than 0")
        if self.fees < 0:
            raise ValueError("fees cannot be negative")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trade":
        return cls(
            id=str(data.get("id", "")),
            date=parse_date(data.get("date")),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            quantity=parse_float(data.get("quantity"), "quantity"),
            price=parse_float(data.get("price"), "price"),
            fees=parse_float(data.get("fees", 0), "fees"),
            notes=str(data.get("notes", "")),
        )

    def with_id(self) -> "Trade":
        if self.id:
            return self
        return Trade(
            id=make_id(),
            date=self.date,
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            price=self.price,
            fees=self.fees,
            notes=self.notes,
        )

    def to_row(self) -> dict[str, str]:
        return {
            "id": self.id,
            "date": self.date.strftime(DATE_FORMAT),
            "symbol": self.symbol,
            "side": self.side,
            "quantity": money_to_text(self.quantity),
            "price": money_to_text(self.price),
            "fees": money_to_text(self.fees),
            "notes": self.notes,
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "date": self.date.strftime(DATE_FORMAT),
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "fees": self.fees,
            "notes": self.notes,
        }


@dataclass
class Dividend:
    id: str
    date: date
    symbol: str
    gross_amount: float
    tax: float = 0.0
    notes: str = ""

    def __post_init__(self) -> None:
        self.id = str(self.id or "")
        self.date = parse_date(self.date)
        self.symbol = normalize_symbol(self.symbol)
        self.gross_amount = parse_float(self.gross_amount, "gross_amount")
        self.tax = parse_float(self.tax, "tax")
        self.notes = str(self.notes or "")
        self.validate()

    def validate(self) -> None:
        if self.gross_amount < 0:
            raise ValueError("gross_amount cannot be negative")
        if self.tax < 0:
            raise ValueError("tax cannot be negative")

    @property
    def net_amount(self) -> float:
        return self.gross_amount - self.tax

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Dividend":
        return cls(
            id=str(data.get("id", "")),
            date=parse_date(data.get("date")),
            symbol=data.get("symbol", ""),
            gross_amount=parse_float(data.get("gross_amount"), "gross_amount"),
            tax=parse_float(data.get("tax", 0), "tax"),
            notes=str(data.get("notes", "")),
        )

    def with_id(self) -> "Dividend":
        if self.id:
            return self
        return Dividend(
            id=make_id(),
            date=self.date,
            symbol=self.symbol,
            gross_amount=self.gross_amount,
            tax=self.tax,
            notes=self.notes,
        )

    def to_row(self) -> dict[str, str]:
        return {
            "id": self.id,
            "date": self.date.strftime(DATE_FORMAT),
            "symbol": self.symbol,
            "gross_amount": money_to_text(self.gross_amount),
            "tax": money_to_text(self.tax),
            "notes": self.notes,
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "date": self.date.strftime(DATE_FORMAT),
            "symbol": self.symbol,
            "gross_amount": self.gross_amount,
            "tax": self.tax,
            "net_amount": self.net_amount,
            "notes": self.notes,
        }
