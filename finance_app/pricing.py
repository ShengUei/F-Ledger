from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path


PRICE_FIELDS = ["date", "close"]


class YahooFinanceProvider:
    def __init__(self, cache_dir: str | Path = "data/price_cache", timeout: int = 10) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def get_prices(self, symbol: str, start: date, end: date) -> dict[date, float]:
        if end < start:
            return {}
        cached = self._read_cache(symbol)
        needs_fetch = self._needs_fetch(cached, start, end)
        if needs_fetch:
            try:
                fetched = self._fetch_from_yahoo(symbol, start, end)
            except Exception:
                fetched = {}
            if fetched:
                cached.update(fetched)
                self._write_cache(symbol, cached)
        return {item_date: close for item_date, close in cached.items() if start <= item_date <= end}

    def get_fx_rate(self, from_currency: str, to_currency: str, as_of: date) -> float:
        source = from_currency.upper()
        target = to_currency.upper()
        if source == target:
            return 1.0
        direct = self._latest_pair_rate(f"{source}{target}=X", as_of)
        if direct is not None:
            return direct
        reverse = self._latest_pair_rate(f"{target}{source}=X", as_of)
        if reverse is not None and reverse != 0:
            return 1 / reverse
        raise ValueError(f"No FX rate available for {source}/{target} on {as_of.isoformat()}")

    def _latest_pair_rate(self, pair_symbol: str, as_of: date) -> float | None:
        start = as_of - timedelta(days=10)
        prices = self.get_prices(pair_symbol, start, as_of)
        candidates = [item_date for item_date in prices if item_date <= as_of]
        if not candidates:
            return None
        return prices[max(candidates)]

    @staticmethod
    def _needs_fetch(cached: dict[date, float], start: date, end: date) -> bool:
        if not cached:
            return True
        range_dates = [item_date for item_date in cached if start <= item_date <= end]
        if not range_dates:
            return True
        latest_cached = max(range_dates)
        return latest_cached < min(end, date.today()) - timedelta(days=3)

    def _fetch_from_yahoo(self, symbol: str, start: date, end: date) -> dict[date, float]:
        period1 = int(datetime.combine(start, time.min, tzinfo=timezone.utc).timestamp())
        period2 = int(datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc).timestamp())
        encoded_symbol = urllib.parse.quote(symbol)
        query = urllib.parse.urlencode(
            {
                "period1": period1,
                "period2": period2,
                "interval": "1d",
                "events": "history",
                "includeAdjustedClose": "true",
            }
        )
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?{query}"
        request = urllib.request.Request(url, headers={"User-Agent": "local-portfolio-tracker/0.1"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload.get("chart", {}).get("result", [])
        if not result:
            return {}
        series = result[0]
        timestamps = series.get("timestamp") or []
        quote = (series.get("indicators", {}).get("quote") or [{}])[0]
        adjclose = (series.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
        closes = adjclose or quote.get("close") or []
        prices: dict[date, float] = {}
        for timestamp, close in zip(timestamps, closes):
            if close is None:
                continue
            item_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
            prices[item_date] = float(close)
        return prices

    def _cache_path(self, symbol: str) -> Path:
        safe = re.sub(r"[^A-Z0-9._-]+", "_", symbol.upper())
        return self.cache_dir / f"{safe}.csv"

    def _read_cache(self, symbol: str) -> dict[date, float]:
        path = self._cache_path(symbol)
        if not path.exists():
            return {}
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            prices = {}
            for row in reader:
                try:
                    prices[datetime.strptime(row["date"], "%Y-%m-%d").date()] = float(row["close"])
                except (KeyError, TypeError, ValueError):
                    continue
            return prices

    def _write_cache(self, symbol: str, prices: dict[date, float]) -> None:
        path = self._cache_path(symbol)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=PRICE_FIELDS)
            writer.writeheader()
            for item_date in sorted(prices):
                writer.writerow({"date": item_date.isoformat(), "close": f"{prices[item_date]:.10g}"})
        temp_path.replace(path)
