# Portfolio Manager

Personal investment portfolio tracker supporting stocks, ETFs, and Spanish mutual funds (Fondos) across multiple brokers and currencies. All metrics are computed dynamically at query time — no stored snapshots.

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI (Python 3.11+) + DuckDB |
| Frontend | React 19 + Vite + Tailwind CSS 4 |
| Charts | Recharts |
| Tables | TanStack Table v8 |
| Price data | yfinance · investpy · mstarpy |
| LLM import | Google Gemini (default) · Anthropic Claude |

## Features

- Track buy/sell transactions across Openbank, Trade Republic, Revolut, Degiro
- Multi-currency support (EUR, USD, GBP, …) with automatic FX conversion
- Portfolio overview: total value, P&L, allocation breakdown
- Historical portfolio value chart with period filters (1D / 1W / 1M / 6M / YTD / 1Y / 5Y / All)
- Automatic price refresh via yfinance; manual price entry for funds without automatic data
- Staleness-aware refresh: skips fetching when the market is still open and prices are fresh
- **LLM-powered batch import**: paste raw broker data in any format → AI extracts transactions → editable preview → confirm

---

## Setup

### Prerequisites

- **Python 3.11 or 3.12** installed from [python.org](https://www.python.org/downloads/) (not the Windows Store version)
- **Node.js 18+**

### 1. Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\pip install -r requirements.txt
cp .env.example .env          # then edit .env with your API keys

# macOS / Linux
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

### 2. Frontend

```bash
cd frontend
npm install
```

### 3. Start

**Windows** — opens two separate PowerShell terminals:
```powershell
.\start.ps1
```

**macOS / Linux** — runs both in one terminal (Ctrl+C stops both):
```bash
chmod +x start.sh
./start.sh
```

**Manually** (any platform):
```bash
# Terminal 1 — backend
cd backend
.venv\Scripts\uvicorn app.main:app --reload   # Windows
.venv/bin/uvicorn app.main:app --reload        # macOS/Linux

# Terminal 2 — frontend
cd frontend && npm run dev
```

| URL | Description |
|-----|-------------|
| http://localhost:5173 | Web app |
| http://localhost:8000/docs | Interactive API docs (Swagger UI) |

---

## Environment Variables

All variables go in `backend/.env` (copy from `.env.example`).

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `data/portfolio.duckdb` | Path to DuckDB file |
| `DEBUG` | `false` | Enable debug mode |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `PRICE_REFRESH_TTL_OPEN` | `15` | Minutes before prices are stale while market is open |
| `PRICE_REFRESH_TTL_CLOSED` | `1440` | Minutes before prices are stale after market close (24h) |
| `LLM_PROVIDER` | `gemini` | LLM for batch import: `gemini` or `anthropic` |
| `GEMINI_API_KEY` | _(empty)_ | Google Gemini API key (required if `LLM_PROVIDER=gemini`) |
| `ANTHROPIC_API_KEY` | _(empty)_ | Anthropic API key (required if `LLM_PROVIDER=anthropic`) |
| `LLM_MODEL` | _(empty)_ | Override default model (`gemini-2.0-flash` / `claude-opus-4-7`) |

---

## Project Structure

```
portfolio/
├── start.ps1                  # Windows launcher (two PowerShell windows)
├── start.sh                   # Unix launcher (one terminal, Ctrl+C to stop)
│
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, CORS, router registration, lifespan
│   │   ├── config.py          # Pydantic settings (reads .env)
│   │   ├── database.py        # DuckDB connection singleton, schema creation, market seeding
│   │   ├── models/
│   │   │   ├── asset.py       # Asset, AssetCreate, AssetOut, AssetUpdate
│   │   │   ├── transaction.py # TransactionCreate, TransactionUpdate, TransactionOut
│   │   │   └── portfolio.py   # PortfolioSummary, HoldingRow, ChartPoint
│   │   ├── routers/
│   │   │   ├── assets.py      # /api/assets — CRUD + search + manual price entry
│   │   │   ├── transactions.py# /api/transactions — CRUD with filters
│   │   │   ├── portfolio.py   # /api/portfolio — summary, holdings, chart
│   │   │   ├── prices.py      # /api/prices — status + refresh triggers
│   │   │   └── import_router.py # /api/import — LLM parse + confirm
│   │   └── services/
│   │       ├── portfolio_calc.py  # All DuckDB CTE queries for portfolio metrics
│   │       ├── price_fetcher.py   # yfinance + investpy + mstarpy; backfill logic
│   │       ├── price_status.py    # Per-asset staleness using market timezone/hours
│   │       ├── currency.py        # EUR conversion from fx_rates table
│   │       └── llm_parser.py      # Gemini/Anthropic provider abstraction + prompt
│   ├── data/                  # DuckDB file lives here (gitignored)
│   ├── .env.example
│   └── requirements.txt
│
└── frontend/
    └── src/
        ├── api/client.ts      # Axios instance + all TypeScript types + API wrappers
        ├── pages/
        │   ├── Portfolio.tsx      # Overview: summary card + chart + holdings table
        │   ├── Transactions.tsx   # Transaction list + add/edit form
        │   └── Import.tsx         # LLM batch import: paste → preview → confirm
        ├── components/
        │   ├── Navbar.tsx             # Navigation + price refresh status
        │   ├── PortfolioSummaryCard.tsx
        │   ├── PortfolioChart.tsx      # Recharts line chart
        │   ├── PortfolioTable.tsx      # TanStack Table (holdings)
        │   ├── PeriodFilter.tsx        # 1D/1W/1M/6M/YTD/1Y/5Y/All selector
        │   ├── TransactionForm.tsx     # Add/edit form with asset autocomplete
        │   ├── TransactionTable.tsx    # TanStack Table (transactions)
        │   └── ManualPriceModal.tsx    # NAV entry for manual-price assets
        └── utils/format.ts    # Number and currency formatters
```

---

## API Reference

### Assets — `/api/assets`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/assets` | List all assets |
| `GET` | `/api/assets/search?q=` | Ticker / name autocomplete (max 10) |
| `POST` | `/api/assets` | Create asset (auto-fetches metadata + historical prices) |
| `PUT` | `/api/assets/{id}` | Update asset fields |
| `PUT` | `/api/assets/{id}/price?price=&price_date=&currency=` | Manual price entry for `manual_price=true` assets |

**Ticker → market auto-detection on creation:**

| Pattern | Market |
|---------|--------|
| Ends `.DE` | XETR (Frankfurt) |
| Ends `.AS` | XAMS (Amsterdam) |
| Ends `.MC` | XMAD (Madrid) |
| Ends `.L` | XLON (London) |
| ISIN (`ES…`) | CNMV (Spanish funds) |
| Bare ticker | XNAS (NASDAQ default) |

### Transactions — `/api/transactions`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/transactions` | List with optional filters (see below) |
| `GET` | `/api/transactions/{id}` | Single transaction |
| `POST` | `/api/transactions` | Create |
| `PUT` | `/api/transactions/{id}` | Update |
| `DELETE` | `/api/transactions/{id}` | Delete |

**GET filters:** `period`, `date_from`, `date_to`, `broker`, `asset_type`, `asset_id`, `sort_by`, `sort_dir`

**`period` values:** `1d` `1w` `1m` `6m` `ytd` `1y` `5y` `all`

**Valid brokers:** `openbank` `trade_republic` `revolut` `degiro`

### Portfolio — `/api/portfolio`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/portfolio/summary` | Total value, invested, P&L, P&L % |
| `GET` | `/api/portfolio/holdings` | Per-asset breakdown (shares, avg cost, current price, P&L, daily change, allocation %) |
| `GET` | `/api/portfolio/chart` | Time series `[{date, value_eur}]` for the period filter |

All three accept `period`, `date_from`, `date_to` query params.

### Prices — `/api/prices`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/prices/status` | `{last_refresh, stale, refreshing, assets[]}` |
| `POST` | `/api/prices/refresh` | Trigger background refresh for all active holdings |
| `POST` | `/api/prices/refresh/{asset_id}` | Refresh single asset |

### Import — `/api/import`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/import/parse` | Send raw text to LLM → returns parsed transactions |
| `POST` | `/api/import/confirm` | Insert reviewed transactions into DB |

**Parse request body:**
```json
{ "raw_text": "…broker data…", "broker_hint": "degiro" }
```

---

## Database Schema

```sql
markets      (id, mic, name, timezone, open_time, close_time, country)
assets       (id, name, ticker, type, currency, market_id, image_url, manual_price, created_at)
transactions (id, asset_id, type, broker, shares, price, price_eur, currency,
              commission, commission_eur, date, notes, created_at, updated_at)
prices       (asset_id, date, price, currency, price_eur)   -- PRIMARY KEY (asset_id, date)
fx_rates     (date, from_ccy, to_ccy, rate)                 -- PRIMARY KEY (date, from_ccy, to_ccy)
refresh_log  (id, started_at, finished_at, assets_updated, status)
```

Pre-seeded markets: `XETR` `XAMS` `XMAD` `XLON` `XNYS` `XNAS` `CNMV`

**Why `price_eur` is stored twice:**
- In `transactions`: locked-in historical EUR rate at the time of the trade (cost basis)
- In `prices`: converted at the rate for each price date (current valuation)

---

## Price Refresh Logic

Prices are fetched via background tasks; the frontend polls `/api/prices/status` on load.

**Staleness per asset** is evaluated against its market's timezone and trading hours:
- Market currently open → stale after `PRICE_REFRESH_TTL_OPEN` minutes (default 15)
- Market closed today and today's price is already in DB → not stale until next open
- Market closed and today's price is missing → stale immediately
- CNMV funds → stale if no price today and current time > 18:00 Europe/Madrid

**Fetch range:**
- First-ever fetch (no prices in DB) → backfill from oldest transaction date − 5 days
- Normal refresh (prices exist) → last 5 days only

**Sources by asset type:**

| Asset type | Primary | Fallback |
|------------|---------|---------|
| Stock / ETF | yfinance (batch) | Manual entry |
| Fund (ISIN) | investpy (investing.com) | mstarpy (Morningstar) → Manual entry |
| FX rates | yfinance (`EURUSD=X`, etc.) | Last known rate |

---

## LLM Batch Import

The Import page lets you paste raw broker data in any format (CSV, copy-pasted table, email extract, PDF text) and have an LLM extract the transactions.

**Flow:**
1. Paste text + optional broker hint → click **Analizar con IA**
2. Review and edit the extracted rows in the preview table (all fields are editable inline)
3. Rows with an unrecognised broker are highlighted in red — select a valid broker before confirming
4. Click **Confirmar importación** → assets are created if needed, transactions are inserted, price backfill runs in background

**Provider configuration** in `backend/.env`:

```env
LLM_PROVIDER=gemini           # or: anthropic
GEMINI_API_KEY=AIza…
# ANTHROPIC_API_KEY=sk-ant-…
```

Default models: `gemini-2.0-flash` (Gemini) · `claude-opus-4-7` (Anthropic). Override with `LLM_MODEL=`.

---

## Brokers Supported

| Broker | Asset types | Notes |
|--------|-------------|-------|
| Openbank | Fondos (mutual funds) | ISIN-based; prices via investpy/mstarpy |
| Trade Republic | Stocks, ETFs | Ticker-based; prices via yfinance |
| Revolut | Stocks, ETFs | Ticker-based; prices via yfinance |
| Degiro | Stocks, ETFs | Ticker-based; prices via yfinance |
