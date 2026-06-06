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
from .models import Dividend, Trade, parse_date
from .pricing import YahooFinanceProvider
from .storage import CSVStore


@dataclass
class AppContext:
    store: CSVStore
    price_provider: object
    web_dir: Path | None = None


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
    analytics = PortfolioAnalytics(context.price_provider)

    if method == "GET" and path == "/api/records":
        return 200, {
            "trades": [trade.to_json() for trade in store.list_trades()],
            "dividends": [dividend.to_json() for dividend in store.list_dividends()],
        }

    if method == "GET" and path == "/api/portfolios":
        trades = store.list_trades()
        dividends = store.list_dividends()
        return 200, {"portfolios": portfolio_names(trades, dividends)}

    if method == "POST" and path == "/api/trades":
        payload = _read_json(body)
        trade = store.add_trade(Trade.from_dict(payload))
        return 201, {"trade": trade.to_json()}

    if method == "POST" and path == "/api/dividends":
        payload = _read_json(body)
        dividend = store.add_dividend(Dividend.from_dict(payload))
        return 201, {"dividend": dividend.to_json()}

    if method == "DELETE" and path.startswith("/api/trades/"):
        record_id = path.rsplit("/", 1)[-1]
        deleted = store.delete_trade(record_id)
        return (200 if deleted else 404), {"deleted": deleted}

    if method == "DELETE" and path.startswith("/api/dividends/"):
        record_id = path.rsplit("/", 1)[-1]
        deleted = store.delete_dividend(record_id)
        return (200 if deleted else 404), {"deleted": deleted}

    if method == "GET" and path == "/api/summary":
        as_of = parse_date(_query_one(query, "as_of", date.today().isoformat()), "as_of")
        portfolio = _query_optional(query, "portfolio")
        return 200, analytics.summary(store.list_trades(), store.list_dividends(), as_of, portfolio=portfolio)

    if method == "GET" and path == "/api/performance":
        trades = store.list_trades()
        dividends = store.list_dividends()
        default_start, default_end = _default_range(trades, dividends)
        start = parse_date(_query_one(query, "start", default_start.isoformat()), "start")
        end = parse_date(_query_one(query, "end", default_end.isoformat()), "end")
        interval = _query_one(query, "interval", "monthly")
        portfolio = _query_optional(query, "portfolio")
        return 200, analytics.performance(trades, dividends, start, end, interval, portfolio=portfolio)

    if method == "GET" and path == "/api/allocation":
        as_of = parse_date(_query_one(query, "as_of", date.today().isoformat()), "as_of")
        return 200, analytics.allocation(store.list_trades(), store.list_dividends(), as_of)

    return 404, {"error": "not found"}


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
    store = CSVStore(data_dir)
    context = AppContext(store=store, price_provider=YahooFinanceProvider(store.price_cache_dir))

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
