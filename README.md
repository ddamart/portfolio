# Portfolio Manager

Personal investment portfolio tracker for stocks, ETFs, Spanish mutual funds (Fondos), and manual cash accounts — across multiple brokers and currencies. All metrics are computed dynamically at query time from raw transactions; no stored snapshots.

---

## What it does

- **Full transaction log** — record every buy and sell across Openbank, Trade Republic, Revolut, and Degiro, in any currency
- **Live portfolio overview** — current value, cost basis, unrealized P&L, daily change, and allocation % per asset
- **Period-scoped performance** — select any window (1D / 1W / 1M / 6M / YTD / 1Y / 5Y / custom drag range) and see returns calculated via Modified Dietz, correctly accounting for capital flows during the period
- **Realized P&L** — AVCO (Average Cost) method tracks gain/loss on every sell, both gross and net of all commissions
- **Portfolio evolution chart** — historical value curve with invested-capital overlay; drag on the chart to filter a custom date range
- **Broker & asset-type filters** — slice the entire view (summary card, chart, and holdings table) by broker or asset class
- **Automatic price refresh** — yfinance for stocks/ETFs, investpy + mstarpy (Morningstar) fallback for Spanish funds; staleness-aware per market timezone
- **GBX (pence sterling) support** — London-listed assets priced in pence are automatically normalized (÷100 → GBP rate)
- **Manual cash accounts (balance assets)** — track accounts where you only know deposits, withdrawals, and periodic valuations; no shares or price feeds needed
- **LLM-powered batch import** — paste raw broker data in any format → AI extracts transactions → editable preview → confirm

---

## Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Backend | FastAPI (Python 3.11+) | REST JSON API; async background tasks |
| Database | DuckDB (embedded) | OLAP-optimized; window functions + ASOF JOIN; no server needed |
| Frontend | React 19 + Vite + Tailwind CSS 4 | SPA, dark mode, responsive |
| Charts | Recharts | Portfolio value line chart with drag-to-zoom |
| Tables | TanStack Table v8 | Headless sorting + filtering |
| Price data | yfinance · investpy · mstarpy | Per-asset-type with fallback chain |
| LLM import | Google Gemini (default) · Anthropic Claude | Provider-agnostic abstraction |

---

## Architecture decisions

**DuckDB instead of PostgreSQL/SQLite**
All portfolio metrics are a single complex CTE query (holdings → latest prices → period start values → P&L). DuckDB's columnar engine and native `ASOF JOIN` make this trivially fast even over years of data. No server to manage; the `.duckdb` file is the entire database.

**Dynamic computation, no snapshots**
Editing or deleting a transaction immediately produces correct metrics on the next page load. There is no background job keeping a "portfolio snapshot" table in sync. The trade-off is a slightly heavier query on each request, which DuckDB handles without issue at personal-portfolio scale.

**`price_eur` stored at two points in time**
- In `transactions`: the EUR rate locked in at trade time (cost basis accuracy — never recomputed)
- In `prices`: the EUR rate for each price date (current valuation)

This avoids recomputing historical FX on every query and ensures cost basis never drifts when FX rates update.

**Modified Dietz for period returns**
Simple return `(V_fin − V_ini) / V_ini` is misleading when you inject or withdraw capital mid-period. Modified Dietz weights each cash flow by how much of the period remained when it occurred:

```
R = (V_fin − V_ini − ΣCF) / (V_ini + Σ(CF_i × W_i))
```

This is what the summary card "Rendimiento" and the per-asset "G/P %" columns show when a period filter is active.

**AVCO (Average Cost) for realized P&L**
Each sell is matched against the running weighted average cost of that asset. Buy commissions are folded into the AVCO cost basis; sell commissions are deducted from proceeds. This avoids FIFO lot-tracking complexity while producing a sound P&L figure.

**Morningstar secId pre-resolution for funds**
mstarpy's fuzzy search by fund name frequently returns the wrong share class (e.g. SEK class instead of USD class for the same ISIN). We pre-resolve the exact Morningstar performance ID via `SecuritySearch.ashx?q={isin}` before calling mstarpy, then validate the returned fund's ISIN matches what was requested.

**Balance asset type**
Some accounts (Openbank Fondos basket, savings products) don't expose individual holdings — only a total value. A `balance` asset type tracks deposits/withdrawals and periodic snapshots. Portfolio value = latest snapshot; P&L = latest snapshot − net contributions. These integrate into the main holdings table, chart, and summary card.

---

## Setup

### Prerequisites

