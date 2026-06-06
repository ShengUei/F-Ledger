from __future__ import annotations

import csv
import json
from pathlib import Path
from threading import RLock
from typing import Iterable, Protocol, runtime_checkable

from .models import DEFAULT_PORTFOLIO, Dividend, Trade, normalize_currency


CURRENT_SCHEMA_VERSION = 3
TRADE_FIELDS = ["id", "date", "symbol", "side", "quantity", "price", "fees", "currency", "portfolio", "notes"]
DIVIDEND_FIELDS = ["id", "date", "symbol", "gross_amount", "tax", "currency", "portfolio", "notes"]


@runtime_checkable
class StorageBackend(Protocol):
    price_cache_dir: Path
    result_cache_dir: Path

    def list_trades(self) -> list[Trade]:
        ...

    def list_dividends(self) -> list[Dividend]:
        ...

    def add_trade(self, trade: Trade) -> Trade:
        ...

    def add_dividend(self, dividend: Dividend) -> Dividend:
        ...

    def delete_trade(self, record_id: str) -> bool:
        ...

    def delete_dividend(self, record_id: str) -> bool:
        ...

    def clear_result_cache(self) -> None:
        ...


class CSVStore:
    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.trades_path = self.data_dir / "trades.csv"
        self.dividends_path = self.data_dir / "dividends.csv"
        self.metadata_path = self.data_dir / "metadata.json"
        self.price_cache_dir = self.data_dir / "price_cache"
        self.result_cache_dir = self.data_dir / "result_cache"
        self._lock = RLock()
        self._ensure_files()

    def _ensure_files(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.price_cache_dir.mkdir(parents=True, exist_ok=True)
        self.result_cache_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_csv(self.trades_path, TRADE_FIELDS)
        self._ensure_csv(self.dividends_path, DIVIDEND_FIELDS)
        self._write_metadata()

    @staticmethod
    def _ensure_csv(path: Path, fields: list[str]) -> None:
        if path.exists() and path.stat().st_size > 0:
            with path.open("r", newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                existing_fields = reader.fieldnames or []
                rows = [dict(row) for row in reader]
            if existing_fields == fields:
                return
            normalized_rows = [CSVStore._normalize_row(row, fields) for row in rows]
            CSVStore._write_rows(path, fields, normalized_rows)
            return
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()

    def list_trades(self) -> list[Trade]:
        with self._lock:
            rows = self._read_rows(self.trades_path)
        trades = [Trade.from_dict(row) for row in rows]
        return sorted(trades, key=lambda item: (item.date, item.portfolio, item.symbol, item.id))

    def list_dividends(self) -> list[Dividend]:
        with self._lock:
            rows = self._read_rows(self.dividends_path)
        dividends = [Dividend.from_dict(row) for row in rows]
        return sorted(dividends, key=lambda item: (item.date, item.portfolio, item.symbol, item.id))

    def add_trade(self, trade: Trade) -> Trade:
        saved = trade.with_id()
        with self._lock:
            rows = self._read_rows(self.trades_path)
            rows.append(saved.to_row())
            self._write_rows(self.trades_path, TRADE_FIELDS, rows)
            self.clear_result_cache()
        return saved

    def add_dividend(self, dividend: Dividend) -> Dividend:
        saved = dividend.with_id()
        with self._lock:
            rows = self._read_rows(self.dividends_path)
            rows.append(saved.to_row())
            self._write_rows(self.dividends_path, DIVIDEND_FIELDS, rows)
            self.clear_result_cache()
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
            self.clear_result_cache()
            return True

    def clear_result_cache(self) -> None:
        if not self.result_cache_dir.exists():
            return
        for path in self.result_cache_dir.glob("*.json"):
            try:
                path.unlink()
            except OSError:
                pass

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

    @staticmethod
    def _normalize_row(row: dict[str, str], fields: list[str]) -> dict[str, str]:
        normalized = {}
        for field in fields:
            if field == "portfolio":
                normalized[field] = row.get(field) or DEFAULT_PORTFOLIO
            elif field == "currency":
                normalized[field] = normalize_currency(row.get(field, ""), row.get("symbol", ""))
            else:
                normalized[field] = row.get(field, "")
        return normalized

    def _write_metadata(self) -> None:
        payload = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "storage_backend": "csv",
            "files": {
                "trades": self.trades_path.name,
                "dividends": self.dividends_path.name,
                "price_cache": self.price_cache_dir.name,
                "result_cache": self.result_cache_dir.name,
            },
        }
        temp_path = self.metadata_path.with_suffix(self.metadata_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.metadata_path)
