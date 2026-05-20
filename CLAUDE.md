# CLAUDE.md — Agent context for portfolio manager

This file is for AI agents working on this codebase. Read it before making changes.

---

## What this project is

A personal investment portfolio tracker. The owner holds Spanish mutual funds (Fondos via Openbank), ETFs and stocks via Trade Republic, Revolut, and Degiro. Multi-currency (EUR, USD, GBP/GBX, CAD, SEK, …). Backend is FastAPI + DuckDB; frontend is React + Vite + Tailwind.

**Backend runs on port 3001** (not the default 8000). Frontend runs on port 5173.

---

## Non-obvious rules

### Always run tests before closing a backend task
```bash
cd backend && python -m pytest tests/ -q
```
105 tests must pass. Run them after any Python change, then commit.

### Commit after every feature or fix
Pattern: run pytest → fix failures → commit. Never leave working changes uncommitted at end of session.

### TypeScript check after frontend changes
```bash
cd frontend && npx tsc --noEmit
```

### DuckDB connection model
DuckDB is embedded (file-based). The app holds one connection open via `get_db()` singleton in `database.py`. Background tasks (price refresh) open their own connection via `duckdb.connect(db_path)` — this works because DuckDB supports multiple connections to the same file with one writer at a time.

**Never try to open the .duckdb file directly while the server is running** — use the REST API to test queries.

### SQL parameter ordering in DuckDB
DuckDB binds `?` positional parameters strictly in order. When building dynamic WHERE/HAVING clauses, the params list must exactly follow the placeholder order in the SQL string. A common mistake: pre-loading all date params before filter params, but WHERE comes before HAVING in SQL. See `get_value_at_date` in `portfolio_calc.py` for the correct pattern (build params incrementally: SELECT dates → WHERE filters → HAVING dates → final date).

---

## Architecture overview

### Data model

Everything derives from raw `transactions` rows. No materialized portfolio snapshots. Holdings, P&L, period performance, allocation — all computed at query time via DuckDB CTEs.

```
transactions → holdings CTE → join prices → portfolio metrics
```

### Key services

**`portfolio_calc.py`** — the brain. Contains:
- `get_holdings()` — per-asset breakdown with optional period performance
- `get_summary()` — portfolio totals + Modified Dietz period return
- `get_value_at_date()` — historical portfolio value (used by Modified Dietz)
- `get_modified_dietz()` — time-weighted period return accounting for cash flows
- `get_realized_pnl()` — AVCO method; builds cost basis from all transactions
- `_get_balance_holdings()` — balance-type asset rows (no transactions, snapshot-based)

**`price_fetcher.py`** — price ingestion. Key points:
- `refresh_all_prices()` — bulk refresh for assets with transactions only
- `refresh_single_asset()` — individual refresh; fills forward from last known price date (works for non-portfolio/watchlist assets too)
- `_get_fetch_range()` — decides start/end dates; 1 year before oldest tx for initial fetch
- `_mstar_resolve_secid()` — pre-resolves Morningstar performance ID via SecuritySearch.ashx to avoid fuzzy-search returning wrong share class
- `_normalize_currency()` — maps yfinance's `"GBp"` → `"GBX"`; GBX prices ÷100 before EUR conversion

**`price_status.py`** — per-asset staleness. Uses market timezone and trading hours. CNMV funds have special logic (stale after 18:00 Europe/Madrid if no price today).

### Balance asset type

Assets with `type='balance'` have no transactions and no price feed. They use `balance_entries` table with three entry types:
- `deposit` / `withdrawal` — cash flows
- `snapshot` — total portfolio value at a point in time

Portfolio value = latest snapshot. P&L = latest snapshot − net contributions. These are integrated into `get_holdings()`, `get_summary()`, `get_chart_data()`, and `get_value_at_date()`.

### Period performance

When a period filter is active (`period != 'all'`):
- Per-asset: simple `(current_value − period_start_value − net_flows) / (period_start_value + weighted_flows)` — displayed in `period_gain_eur` / `period_gain_pct`
- Portfolio summary: full Modified Dietz via `get_modified_dietz()` — displayed in `period_return_eur` / `period_return_pct`
- The "Invertido" column always shows the all-time cost basis (`total_shares × avg_buy_price_eur`), not `period_invested_eur`

### Broker/asset-type filters

