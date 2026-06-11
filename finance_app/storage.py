from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from collections.abc import Iterator
from typing import Iterable, Protocol, runtime_checkable

from .models import DEFAULT_PORTFOLIO, Dividend, Trade, normalize_currency


CURRENT_SCHEMA_VERSION = 4
SQLITE_FILE = "portfolio.sqlite3"
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

    def update_trade(self, record_id: str, trade: Trade) -> Trade | None:
        ...

    def update_dividend(self, record_id: str, dividend: Dividend) -> Dividend | None:
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

    def update_trade(self, record_id: str, trade: Trade) -> Trade | None:
        saved = Trade(
            id=record_id,
            date=trade.date,
            symbol=trade.symbol,
            side=trade.side,
            quantity=trade.quantity,
            price=trade.price,
            fees=trade.fees,
            notes=trade.notes,
            portfolio=trade.portfolio,
            currency=trade.currency,
        )
        return self._update_by_id(self.trades_path, TRADE_FIELDS, record_id, saved.to_row(), saved)

    def update_dividend(self, record_id: str, dividend: Dividend) -> Dividend | None:
        saved = Dividend(
            id=record_id,
            date=dividend.date,
            symbol=dividend.symbol,
            gross_amount=dividend.gross_amount,
            tax=dividend.tax,
            notes=dividend.notes,
            portfolio=dividend.portfolio,
            currency=dividend.currency,
        )
        return self._update_by_id(self.dividends_path, DIVIDEND_FIELDS, record_id, saved.to_row(), saved)

    def delete_trade(self, record_id: str) -> bool:
        return self._delete_by_id(self.trades_path, TRADE_FIELDS, record_id)

    def delete_dividend(self, record_id: str) -> bool:
        return self._delete_by_id(self.dividends_path, DIVIDEND_FIELDS, record_id)

    def _update_by_id(self, path: Path, fields: list[str], record_id: str, updated_row: dict[str, str], saved: Trade | Dividend):
        with self._lock:
            rows = self._read_rows(path)
            found = False
            updated = []
            for row in rows:
                if row.get("id") == record_id:
                    updated.append(updated_row)
                    found = True
                else:
                    updated.append(row)
            if not found:
                return None
            self._write_rows(path, fields, updated)
            self.clear_result_cache()
            return saved

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


