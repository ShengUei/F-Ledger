# Stock Portfolio Tracker SDD

## Goal

Build a local WebUI tool that lets a user enter stock trades and dividends,
then inspect portfolio performance for the current date, each year, or any
selected date range.

## Constraints

- Python backend plus HTML and JavaScript frontend.
- Yahoo Finance is the market data source.
- No Redis, database, ELK, or external service.
- User records and cached market data are managed as CSV files.
- The application is started locally and used through a browser.
- The design should keep room for future features.
- Development follows SDD and TDD: this file defines behavior; tests protect
  storage, calculation, and API behavior.

## CSV Files

Current storage schema version is tracked in `data/metadata.json`.

```json
{
  "schema_version": 3,
  "storage_backend": "csv"
}
```

The application migrates older CSV files at startup. Existing rows without
`portfolio` receive `General`; existing rows without `currency` are inferred
from the symbol.

### `trades.csv`

| column | type | notes |
| --- | --- | --- |
| id | string | generated UUID |
| date | YYYY-MM-DD | transaction date |
| symbol | string | stock ticker, normalized uppercase |
| side | BUY or SELL | transaction direction |
| quantity | decimal | positive share quantity |
| price | decimal | unit price |
| fees | decimal | transaction fee, default 0 |
| currency | string | source currency, default inferred from symbol |
| portfolio | string | investment portfolio name, default `General` |
| notes | string | optional |

### `dividends.csv`

| column | type | notes |
| --- | --- | --- |
| id | string | generated UUID |
| date | YYYY-MM-DD | payment date |
| symbol | string | stock ticker, normalized uppercase |
| gross_amount | decimal | total dividend amount before tax |
| tax | decimal | withholding or other tax, default 0 |
| currency | string | source currency, default inferred from symbol |
| portfolio | string | investment portfolio name, default `General` |
| notes | string | optional |

### Price Cache

Files live in `price_cache/{symbol}/{year}.csv`, for example
`price_cache/GOOG/2024.csv`. Legacy flat files such as `price_cache/GOOG.csv`
are migrated into year files when read.

| column | type | notes |
| --- | --- | --- |
| date | YYYY-MM-DD | market date |
| close | decimal | adjusted close from Yahoo Finance when available |

### Result Cache

Performance results live in `result_cache/{sha256}.json`. The cache key includes
query parameters plus all trade and dividend records, so changing user records
creates a different key. Record mutations also clear cached result files.

## Storage Boundary

`StorageBackend` defines the storage contract used by the HTTP layer:

- list, add, and delete trades.
- list, add, and delete dividends.
- expose price and result cache directories.
- clear result cache after data mutations.

`CSVStore` is the current implementation. Future storage formats can implement
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
| GET | `/api/records` | returns all trades and dividends |
| POST | `/api/trades` | creates a trade |
| GET | `/api/templates/trades` | returns a CSV template for trade batch import |
| POST | `/api/import/trades` | imports multiple trade records from parsed CSV rows |
| DELETE | `/api/trades/{id}` | deletes a trade |
| POST | `/api/dividends` | creates a dividend |
| DELETE | `/api/dividends/{id}` | deletes a dividend |
| GET | `/api/portfolios` | returns available portfolio names |
| GET | `/api/summary?as_of=YYYY-MM-DD&portfolio=Active&currency=TWD` | returns all-portfolio or selected-portfolio summary in a display currency |
| GET | `/api/performance?start=YYYY-MM-DD&end=YYYY-MM-DD&interval=monthly&portfolio=Active&currency=TWD` | returns filtered performance series and annual bars |
| GET | `/api/allocation?as_of=YYYY-MM-DD&currency=TWD` | returns overall and per-portfolio holding weights |

## Acceptance Scenarios

1. A user can add a BUY trade and see it in the records table.
2. A user can add a SELL trade and realized gain is computed with average cost.
3. A user can add a dividend and net dividend appears in summary and charts.
4. A user can select a date range and interval to inspect performance.
5. A user can inspect yearly performance bars for multi-year records.
6. The app can run locally with `python -m finance_app`.
7. A user can assign records to portfolios such as `Active` or `DCA`.
8. A user can view all-stock performance or performance for one portfolio.
9. A user can view holding allocation for the full account and for each portfolio.
10. A user can record source currency for US and Taiwan stock transactions.
11. A user can switch the report display currency between TWD and USD.
12. Holdings, allocation, performance charts, and annual charts update when the display currency changes.
13. A user can choose chart X-axis label format and Y-axis value mode.
14. A user can hover a chart to inspect the nearest point or annual bar values.
15. A user can select an existing portfolio from a dropdown or create a new portfolio while adding a record.
16. A user can download a trade CSV import template.
17. A user can upload a trade CSV file and import multiple trade records at once.
