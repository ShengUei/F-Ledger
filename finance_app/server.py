from __future__ import annotations

import argparse
import json
import mimetypes
from dataclasses import dataclass
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analytics import PortfolioAnalytics, portfolio_names
from .cache import JSONResultCache, ResultCache
from .models import DEFAULT_DISPLAY_CURRENCY, Dividend, Trade, parse_date
from .pricing import YahooFinanceProvider
from .storage import SQLiteStore, StorageBackend


DIVIDEND_IMPORT_TEMPLATE = (
    "date,symbol,gross_amount,tax,currency,portfolio,notes\n"
    "2024-02-01,GOOG,10,3,USD,Active,example dividend\n"
    "2024-03-01,2330.TW,20,0,TWD,DCA,example dividend\n"
)

DEFAULT_MARKET_SYMBOLS = ("^TWII", "SPY")


TRADE_IMPORT_TEMPLATE = (
    "date,symbol,side,quantity,price,fees,currency,portfolio,notes\n"
    "2024-01-02,GOOG,BUY,10,100,1,USD,Active,example buy\n"
    "2024-01-03,2330.TW,BUY,5,500,20,TWD,DCA,example buy\n"
)


@dataclass
class AppContext:
    store: StorageBackend
    price_provider: object
    result_cache: ResultCache | None = None
    web_dir: Path | None = None
    today: date | None = None


def handle_api_request(
    context: AppContext,
    method: str,
    path: str,
    query: dict[str, list[str]],
    body: bytes,
) -> tuple[int, dict]:
    try:
        return _handle_api_request(context, method, path, query, body)
    except ValueError as exc:
        return 400, {"error": str(exc)}


