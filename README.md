# Local Stock Portfolio Tracker

A local-only stock portfolio tool built with Python, HTML, and JavaScript.
User trades and dividends are stored in SQLite. Market prices and FX rates are
loaded from Yahoo Finance through its public chart endpoint, with local file
caches under `data/`.

## Features

- Record stock buy/sell transactions.
- Record dividend income and taxes.
- Edit or delete existing trade and dividend records from a separate records page.
- View date-range market value, total gain, realized gain, sell gain, and dividends.
- Chart portfolio value, total gain, dividends, yearly performance, and allocation with Chart.js.
- Query performance for any date range.
- Assign trades and dividends to portfolios such as `Active` or `DCA`.
- Filter performance by one portfolio or view all portfolios together.
- View holding allocation as an interactive pie chart for all holdings or one selected portfolio.
- Record source currency for US and Taiwan stock trades and dividends.
- Switch report display currency between TWD and USD.
- Default dates use the current year start, today as range end, and the latest available trading day as the settlement date.
- Download trade and dividend import templates and upload CSV files to add many records at once.
- Show row-level duplicate details when batch imports skip existing records.
- Filter and paginate records on the records management page.
- No Redis, ELK, external database server, or external service is required.

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

Runtime files are created under `data/` by default:

- `data/portfolio.sqlite3`
- `data/metadata.json`
- `data/logs/app.log`
- `data/price_cache/{symbol}/{year}.csv`
- `data/result_cache/{sha256}.json`

Existing `data/trades.csv` and `data/dividends.csv` files are imported into
SQLite automatically when `portfolio.sqlite3` is empty. Missing portfolios are
assigned to `General`; missing currencies are inferred from the symbol, where
`.TW` and `.TWO` use TWD and other symbols use USD.

Market prices and FX rates are loaded from Yahoo Finance. FX conversion uses
transaction-date rates for trades, payment-date rates for dividends, and
valuation-date rates for current market value.

`data/metadata.json` stores the current storage schema version. `SQLiteStore`
implements the `StorageBackend` protocol, so future storage changes can stay
behind the same storage boundary without rewriting analytics or the WebUI.

Backend logs are written to `data/logs/app.log`. The log includes server start,
API responses, API validation errors, and batch-import duplicate rows.

## Trade Import

Use the WebUI batch import panel to download `trade-import-template.csv`.
The uploaded CSV should use these columns:

```csv
date,symbol,side,quantity,price,fees,currency,portfolio,notes
2024-01-02,GOOG,BUY,10,100,1,USD,Active,example buy
2024-01-03,2330.TW,BUY,5,500,20,TWD,DCA,example buy
```

Required columns are `date`, `symbol`, `side`, `quantity`, and `price`.
Missing `fees` defaults to `0`; missing `currency` and `portfolio` are inferred
by the app.

## Dividend Import

Use the WebUI batch import panel to download `dividend-import-template.csv`.
The uploaded CSV should use these columns:

```csv
date,symbol,gross_amount,tax,currency,portfolio,notes
2024-02-01,GOOG,10,3,USD,Active,example dividend
2024-03-01,2330.TW,20,0,TWD,DCA,example dividend
```

Required columns are `date`, `symbol`, and `gross_amount`. Missing `tax`
defaults to `0`; missing `currency` and `portfolio` are inferred by the app.

## Tests

```powershell
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests
```

## Design Notes

- The backend uses only the Python standard library, including `sqlite3`.
- The frontend uses vanilla HTML, CSS, JavaScript, and a vendored Chart.js browser build.
- SQLite and import CSV schemas are documented in `docs/spec.md`.
- Core portfolio math is isolated from HTTP and storage code, so new features
  can be added without rewriting the UI or data layer.
- Python commands should run from `.venv`.
- Source files should be managed in git; runtime SQLite/cache data and `.venv` are ignored.
