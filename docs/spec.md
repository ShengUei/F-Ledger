# Stock Portfolio Tracker SDD

## Goal

Build a local WebUI tool that lets a user enter stock trades and dividends,
then inspect portfolio performance for the current date, each year, or any
selected date range.

## Constraints

- Python backend plus HTML and JavaScript frontend.
- Yahoo Finance is the market data source.
- No Redis, ELK, external database server, or external service.
- User records are stored in SQLite through Python's standard `sqlite3` module.
- Batch import/export templates use CSV files.
- The application is started locally and used through a browser.
- Charts use the vendored browser build of Chart.js 4.5.0, an MIT-licensed
  open-source JavaScript charting library.
- The design should keep room for future features.
- Development follows SDD and TDD: this file defines behavior; tests protect
  storage, calculation, API, and UI-facing data behavior.

## SQLite Storage

Current storage schema version is tracked in `data/metadata.json` and in the
SQLite `PRAGMA user_version`.

```json
{
  "schema_version": 4,
  "storage_backend": "sqlite"
}
```

The main database file is `data/portfolio.sqlite3`.

Existing `data/trades.csv` and `data/dividends.csv` files are imported into
SQLite automatically when the SQLite tables are empty. Existing CSV rows without
`portfolio` receive `General`; existing rows without `currency` are inferred
from the symbol.

### `trades`

| column | type | notes |
| --- | --- | --- |
| id | text primary key | generated UUID |
| date | YYYY-MM-DD text | transaction date |
| symbol | text | stock ticker, normalized uppercase |
| side | BUY or SELL | transaction direction |
| quantity | real | positive share quantity |
| price | real | unit price |
| fees | real | transaction fee, default 0 |
| currency | text | source currency, default inferred from symbol |
| portfolio | text | investment portfolio name, default `General` |
| notes | text | optional |

### `dividends`

| column | type | notes |
| --- | --- | --- |
| id | text primary key | generated UUID |
| date | YYYY-MM-DD text | payment date |
| symbol | text | stock ticker, normalized uppercase |
| gross_amount | real | total dividend amount before tax |
| tax | real | withholding or other tax, default 0 |
| currency | text | source currency, default inferred from symbol |
| portfolio | text | investment portfolio name, default `General` |
| notes | text | optional |

## Import CSV Templates

Trade imports use:

```csv
date,symbol,side,quantity,price,fees,currency,portfolio,notes
```

Dividend imports use:

```csv
date,symbol,gross_amount,tax,currency,portfolio,notes
```

The import format is not the storage format; it is a user-facing batch entry
format parsed by the WebUI and submitted to the API.

## Price Cache

Files live in `price_cache/{symbol}/{year}.csv`, for example
`price_cache/GOOG/2024.csv`. Legacy flat files such as `price_cache/GOOG.csv`
are migrated into year files when read.

| column | type | notes |
| --- | --- | --- |
| date | YYYY-MM-DD | market date |
| close | decimal | adjusted close from Yahoo Finance when available |

## Result Cache

Performance results live in `result_cache/{sha256}.json`. The cache key includes
query parameters plus all trade and dividend records, so changing user records
creates a different key. Record mutations also clear cached result files.

## Storage Boundary

`StorageBackend` defines the storage contract used by the HTTP layer:

- list, add, update, and delete trades.
- list, add, update, and delete dividends.
- expose price and result cache directories.
- clear result cache after data mutations.

`SQLiteStore` is the current implementation. Storage formats can change behind
the same protocol without changing analytics or WebUI code.

## Portfolio Math

Trades are processed chronologically by symbol using average cost.

- BUY:
  - shares increase by quantity.
  - cost basis increases by `quantity * price + fees`.
  - cash flow decreases by the same amount.
- SELL:
  - shares decrease by quantity.
  - realized gain increases by `net proceeds - average_cost * quantity`.
  - cost basis decreases by `average_cost * quantity`.
  - cash flow increases by `quantity * price - fees`.
- DIVIDEND:
  - dividend total increases by `gross_amount - tax`.
  - cash flow increases by the same amount.

At a valuation date:

- market value is open shares times the latest known close on or before the date.
- total gain is `market_value + cumulative_cash_flow`.
- return percent is `total_gain / total_buy_cost`.

If Yahoo price data is unavailable, the engine uses the latest transaction price
before the valuation date as a fallback and returns a warning.

