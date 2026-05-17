# Portfolio Manager

Personal investment portfolio tracker supporting stocks, ETFs, and Spanish mutual funds (Fondos) across multiple brokers and currencies.

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI (Python) + DuckDB |
| Frontend | React + Vite + Tailwind CSS |
| Charts | Recharts |
| Tables | TanStack Table |
| Price data | yfinance (stocks/ETFs) + investpy/mstarpy (Fondos) |

## Features

- Track buy/sell transactions across Openbank, Trade Republic, Revolut, Degiro
- Multi-currency support (EUR, USD, etc.) with automatic FX conversion
- Portfolio overview: total value, P&L, allocation breakdown
- Historical portfolio value chart with period filters (1D / 1W / 1M / 6M / YTD / 1Y / 5Y / All)
- Automatic price refresh via yfinance; manual price entry for funds without automatic data
- Staleness-aware refresh: only fetches new prices when markets have closed

## Setup

### Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

API runs on http://localhost:8000  
API docs at http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App runs on http://localhost:5173

## Project Structure

```
portfolio/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── database.py          # DuckDB schema + seeding
│   │   ├── config.py            # Settings
│   │   ├── routers/             # API endpoints
│   │   ├── services/            # Business logic
│   │   └── models/              # Pydantic models
│   ├── data/                    # DuckDB file (gitignored)
│   ├── .env.example
│   └── requirements.txt
└── frontend/
    └── src/
        ├── api/client.ts        # API layer + types
        ├── components/          # React components
        ├── pages/               # Portfolio + Transactions pages
        └── utils/format.ts      # Number/currency formatters
```

## Brokers supported

- Openbank (Fondos / mutual funds via ISIN)
- Trade Republic
- Revolut
- Degiro

## Fund price data

For Spanish mutual funds (Fondos) identified by ISIN:
1. **investpy** (primary) — investing.com data, ISIN search
2. **mstarpy** (fallback) — Morningstar scraper
3. **Manual entry** — for funds without automatic coverage; enter NAV per date via the UI pencil icon

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `data/portfolio.duckdb` | Path to DuckDB file |
| `DEBUG` | `false` | Enable debug mode |
| `PRICE_REFRESH_TTL_OPEN` | `15` | Minutes before stale during market hours |
| `PRICE_REFRESH_TTL_CLOSED` | `1440` | Minutes before stale outside market hours |