- **Python 3.11 or 3.12** from [python.org](https://www.python.org/downloads/) (not the Windows Store version)
- **Node.js 18+**

### 1. Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\pip install -r requirements.txt
cp .env.example .env          # edit with your API keys

# macOS / Linux
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

### 2. Frontend

```bash
cd frontend
npm install
```

### 3. Run

**Windows** — two separate PowerShell terminals:
```powershell
.\start.ps1
```

**macOS / Linux** — both processes in one terminal:
```bash
chmod +x start.sh && ./start.sh
```

**Manually:**
```bash
# Terminal 1 — backend (port 3001)
cd backend
.venv\Scripts\uvicorn app.main:app --reload --port 3001   # Windows
.venv/bin/uvicorn app.main:app --reload --port 3001        # macOS/Linux

# Terminal 2 — frontend (port 5173)
cd frontend && npm run dev
```

| URL | Description |
|-----|-------------|
| http://localhost:5173 | Web app |
| http://localhost:3001/docs | Swagger UI (interactive API docs) |

---

## Environment variables

All go in `backend/.env` (copy from `.env.example`).

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `data/portfolio.duckdb` | Path to DuckDB file |
| `DEBUG` | `false` | FastAPI debug mode |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `PRICE_REFRESH_TTL_OPEN` | `15` | Minutes before prices are stale while market is open |
| `PRICE_REFRESH_TTL_CLOSED` | `1440` | Minutes before stale after close (24 h) |
| `LLM_PROVIDER` | `gemini` | `gemini` or `anthropic` |
| `GEMINI_API_KEY` | _(empty)_ | Required when `LLM_PROVIDER=gemini` |
| `ANTHROPIC_API_KEY` | _(empty)_ | Required when `LLM_PROVIDER=anthropic` |
| `LLM_MODEL` | _(empty)_ | Override default model per provider |

---

## Project structure

```
portfolio/
├── start.ps1 / start.sh               # Launchers
│
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app, CORS, router registration, lifespan
│   │   ├── config.py                  # Pydantic settings (reads .env)
│   │   ├── database.py                # DuckDB singleton, schema init, market seeding, migrations
│   │   ├── models/
│   │   │   ├── asset.py               # Asset, AssetCreate, AssetOut, AssetUpdate
│   │   │   ├── transaction.py         # TransactionCreate, TransactionOut, …
│   │   │   ├── portfolio.py           # PortfolioSummary, HoldingRow, ChartPoint
│   │   │   └── balance.py             # BalanceEntryCreate, BalanceEntryOut
│   │   ├── routers/
│   │   │   ├── assets.py              # /api/assets — CRUD, search, lookup, price import
│   │   │   ├── transactions.py        # /api/transactions — CRUD with filters
│   │   │   ├── portfolio.py           # /api/portfolio — summary, holdings, chart
│   │   │   ├── prices.py              # /api/prices — status, refresh (all + single)
│   │   │   ├── balance.py             # /api/balance — balance asset entries CRUD
│   │   │   └── import_router.py       # /api/import — LLM parse + confirm
│   │   └── services/
│   │       ├── portfolio_calc.py      # All DuckDB CTE queries; Modified Dietz; AVCO realized P&L
│   │       ├── price_fetcher.py       # yfinance + investpy + mstarpy; backfill; FX; GBX
│   │       ├── price_status.py        # Per-asset staleness (market timezone + trading hours)
│   │       ├── currency.py            # EUR conversion helpers; GBX = GBP/100
│   │       └── llm_parser.py          # Gemini/Anthropic abstraction + extraction prompt
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_assets.py
│   │   ├── test_transactions.py
│   │   ├── test_portfolio.py
│   │   └── test_price_fetcher.py
│   ├── data/                          # DuckDB file lives here (gitignored)
│   ├── .env.example
│   └── requirements.txt
│
└── frontend/
    └── src/
        ├── api/client.ts              # Axios instance + all TS types + API wrappers
        ├── contexts/
        │   └── RefreshContext.tsx     # Global price-refresh state broadcast to all components
        ├── pages/
        │   ├── Portfolio.tsx          # Summary card + chart + holdings table + filter pills
        │   ├── Transactions.tsx       # Transaction list (fills viewport, body scrolls)
        │   ├── Assets.tsx             # Asset catalog: create, edit, price management
        │   └── Import.tsx             # LLM batch import: paste → preview → confirm
        ├── components/
        │   ├── Navbar.tsx             # Navigation + global price refresh + status indicator
        │   ├── PortfolioSummaryCard.tsx  # Top metrics: value, invested, P&L, period return
        │   ├── PortfolioChart.tsx        # Recharts line chart; period filter; drag-to-zoom
        │   ├── PortfolioTable.tsx        # Holdings breakdown; balance assets section
        │   ├── BalanceDrawer.tsx         # Slide-over for balance asset entries
        │   ├── AssetDetailDrawer.tsx     # Slide-over with asset price history chart
        │   ├── PeriodFilter.tsx          # 1D/1W/1M/6M/YTD/1Y/5Y/All + date pickers
        │   ├── TransactionForm.tsx       # Add/edit transaction modal
        │   ├── TransactionTable.tsx      # Sortable transaction list with inline edit/delete
        │   ├── ManualPriceModal.tsx      # NAV entry for manual-price assets
        │   └── PriceImportModal.tsx      # Bulk CSV price import for an asset
        └── utils/format.ts              # EUR/CCY formatters, number helpers, P&L colours
```

---

## Database schema

```sql
markets (id, mic, name, timezone, open_time, close_time, country)
-- Pre-seeded: XETR XAMS XMAD XLON XNYS XNAS CNMV

assets (id, name, ticker, type, currency, market_id, image_url, manual_price, isin, created_at)
-- type: 'etf' | 'stock' | 'fund' | 'balance'
-- manual_price=true → no automatic price fetch

transactions (id, asset_id, type, broker, shares, price, price_eur, currency,
              commission, commission_eur, commission_currency, date, notes,
              created_at, updated_at)
-- type: 'buy' | 'sell'
-- broker: 'openbank' | 'trade_republic' | 'revolut' | 'degiro'
-- price_eur: EUR rate locked in at trade time (never recomputed)

prices (asset_id, date, price, currency, price_eur)
-- PRIMARY KEY (asset_id, date) — upsert on every refresh
-- price_eur here uses the FX rate for that date (valuation, not cost basis)

fx_rates (date, from_ccy, to_ccy, rate)
-- PRIMARY KEY (date, from_ccy, to_ccy)

balance_entries (id, asset_id, date, type, amount_eur, notes, created_at)
-- type: 'deposit' | 'withdrawal' | 'snapshot'
-- snapshot = total portfolio value at that date

refresh_log (id, started_at, finished_at, assets_updated, status)
```

---

## API reference

### Assets — `/api/assets`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/assets` | List all assets |
| `GET` | `/api/assets/search?q=` | Ticker / name autocomplete |
| `GET` | `/api/assets/lookup?q=` | ISIN / ticker lookup with metadata |
| `POST` | `/api/assets` | Create — auto-fetches metadata + historical prices |
| `PUT` | `/api/assets/{id}` | Update fields |
| `DELETE` | `/api/assets/{id}` | Delete asset and all its transactions |
| `PUT` | `/api/assets/{id}/price` | Manual price entry |
| `DELETE` | `/api/assets/{id}/prices` | Clear all price history |
| `POST` | `/api/assets/{id}/prices/import` | Bulk import price rows |
| `GET` | `/api/assets/{id}/history?period=` | Price history for chart |

### Transactions — `/api/transactions`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/transactions` | List with filters |
| `POST` | `/api/transactions` | Create |
| `PUT` | `/api/transactions/{id}` | Update |
| `DELETE` | `/api/transactions/{id}` | Delete |

Query params: `period`, `date_from`, `date_to`, `broker`, `asset_type`, `asset_id`, `sort_by`, `sort_dir`

### Portfolio — `/api/portfolio`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/portfolio/summary` | Total value, invested, P&L, period return (Modified Dietz) |
| `GET` | `/api/portfolio/holdings` | Per-asset breakdown with period performance |
| `GET` | `/api/portfolio/chart` | `[{date, value_eur, invested_eur}]` time series |

All three accept: `period`, `date_from`, `date_to`, `broker`, `asset_type`

### Prices — `/api/prices`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/prices/status` | Staleness status per asset |
| `POST` | `/api/prices/refresh` | Background refresh for all active holdings |
| `POST` | `/api/prices/refresh/{id}` | Refresh single asset (fill-forward from last price) |

### Balance — `/api/balance`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/balance/{asset_id}` | List entries |
| `POST` | `/api/balance/{asset_id}` | Add entry (deposit / withdrawal / snapshot) |
| `DELETE` | `/api/balance/entries/{id}` | Delete entry |

### Import — `/api/import`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/import/parse` | Send raw text → LLM extracts transactions |
| `POST` | `/api/import/confirm` | Insert reviewed transactions |

---

## Price refresh

The frontend calls `/api/prices/status` on load. If `stale=true`, a background refresh fires automatically and a spinner appears in the navbar.

**Staleness per asset** (market timezone-aware):
- Market open → stale after `PRICE_REFRESH_TTL_OPEN` minutes
- Market closed, today's price in DB → not stale until next open
- Market closed, today's price missing → immediately stale
- CNMV funds → stale if no price today and local time > 18:00 Europe/Madrid

**Fetch range:**
- Single-asset refresh → fills forward from last recorded price date (works for non-portfolio/watchlist assets)
- Bulk refresh → 1 year before oldest transaction (initial), or last 5 days (incremental)

**Source chain:**

| Asset type | Primary | Fallback |
|------------|---------|---------|
| Stock / ETF | yfinance (batched) | Manual entry |
| Fund (ISIN) | investpy | mstarpy (Morningstar, exact secId pre-resolved) → Manual |
| FX rates | yfinance (`EURUSD=X` etc.) | Last known stored rate |

---

## LLM batch import

Paste any raw broker data (CSV, copy-pasted table, email text, PDF extract) and have an LLM extract the transactions.

1. Paste text + optional broker hint → **Analizar con IA**
2. Review and edit extracted rows inline
3. **Confirmar importación** → assets created if needed, transactions inserted, prices backfilled in background

```env
LLM_PROVIDER=gemini          # or: anthropic
GEMINI_API_KEY=AIza…
```

Default models: `gemini-2.0-flash` · `claude-opus-4-7`. Override with `LLM_MODEL=`.

---

## Tests

```bash
cd backend
python -m pytest tests/ -q
# 105 tests — assets, transactions, portfolio calculations, price fetcher
```