def _handle_api_request(
    context: AppContext,
    method: str,
    path: str,
    query: dict[str, list[str]],
    body: bytes,
) -> tuple[int, dict]:
    store = context.store
    analytics = PortfolioAnalytics(context.price_provider, context.result_cache)

    if method == "GET" and path == "/api/records":
        if hasattr(store, "query_records"):
            return 200, _records_payload_sql(store, query)
        return 200, _records_payload(store.list_trades(), store.list_dividends(), query)

    if method == "GET" and path == "/api/portfolios":
        names_fn = getattr(store, "portfolio_names", None)
        if callable(names_fn):
            return 200, {"portfolios": names_fn()}
        trades = store.list_trades()
        dividends = store.list_dividends()
        return 200, {"portfolios": portfolio_names(trades, dividends)}

    if method == "GET" and path == "/api/defaults":
        return 200, _default_dates(context.price_provider, context.today or date.today())

    if method == "GET" and path == "/api/templates/trades":
        return 200, {
            "filename": "trade-import-template.csv",
            "content_type": "text/csv; charset=utf-8",
            "content": TRADE_IMPORT_TEMPLATE,
        }

    if method == "GET" and path == "/api/templates/dividends":
        return 200, {
            "filename": "dividend-import-template.csv",
            "content_type": "text/csv; charset=utf-8",
            "content": DIVIDEND_IMPORT_TEMPLATE,
        }

    if method == "POST" and path == "/api/trades":
        payload = _read_json(body)
        trade = store.add_trade(Trade.from_dict(payload))
        _clear_result_cache(context)
        return 201, {"trade": trade.to_json()}

    if method == "POST" and path == "/api/import/trades":
        payload = _read_json(body)
        raw_records = payload.get("records")
        if not isinstance(raw_records, list) or not raw_records:
            raise ValueError("records must be a non-empty list")
        trades = []
        for index, record in enumerate(raw_records, start=1):
            if not isinstance(record, dict):
                raise ValueError(f"row {index}: record must be an object")
            try:
                trades.append(Trade.from_dict(record))
            except ValueError as exc:
                raise ValueError(f"row {index}: {exc}") from exc
        existing_keys = {_trade_dedup_key(trade) for trade in store.list_trades()}
        saved = []
        skipped = 0
        for trade in trades:
            key = _trade_dedup_key(trade)
            if key in existing_keys:
                skipped += 1
                continue
            saved.append(store.add_trade(trade))
            existing_keys.add(key)
        _clear_result_cache(context)
        return 201, {
            "imported_count": len(saved),
            "skipped_duplicates": skipped,
            "trades": [trade.to_json() for trade in saved],
        }

    if method == "POST" and path == "/api/dividends":
        payload = _read_json(body)
        dividend = store.add_dividend(Dividend.from_dict(payload))
        _clear_result_cache(context)
        return 201, {"dividend": dividend.to_json()}

    if method == "POST" and path == "/api/import/dividends":
        payload = _read_json(body)
        raw_records = payload.get("records")
        if not isinstance(raw_records, list) or not raw_records:
            raise ValueError("records must be a non-empty list")
        dividends = []
        for index, record in enumerate(raw_records, start=1):
            if not isinstance(record, dict):
                raise ValueError(f"row {index}: record must be an object")
            try:
                dividends.append(Dividend.from_dict(record))
            except ValueError as exc:
                raise ValueError(f"row {index}: {exc}") from exc
        existing_keys = {_dividend_dedup_key(dividend) for dividend in store.list_dividends()}
        saved = []
        skipped = 0
        for dividend in dividends:
            key = _dividend_dedup_key(dividend)
            if key in existing_keys:
                skipped += 1
                continue
            saved.append(store.add_dividend(dividend))
            existing_keys.add(key)
        _clear_result_cache(context)
        return 201, {
            "imported_count": len(saved),
            "skipped_duplicates": skipped,
            "dividends": [dividend.to_json() for dividend in saved],
        }

    if method == "PUT" and path.startswith("/api/trades/"):
        record_id = path.rsplit("/", 1)[-1]
        payload = _read_json(body)
        trade = store.update_trade(record_id, Trade.from_dict({**payload, "id": record_id}))
        if trade is None:
            return 404, {"updated": False}
        _clear_result_cache(context)
        return 200, {"updated": True, "trade": trade.to_json()}

    if method == "PUT" and path.startswith("/api/dividends/"):
        record_id = path.rsplit("/", 1)[-1]
        payload = _read_json(body)
        dividend = store.update_dividend(record_id, Dividend.from_dict({**payload, "id": record_id}))
        if dividend is None:
            return 404, {"updated": False}
        _clear_result_cache(context)
        return 200, {"updated": True, "dividend": dividend.to_json()}

    if method == "DELETE" and path.startswith("/api/trades/"):
        record_id = path.rsplit("/", 1)[-1]
        deleted = store.delete_trade(record_id)
        if deleted:
            _clear_result_cache(context)
        return (200 if deleted else 404), {"deleted": deleted}

    if method == "DELETE" and path.startswith("/api/dividends/"):
        record_id = path.rsplit("/", 1)[-1]
        deleted = store.delete_dividend(record_id)
        if deleted:
            _clear_result_cache(context)
        return (200 if deleted else 404), {"deleted": deleted}

    if method == "GET" and path == "/api/summary":
        as_of = parse_date(_query_one(query, "as_of", date.today().isoformat()), "as_of")
        portfolio = _query_optional(query, "portfolio")
        currency = _query_one(query, "currency", DEFAULT_DISPLAY_CURRENCY)
        return 200, analytics.summary(
            store.list_trades(),
            store.list_dividends(),
            as_of,
            portfolio=portfolio,
            display_currency=currency,
        )

    if method == "GET" and path == "/api/period-summary":
        trades = store.list_trades()
        dividends = store.list_dividends()
        default_start, default_end = _default_range(trades, dividends)
        start = parse_date(_query_one(query, "start", default_start.isoformat()), "start")
        end = parse_date(_query_one(query, "end", default_end.isoformat()), "end")
        portfolio = _query_optional(query, "portfolio")
        currency = _query_one(query, "currency", DEFAULT_DISPLAY_CURRENCY)
        return 200, analytics.period_summary(
            trades,
            dividends,
            start,
            end,
            portfolio=portfolio,
            display_currency=currency,
        )

    if method == "GET" and path == "/api/performance":
        trades = store.list_trades()
        dividends = store.list_dividends()
        default_start, default_end = _default_range(trades, dividends)
        start = parse_date(_query_one(query, "start", default_start.isoformat()), "start")
        end = parse_date(_query_one(query, "end", default_end.isoformat()), "end")
        interval = _query_one(query, "interval", "monthly")
        portfolio = _query_optional(query, "portfolio")
        currency = _query_one(query, "currency", DEFAULT_DISPLAY_CURRENCY)
        version_fn = getattr(store, "data_version", None)
        cache_token = f"{version_fn()}:{len(trades)}:{len(dividends)}" if callable(version_fn) else None
        return 200, analytics.performance(
            trades,
            dividends,
            start,
            end,
            interval,
            portfolio=portfolio,
            display_currency=currency,
            cache_token=cache_token,
        )

    if method == "GET" and path == "/api/allocation":
        as_of = parse_date(_query_one(query, "as_of", date.today().isoformat()), "as_of")
        portfolio = _query_optional(query, "portfolio")
        currency = _query_one(query, "currency", DEFAULT_DISPLAY_CURRENCY)
        return 200, analytics.allocation(
            store.list_trades(),
            store.list_dividends(),
            as_of,
            display_currency=currency,
            portfolio=portfolio,
        )

    return 404, {"error": "not found"}