class SQLiteStore:
    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / SQLITE_FILE
        self.metadata_path = self.data_dir / "metadata.json"
        self.trades_path = self.data_dir / "trades.csv"
        self.dividends_path = self.data_dir / "dividends.csv"
        self.price_cache_dir = self.data_dir / "price_cache"
        self.result_cache_dir = self.data_dir / "result_cache"
        self._lock = RLock()
        self._ensure_database()

    def _ensure_database(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.price_cache_dir.mkdir(parents=True, exist_ok=True)
        self.result_cache_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    fees REAL NOT NULL DEFAULT 0,
                    currency TEXT NOT NULL,
                    portfolio TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(date);
                CREATE INDEX IF NOT EXISTS idx_trades_portfolio ON trades(portfolio);
                CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);

                CREATE TABLE IF NOT EXISTS dividends (
                    id TEXT PRIMARY KEY,
                    date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    gross_amount REAL NOT NULL,
                    tax REAL NOT NULL DEFAULT 0,
                    currency TEXT NOT NULL,
                    portfolio TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_dividends_date ON dividends(date);
                CREATE INDEX IF NOT EXISTS idx_dividends_portfolio ON dividends(portfolio);
                CREATE INDEX IF NOT EXISTS idx_dividends_symbol ON dividends(symbol);
                """
            )
            connection.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
            connection.execute("PRAGMA journal_mode=WAL")
            self._write_metadata_rows(connection)
        self._migrate_legacy_csv_if_empty()
        self._write_metadata_file()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=NORMAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_trades(self) -> list[Trade]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, date, symbol, side, quantity, price, fees, currency, portfolio, notes
                FROM trades
                ORDER BY date, portfolio, symbol, id
                """
            ).fetchall()
        return [Trade.from_dict(dict(row)) for row in rows]

    def list_dividends(self) -> list[Dividend]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, date, symbol, gross_amount, tax, currency, portfolio, notes
                FROM dividends
                ORDER BY date, portfolio, symbol, id
                """
            ).fetchall()
        return [Dividend.from_dict(dict(row)) for row in rows]

    def portfolio_names(self) -> list[str]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT portfolio FROM trades UNION SELECT DISTINCT portfolio FROM dividends ORDER BY 1"
            ).fetchall()
        return [row[0] for row in rows]

    def query_records(
        self,
        *,
        kind: str | None = None,
        symbol_contains: str | None = None,
        portfolio: str | None = None,
        start: str | None = None,
        end: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[dict], int, int]:
        """Filtered, paginated trade+dividend rows; returns (rows, total, effective_page)."""
        base = """
            SELECT 'trade' AS kind, id, date, symbol, portfolio, currency, side, quantity, price, fees,
                   NULL AS gross_amount, NULL AS tax, notes
            FROM trades
            UNION ALL
            SELECT 'dividend' AS kind, id, date, symbol, portfolio, currency, NULL AS side, NULL AS quantity,
                   NULL AS price, NULL AS fees, gross_amount, tax, notes
            FROM dividends
        """
        clauses = []
        params: list[object] = []
        if kind in {"trade", "dividend"}:
            clauses.append("kind = ?")
            params.append(kind)
        if symbol_contains:
            clauses.append("instr(UPPER(symbol), ?) > 0")
            params.append(symbol_contains.upper())
        if portfolio:
            clauses.append("portfolio = ?")
            params.append(portfolio)
        if start:
            clauses.append("date >= ?")
            params.append(start)
        if end:
            clauses.append("date <= ?")
            params.append(end)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock, self._connect() as connection:
            total = connection.execute(f"SELECT COUNT(*) FROM ({base}){where}", params).fetchone()[0]
            total_pages = max(1, (total + page_size - 1) // page_size)
            effective_page = min(total_pages, max(1, page))
            offset = (effective_page - 1) * page_size
            rows = connection.execute(
                f"SELECT * FROM ({base}){where} ORDER BY date DESC, symbol DESC, id DESC LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            ).fetchall()
        return [dict(row) for row in rows], total, effective_page

    def add_trade(self, trade: Trade) -> Trade:
        saved = trade.with_id()
        with self._lock, self._connect() as connection:
            self._insert_trade(connection, saved)
            self._bump_data_version(connection)
            self.clear_result_cache()
        return saved

    def add_dividend(self, dividend: Dividend) -> Dividend:
        saved = dividend.with_id()
        with self._lock, self._connect() as connection:
            self._insert_dividend(connection, saved)
            self._bump_data_version(connection)
            self.clear_result_cache()
        return saved

    def data_version(self) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT value FROM metadata WHERE key = 'data_version'").fetchone()
        return int(row["value"]) if row else 0

    @staticmethod
    def _bump_data_version(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO metadata (key, value) VALUES ('data_version', '1')
            ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)
            """
        )

    def update_trade(self, record_id: str, trade: Trade) -> Trade | None:
        saved = Trade(
            id=record_id,
            date=trade.date,
            symbol=trade.symbol,
            side=trade.side,
            quantity=trade.quantity,
            price=trade.price,
            fees=trade.fees,
            notes=trade.notes,
            portfolio=trade.portfolio,
            currency=trade.currency,
        )
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE trades
                SET date = ?, symbol = ?, side = ?, quantity = ?, price = ?, fees = ?,
                    currency = ?, portfolio = ?, notes = ?
                WHERE id = ?
                """,
                (
                    saved.date.isoformat(),
                    saved.symbol,
                    saved.side,
                    saved.quantity,
                    saved.price,
                    saved.fees,
                    saved.currency,
                    saved.portfolio,
                    saved.notes,
                    record_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            self._bump_data_version(connection)
            self.clear_result_cache()
        return saved

    def update_dividend(self, record_id: str, dividend: Dividend) -> Dividend | None:
        saved = Dividend(
            id=record_id,
            date=dividend.date,
            symbol=dividend.symbol,
            gross_amount=dividend.gross_amount,
            tax=dividend.tax,
            notes=dividend.notes,
            portfolio=dividend.portfolio,
            currency=dividend.currency,
        )
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE dividends
                SET date = ?, symbol = ?, gross_amount = ?, tax = ?, currency = ?,
                    portfolio = ?, notes = ?
                WHERE id = ?
                """,
                (
                    saved.date.isoformat(),
                    saved.symbol,
                    saved.gross_amount,
                    saved.tax,
                    saved.currency,
                    saved.portfolio,
                    saved.notes,
                    record_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            self._bump_data_version(connection)
            self.clear_result_cache()
        return saved

    def delete_trade(self, record_id: str) -> bool:
        return self._delete_by_id("trades", record_id)

    def delete_dividend(self, record_id: str) -> bool:
        return self._delete_by_id("dividends", record_id)

    def _delete_by_id(self, table: str, record_id: str) -> bool:
        if table not in {"trades", "dividends"}:
            raise ValueError(f"unsupported table: {table}")
        with self._lock, self._connect() as connection:
            cursor = connection.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
            if cursor.rowcount == 0:
                return False
            self._bump_data_version(connection)
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

    def _migrate_legacy_csv_if_empty(self) -> None:
        with self._lock, self._connect() as connection:
            trade_count = connection.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            dividend_count = connection.execute("SELECT COUNT(*) FROM dividends").fetchone()[0]
            if trade_count or dividend_count:
                return
            trades = [Trade.from_dict(row) for row in self._legacy_csv_rows(self.trades_path, TRADE_FIELDS)]
            dividends = [Dividend.from_dict(row) for row in self._legacy_csv_rows(self.dividends_path, DIVIDEND_FIELDS)]
            for trade in trades:
                self._insert_trade(connection, trade.with_id())
            for dividend in dividends:
                self._insert_dividend(connection, dividend.with_id())

    @staticmethod
    def _legacy_csv_rows(path: Path, fields: list[str]) -> list[dict[str, str]]:
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            return [CSVStore._normalize_row(dict(row), fields) for row in reader]

    @staticmethod
    def _insert_trade(connection: sqlite3.Connection, trade: Trade) -> None:
        connection.execute(
            """
            INSERT INTO trades (id, date, symbol, side, quantity, price, fees, currency, portfolio, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.id,
                trade.date.isoformat(),
                trade.symbol,
                trade.side,
                trade.quantity,
                trade.price,
                trade.fees,
                trade.currency,
                trade.portfolio,
                trade.notes,
            ),
        )

    @staticmethod
    def _insert_dividend(connection: sqlite3.Connection, dividend: Dividend) -> None:
        connection.execute(
            """
            INSERT INTO dividends (id, date, symbol, gross_amount, tax, currency, portfolio, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dividend.id,
                dividend.date.isoformat(),
                dividend.symbol,
                dividend.gross_amount,
                dividend.tax,
                dividend.currency,
                dividend.portfolio,
                dividend.notes,
            ),
        )

    def _write_metadata_rows(self, connection: sqlite3.Connection) -> None:
        rows = {
            "schema_version": str(CURRENT_SCHEMA_VERSION),
            "storage_backend": "sqlite",
        }
        for key, value in rows.items():
            connection.execute(
                """
                INSERT INTO metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def _write_metadata_file(self) -> None:
        payload = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "storage_backend": "sqlite",
            "files": {
                "database": self.db_path.name,
                "legacy_trades": self.trades_path.name,
                "legacy_dividends": self.dividends_path.name,
                "price_cache": self.price_cache_dir.name,
                "result_cache": self.result_cache_dir.name,
            },
        }
        temp_path = self.metadata_path.with_suffix(self.metadata_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.metadata_path)
