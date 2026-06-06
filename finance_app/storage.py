from __future__ import annotations

import csv
from pathlib import Path
from threading import RLock
from typing import Iterable

from .models import Dividend, Trade


TRADE_FIELDS = ["id", "date", "symbol", "side", "quantity", "price", "fees", "notes"]
DIVIDEND_FIELDS = ["id", "date", "symbol", "gross_amount", "tax", "notes"]


class CSVStore:
    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.trades_path = self.data_dir / "trades.csv"
        self.dividends_path = self.data_dir / "dividends.csv"
        self.price_cache_dir = self.data_dir / "price_cache"
        self._lock = RLock()
        self._ensure_files()

    def _ensure_files(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.price_cache_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_csv(self.trades_path, TRADE_FIELDS)
        self._ensure_csv(self.dividends_path, DIVIDEND_FIELDS)

    @staticmethod
    def _ensure_csv(path: Path, fields: list[str]) -> None:
        if path.exists():
            return
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()

    def list_trades(self) -> list[Trade]:
        with self._lock:
            rows = self._read_rows(self.trades_path)
        trades = [Trade.from_dict(row) for row in rows]
        return sorted(trades, key=lambda item: (item.date, item.symbol, item.id))

    def list_dividends(self) -> list[Dividend]:
        with self._lock:
            rows = self._read_rows(self.dividends_path)
        dividends = [Dividend.from_dict(row) for row in rows]
        return sorted(dividends, key=lambda item: (item.date, item.symbol, item.id))

    def add_trade(self, trade: Trade) -> Trade:
        saved = trade.with_id()
        with self._lock:
            rows = self._read_rows(self.trades_path)
            rows.append(saved.to_row())
            self._write_rows(self.trades_path, TRADE_FIELDS, rows)
        return saved

    def add_dividend(self, dividend: Dividend) -> Dividend:
        saved = dividend.with_id()
        with self._lock:
            rows = self._read_rows(self.dividends_path)
            rows.append(saved.to_row())
            self._write_rows(self.dividends_path, DIVIDEND_FIELDS, rows)
        return saved

    def delete_trade(self, record_id: str) -> bool:
        return self._delete_by_id(self.trades_path, TRADE_FIELDS, record_id)

    def delete_dividend(self, record_id: str) -> bool:
        return self._delete_by_id(self.dividends_path, DIVIDEND_FIELDS, record_id)

    def _delete_by_id(self, path: Path, fields: list[str], record_id: str) -> bool:
        with self._lock:
            rows = self._read_rows(path)
            remaining = [row for row in rows if row.get("id") != record_id]
            if len(remaining) == len(rows):
                return False
            self._write_rows(path, fields, remaining)
            return True

    @staticmethod
    def _read_rows(path: Path) -> list[dict[str, str]]:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for row in reader]

    @staticmethod
    def _write_rows(path: Path, fields: list[str], rows: Iterable[dict[str, str]]) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(path)