def _default_dates(price_provider: object, today: date) -> dict:
    start = date(today.year, 1, 1)
    search_start = today - timedelta(days=14)
    latest_market_day = None
    for symbol in DEFAULT_MARKET_SYMBOLS:
        try:
            prices = price_provider.get_prices(symbol, search_start, today)
        except Exception:
            prices = {}
        candidates = [item_date for item_date in prices if item_date <= today]
        if candidates:
            candidate = max(candidates)
            latest_market_day = max(latest_market_day, candidate) if latest_market_day else candidate
    if latest_market_day is None:
        latest_market_day = _previous_weekday(today)
    return {
        "today": today.isoformat(),
        "as_of": latest_market_day.isoformat(),
        "start": start.isoformat(),
        "end": today.isoformat(),
    }


def _previous_weekday(day: date) -> date:
    current = day
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _records_payload(trades: list[Trade], dividends: list[Dividend], query: dict[str, list[str]]) -> dict:
    records = [_trade_record(trade) for trade in trades] + [_dividend_record(dividend) for dividend in dividends]
    records.sort(key=lambda item: (item["date"], item["symbol"], item["id"]), reverse=True)
    kind = (_query_one(query, "kind", "all") or "all").lower()
    symbol = (_query_optional(query, "symbol") or "").strip().upper()
    portfolio = _query_optional(query, "portfolio")
    portfolio = None if not portfolio or portfolio == "All" else portfolio
    start_text = _query_optional(query, "start")
    end_text = _query_optional(query, "end")
    start = parse_date(start_text, "start") if start_text else None
    end = parse_date(end_text, "end") if end_text else None

    if kind in {"trade", "dividend"}:
        records = [record for record in records if record["kind"] == kind]
    if symbol:
        records = [record for record in records if symbol in record["symbol"].upper()]
    if portfolio:
        records = [record for record in records if record["portfolio"] == portfolio]
    if start:
        records = [record for record in records if parse_date(record["date"]) >= start]
    if end:
        records = [record for record in records if parse_date(record["date"]) <= end]

    page_size = min(200, max(1, _query_int(query, "page_size", 25)))
    total = len(records)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(total_pages, max(1, _query_int(query, "page", 1)))
    offset = (page - 1) * page_size
    return {
        "records": records[offset : offset + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _records_payload_sql(store: SQLiteStore, query: dict[str, list[str]]) -> dict:
    kind = (_query_one(query, "kind", "all") or "all").lower()
    symbol = (_query_optional(query, "symbol") or "").strip().upper()
    portfolio = _query_optional(query, "portfolio")
    portfolio = None if not portfolio or portfolio == "All" else portfolio
    start_text = _query_optional(query, "start")
    end_text = _query_optional(query, "end")
    start = parse_date(start_text, "start") if start_text else None
    end = parse_date(end_text, "end") if end_text else None
    page_size = min(200, max(1, _query_int(query, "page_size", 25)))

    rows, total, page = store.query_records(
        kind=kind if kind in {"trade", "dividend"} else None,
        symbol_contains=symbol or None,
        portfolio=portfolio,
        start=start.isoformat() if start else None,
        end=end.isoformat() if end else None,
        page=max(1, _query_int(query, "page", 1)),
        page_size=page_size,
    )
    records = [
        _trade_record(Trade.from_dict(row)) if row["kind"] == "trade" else _dividend_record(Dividend.from_dict(row))
        for row in rows
    ]
    return {
        "records": records,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


def _trade_dedup_key(trade: Trade) -> tuple[str, ...]:
    row = trade.to_row()
    return (
        row["date"],
        row["symbol"],
        row["side"],
        row["quantity"],
        row["price"],
        row["fees"],
        row["currency"],
        row["portfolio"],
    )


def _dividend_dedup_key(dividend: Dividend) -> tuple[str, ...]:
    row = dividend.to_row()
    return (
        row["date"],
        row["symbol"],
        row["gross_amount"],
        row["tax"],
        row["currency"],
        row["portfolio"],
    )


def _trade_record(trade: Trade) -> dict:
    amount = trade.quantity * trade.price + trade.fees if trade.side == "BUY" else trade.quantity * trade.price - trade.fees
    return {
        "kind": "trade",
        "id": trade.id,
        "date": trade.date.isoformat(),
        "symbol": trade.symbol,
        "portfolio": trade.portfolio,
        "currency": trade.currency,
        "type": trade.side,
        "side": trade.side,
        "quantity": trade.quantity,
        "price": trade.price,
        "fees": trade.fees,
        "amount": amount,
        "notes": trade.notes,
    }


def _dividend_record(dividend: Dividend) -> dict:
    return {
        "kind": "dividend",
        "id": dividend.id,
        "date": dividend.date.isoformat(),
        "symbol": dividend.symbol,
        "portfolio": dividend.portfolio,
        "currency": dividend.currency,
        "type": "DIVIDEND",
        "gross_amount": dividend.gross_amount,
        "tax": dividend.tax,
        "net_amount": dividend.net_amount,
        "amount": dividend.net_amount,
        "notes": dividend.notes,
    }


def _read_json(body: bytes) -> dict:
    if not body:
        raise ValueError("request body is required")
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def _query_one(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0] or default


def _query_optional(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0] or None


def _query_int(query: dict[str, list[str]], key: str, default: int) -> int:
    value = _query_one(query, key, str(default))
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be an integer") from None


def _clear_result_cache(context: AppContext) -> None:
    context.store.clear_result_cache()
    if context.result_cache is not None:
        context.result_cache.clear()


def _default_range(trades: list[Trade], dividends: list[Dividend]) -> tuple[date, date]:
    today = date.today()
    activity_dates = [trade.date for trade in trades] + [dividend.date for dividend in dividends]
    if not activity_dates:
        return today - timedelta(days=365), today
    return min(activity_dates), today


class PortfolioRequestHandler(BaseHTTPRequestHandler):
    context: AppContext

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def do_PUT(self) -> None:
        self._dispatch()

    def do_DELETE(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length) if length else b""
            status, payload = handle_api_request(
                self.context,
                self.command,
                parsed.path,
                parse_qs(parsed.query),
                body,
            )
            self._send_json(status, payload)
            return
        self._serve_static(parsed.path)

    def _serve_static(self, request_path: str) -> None:
        web_dir = self.context.web_dir or Path(__file__).with_name("web")
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        if relative.startswith("static/"):
            relative = relative.removeprefix("static/")
        target = (web_dir / relative).resolve()
        try:
            target.relative_to(web_dir.resolve())
        except ValueError:
            self._send_json(403, {"error": "forbidden"})
            return
        if not target.exists() or not target.is_file():
            self._send_json(404, {"error": "not found"})
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if relative.startswith("vendor/"):
            self.send_header("Cache-Control", "public, max-age=604800, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def create_server(host: str, port: int, data_dir: str | Path) -> ThreadingHTTPServer:
    store = SQLiteStore(data_dir)
    context = AppContext(
        store=store,
        price_provider=YahooFinanceProvider(store.price_cache_dir),
        result_cache=JSONResultCache(store.result_cache_dir),
    )

    class Handler(PortfolioRequestHandler):
        pass

    Handler.context = context
    return ThreadingHTTPServer((host, port), Handler)


def run_server(host: str = "127.0.0.1", port: int = 8000, data_dir: str | Path = "data") -> None:
    server = create_server(host, port, data_dir)
    print(f"Local Stock Portfolio Tracker running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local stock portfolio tracker.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args(argv)
    run_server(args.host, args.port, args.data_dir)


if __name__ == "__main__":
    main()