For a selected date range, period summary uses only records in the selected
range. Market value, positions, total gain, realized gain, sell gain, dividends,
and cash flow are shown for the selected period.

When a report display currency is selected:

- BUY and SELL cash flows use the transaction-date FX rate.
- DIVIDEND cash flows use the payment-date FX rate.
- Market value uses the valuation-date FX rate.
- FX rates are loaded from Yahoo Finance currency pairs such as `USDTWD=X`.
- Existing CSV rows without `currency` are migrated with inferred defaults:
  `.TW` and `.TWO` symbols use TWD; other symbols use USD.

## API

| method | path | behavior |
| --- | --- | --- |
| GET | `/api/defaults` | returns default as-of, start, and end dates; as-of uses the latest Yahoo market day when possible |
| GET | `/api/records?kind=trade&page=1&page_size=25&portfolio=Active&symbol=GOOG` | returns filtered and paginated records with edit fields |
| POST | `/api/trades` | creates a trade |
| PUT | `/api/trades/{id}` | updates a trade |
| GET | `/api/templates/trades` | returns a CSV template for trade batch import |
| POST | `/api/import/trades` | imports multiple trade records from parsed CSV rows |
| DELETE | `/api/trades/{id}` | deletes a trade |
| POST | `/api/dividends` | creates a dividend |
| PUT | `/api/dividends/{id}` | updates a dividend |
| GET | `/api/templates/dividends` | returns a CSV template for dividend batch import |
| POST | `/api/import/dividends` | imports multiple dividend records from parsed CSV rows |
| DELETE | `/api/dividends/{id}` | deletes a dividend |
| GET | `/api/portfolios` | returns available portfolio names |
| GET | `/api/summary?as_of=YYYY-MM-DD&portfolio=Active&currency=TWD` | returns all-portfolio or selected-portfolio summary in a display currency |
| GET | `/api/period-summary?start=YYYY-MM-DD&end=YYYY-MM-DD&portfolio=Active&currency=TWD` | returns date-range metrics and ending positions |
| GET | `/api/performance?start=YYYY-MM-DD&end=YYYY-MM-DD&interval=monthly&portfolio=Active&currency=TWD` | returns filtered performance series and annual bars |
| GET | `/api/allocation?as_of=YYYY-MM-DD&portfolio=Active&currency=TWD` | returns selected, overall, and per-portfolio holding weights |

## WebUI

- The dashboard view shows filters, metrics, charts, holdings, allocation, and record entry/import forms.
- The records management view is separate from the dashboard.
- The records management view supports type, portfolio, symbol, date range, and page-size filters.
- The records management view supports pagination.
- Each visible record can be edited or deleted.
- Editing a trade supports date, symbol, portfolio, currency, side, quantity, price, fees, and notes.
- Editing a dividend supports date, symbol, portfolio, currency, gross amount, tax, and notes.

## Acceptance Scenarios

1. A user can add a BUY trade and see it in the records management page.
2. A user can edit an incorrect trade and see analytics update from the corrected data.
3. A user can add a SELL trade and realized gain is computed with average cost.
4. A user can add and edit a dividend and net dividend appears in summary and charts.
5. A user can select a date range and interval to inspect performance.
6. A user can inspect yearly performance bars for multi-year records.
7. The app can run locally with `python -m finance_app`.
8. A user can assign records to portfolios such as `Active` or `DCA`.
9. A user can view all-stock performance or performance for one portfolio.
10. A user can view holding allocation for the full account or selected portfolio as an interactive pie chart.
11. A user can record source currency for US and Taiwan stock transactions.
12. A user can switch the report display currency between TWD and USD.
13. Holdings, allocation, performance charts, and annual charts update when the display currency changes.
14. A user can choose chart X-axis label format and Y-axis value mode.
15. A user can hover a chart to inspect the nearest point or annual bar values.
16. A user can select an existing portfolio from a dropdown or create a new portfolio while adding or editing a record.
17. A user can download a trade CSV import template.
18. A user can upload a trade CSV file and import multiple trade records at once.
19. A user can download a dividend CSV import template and import multiple dividend records at once.
20. Records are managed in a separate page with filtering and pagination.
21. The default start date is January 1 of the current year, end date is today, and as-of date is the latest available trading day when today is not a trading day.
22. Top-level metrics update from the selected date range instead of always showing all-time values.
23. Existing CSV records are imported into SQLite automatically when the SQLite database is empty.