`broker` and `asset_type` params are accepted by all three portfolio endpoints (`/summary`, `/holdings`, `/chart`) and thread through to every sub-query. The frontend sends them from the Portfolio page's FilterPills component and includes them in all API calls from `PortfolioSummaryCard`, `PortfolioChart`, and `PortfolioTable`.

---

## Frontend patterns

### Viewport-filling pages
Both Portfolio and Transactions pages use `h-[calc(100vh-3.5rem)]` (100vh minus the `h-14` navbar) with `flex flex-col`. The table body gets `flex-1 min-h-0 overflow-auto` — only the table scrolls, not the page.

### RefreshContext
`RefreshContext` broadcasts `lastRefreshAt` timestamp when prices finish refreshing. All components that display price data include it in their `useEffect` dependency array so they re-fetch automatically.

### API client
All types and API wrappers live in `frontend/src/api/client.ts`. Add new endpoint types there first, then use them in components.

### Error handling on 422
FastAPI validation errors have `detail` as an array of objects `[{msg, loc, type, …}]`, not a string. The frontend handles both: `typeof detail === 'string' ? detail : detail.map(e => e.msg).join('; ')`.

---

## Database migrations

The schema is initialized in `database.py` at startup via `CREATE TABLE IF NOT EXISTS`. When adding columns or modifying constraints:

1. Add `ALTER TABLE` statements in `_run_migrations()` in `database.py`, guarded by a try/except so they're idempotent
2. Update the `CREATE TABLE IF NOT EXISTS` statement for fresh installs
3. DuckDB unnamed CHECK constraints cannot be dropped by name — to change a CHECK, use `ALTER COLUMN type TYPE VARCHAR` (drops inline constraint), then `ALTER TABLE … ADD CHECK (…)` with the new constraint

---

## Brokers

| Broker | Asset types | Price source |
|--------|-------------|--------------|
| Openbank | Fondos (Spanish mutual funds) | investpy → mstarpy → manual |
| Trade Republic | Stocks, ETFs | yfinance |
| Revolut | Stocks, ETFs | yfinance |
| Degiro | Stocks, ETFs | yfinance |

Valid broker strings in DB: `openbank`, `trade_republic`, `revolut`, `degiro`

---

## Markets (pre-seeded)

| MIC | Exchange | Auto-detection |
|-----|----------|----------------|
| XETR | Frankfurt | ticker ends `.DE` |
| XAMS | Amsterdam | ticker ends `.AS` |
| XMAD | Madrid | ticker ends `.MC` |
| XLON | London | ticker ends `.L` — default currency GBX |
| XNYS | NYSE | bare ticker (fallback) |
| XNAS | NASDAQ | bare ticker (default) |
| CNMV | Spanish funds | ISIN starting `ES` |

---

## GBX (pence sterling)

yfinance returns `"GBp"` (lowercase p) for XLON assets. Detection and normalization:
- `_normalize_currency("GBp")` → `"GBX"`
- Price is divided by 100 before applying the GBP FX rate
- `EURGBX=X` doesn't exist in yfinance — always fetch `EURGBP=X` and divide by 100
- Frontend: `formatCcy` has a special case for GBX (not ISO 4217, Intl throws)

---

## ISIN validation

`_validate_isin()` in `asset.py` intentionally accepts any non-empty string. Off-market and manual assets use custom identifiers (e.g. `"OP001"`) that don't follow 12-char ISIN format. Do not re-add strict format validation.

---

## Testing notes

- `tests/conftest.py` sets up an in-memory DuckDB and a FastAPI TestClient for each test
- mstarpy tests use `patch.dict("sys.modules", {"mstarpy": MagicMock(Funds=mock_cls)})` plus `patch("app.services.price_fetcher._mstar_resolve_secid", return_value=None)` to avoid real HTTP calls
- Asset ISIN tests: `test_any_isin_format_accepted` (not `test_invalid_isin_rejected` — the old strict test was removed when validation was relaxed)

---

## Things to keep in mind

- The DuckDB `ASOF JOIN` is used in `get_chart_data` to fill price gaps on weekends/holidays across a date spine generated by `generate_series`
- `commission_eur` and `commission_currency` are stored separately; some brokers charge in the asset's native currency
- `price_eur` in the `transactions` table is locked at trade time — it must never be updated retroactively even if FX rates change
- Balance assets are excluded from the main SQL holdings query (they have no transactions); they're fetched separately and appended in Python
- The `refresh_log` table tracks every bulk refresh for debugging; single-asset refreshes are not logged
