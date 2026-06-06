# Local Stock Portfolio Tracker

A local-only stock portfolio tool built with Python, HTML, and JavaScript.
It stores all user records and price cache files as CSV. Market prices are
loaded from Yahoo Finance through its public chart endpoint.

## Features

- Record stock buy/sell transactions.
- Record dividend income and taxes.
- View current holdings, realized gain, dividends, market value, and total gain.
- Chart portfolio value, total gain, dividends, and yearly performance.
- Query performance for any date range.
- Assign trades and dividends to portfolios such as `Active` or `DCA`.
- Filter performance by one portfolio or view all portfolios together.
- View holding allocation for the full account and for each portfolio.
- Record source currency for US and Taiwan stock trades and dividends.
- Switch report display currency between TWD and USD.
- No database, Redis, ELK, or external service is required.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m finance_app --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

CSV files are created under `data/` by default:

- `data/trades.csv`
- `data/dividends.csv`
- `data/price_cache/*.csv`

Trades and dividends include `portfolio` and `currency` columns. Existing CSV
files without those columns are migrated automatically. Missing portfolios are
assigned to `General`; missing currencies are inferred from the symbol, where
`.TW` and `.TWO` use TWD and other symbols use USD.

Market prices and FX rates are loaded from Yahoo Finance. FX conversion uses
transaction-date rates for trades, payment-date rates for dividends, and
valuation-date rates for current market value.

## Tests

```powershell
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests
```

## Design Notes

- The backend uses only the Python standard library.
- The frontend uses vanilla HTML, CSS, and JavaScript.
- CSV schemas are documented in `docs/spec.md`.
- Core portfolio math is isolated from HTTP and storage code, so new features
  can be added without rewriting the UI or data layer.
- Python commands should run from `.venv`.
- Source files should be managed in git; runtime CSV data and `.venv` are ignored.
