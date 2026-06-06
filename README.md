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
- View holding allocation as an interactive pie chart for all holdings or one selected portfolio.
- Record source currency for US and Taiwan stock trades and dividends.
- Switch report display currency between TWD and USD.
- Download a trade import template and upload CSV files to add many trades at once.
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
- `data/metadata.json`
- `data/price_cache/{symbol}/{year}.csv`
- `data/result_cache/{sha256}.json`

Trades and dividends include `portfolio` and `currency` columns. Existing CSV
files without those columns are migrated automatically. Missing portfolios are
assigned to `General`; missing currencies are inferred from the symbol, where
`.TW` and `.TWO` use TWD and other symbols use USD.

Market prices and FX rates are loaded from Yahoo Finance. FX conversion uses
transaction-date rates for trades, payment-date rates for dividends, and
valuation-date rates for current market value.

`data/metadata.json` stores the current CSV schema version. The app migrates
older CSV headers automatically at startup. `CSVStore` implements the
`StorageBackend` protocol, so a future storage format can replace CSV without
rewriting analytics or the WebUI.

## Trade Import

Use the WebUI batch import panel to download `trade-import-template.csv`.
The uploaded CSV should use these columns:

```csv
date,symbol,side,quantity,price,fees,currency,portfolio,notes
2024-01-02,GOOG,BUY,10,100,1,USD,美股,example buy
2024-01-03,2330.TW,BUY,5,500,20,TWD,臺股,example buy
```

Required columns are `date`, `symbol`, `side`, `quantity`, and `price`.
Missing `fees` defaults to `0`; missing `currency` and `portfolio` are inferred
by the app.

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
