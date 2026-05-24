# Changelog

## [Unreleased] — Portfolio Page Overhaul

### Resumen de cambios
Revisión completa de la página `/portfolio`: redefinición de métricas, nuevas columnas, rediseño de KPI cards, corrección de bugs en balance assets, nuevo endpoint de ventas realizadas.

---

### Backend

#### Nuevos campos en `HoldingRow`

| Campo | Antes | Ahora |
|-------|-------|-------|
| `cambio_eur` | No existía | `total_shares × (price_date_to − price_date_from)` |
| `cambio_pct` | No existía | `cambio_eur / (shares × avg_buy_price_eur) × 100` |
| `balance_inicio_eur` | No existía | Primer snapshot `≥ date_from` (fallback: último `≤ date_from`) |

Campos eliminados de `HoldingRow` (no se exponían en la UI):
- `period_invested_eur` — reemplazado por `cambio_eur`
- `period_avg_price_eur` — no se usaba en UI

#### Nuevos campos en `PortfolioSummary`

| Campo | Descripción |
|-------|-------------|
| `unrealized_cambio_eur` | SUM(cambio_eur) para todos los activos — G/P no realizada (period) |
| `unrealized_cambio_pct` | `unrealized_cambio_eur / total_invested_eur × 100` |
| `rendimiento_total_eur` | `total_pnl_eur + realized_pnl_all_time_eur` — todo tiempo, solo respeta `date_to` |
| `rendimiento_total_pct` | `rendimiento_total_eur / total_invested_ever_eur × 100` |
| `cambio_total_eur` | `unrealized_cambio_eur + realized_pnl_eur` — cambio total en el período |
| `cambio_total_pct` | `cambio_total_eur / period_start_value_eur × 100` |

#### Correcciones de bugs en balance assets (`_get_balance_holdings`)

1. **`balance_contributions_eur` sin filtro de fecha (bug):** La CTE `net_contrib` no tenía `AND date <= latest_date`, lo que incluía depósitos futuros. Corregido.
2. **Lookup "Inicio" incorrecto:** Antes usaba `last snapshot ≤ date_from`. Ahora usa `first snapshot ≥ date_from` (acotado a `date_to`) con fallback a `last ≤ date_from`.
3. **"Fin" sin fallback:** Añadido fallback a `first snapshot ≥ date_to` cuando no existe snapshot `≤ date_to`.

#### Fórmula de Asignación

| Antes | Ahora |
|-------|-------|
| `value_eur / total_portfolio_value` (por valor de mercado) | `invested_eur / total_portfolio_invested` (por coste base) |

Pools separados: TX assets entre ellos, balance assets entre ellos.

#### Nuevo endpoint

`GET /api/portfolio/realized-sales` — devuelve lista de ventas con P&L AVCO calculado, filtrable por período/broker/tipo.

---

### Frontend

#### `PortfolioSummaryCard` — rediseño grid 3×2

**Antes:** Layout dinámico (1 o 2 filas según `hasRealized`). Condicionado por `hasPeriod`.

**Ahora:** Grid fijo 3×2 siempre visible:
- **(0,0)** Valor total | **(0,1)** G/P no realizada (SUM de cambios del período)
- **(1,0)** Total Invertido | **(1,1)** G/P Realizada (clickable → `RealizedSalesModal`)
- **(2,0)** Rendimiento total | **(2,1)** Cambio

Eliminado el card "Valor inicio período" (era confuso y redundante).

#### `PortfolioTable` — columnas holdings

| Columna G/P | Antes | Ahora |
|-------------|-------|-------|
| G/P (€) | Period-aware: mostraba `period_gain_eur` cuando había período | Siempre `pnl_eur` (ganancia latente all-time) |
| G/P (%) | Period-aware: mostraba `period_gain_pct` | Siempre `gain_pct` |

Nueva columna **Cambio** (€ + % en misma celda): precio período × cantidad actual.

Para reducir columnas a 1440p: G/P y Cambio muestran valor € con % debajo en la misma celda.

#### `PortfolioTable` — sección Carteras/Cuentas

| Columna | Antes | Ahora |
|---------|-------|-------|
| "Apor. netas" | Flujos del período | Renombrado "Invertido" — aportaciones netas all-time ≤ `date_to` |
| "Inicio" | `period_start_value_eur` | `balance_inicio_eur` (primer snapshot ≥ `date_from`) |
| G/P | No existía separado | `pnl_eur` (Fin − Invertido all-time) con `gain_pct` |
| Cambio | Existía como "G/P" period-aware | `period_gain_eur` (Modified Dietz numerador) |

#### Componente nuevo: `RealizedSalesModal`

Modal con tabla de ventas del período (fecha, activo, participaciones, precio venta, base de coste, G/P, G/P %). Abierto desde la card G/P Realizada.

#### Refactor: `getPeriodParams` helper

Extraída función `utils/period.ts::getPeriodParams()` que elimina la construcción duplicada de params de período en `PortfolioSummaryCard`, `PortfolioTable`, `PortfolioChart`, y `RealizedSalesModal`.

---

### Tests

**Backend** — 14 nuevos tests en `test_portfolio.py`:
- `TestCambioEur` (5 tests): cálculo correcto, fallback, negative, no-period
- `TestAllocationByInvested` (1 test): asignación por invertido, no por valor
- `TestBalanceContributionDateFilter` (1 test): fix del bug de fecha en contributions
- `TestBalanceInicio` (2 tests): lookup nuevo para snapshot inicio
- `TestRendimientoTotal` (2 tests): unrealized + all-time realized
- `TestRealizedSalesEndpoint` (3 tests): endpoint vacío, P&L correcto, filtro período

Tests actualizados (2): `test_period_gain_pct_simple_roi` → `test_cambio_uses_price_difference_times_quantity`; `test_period_gain_uses_historical_price_at_date_to` → `test_cambio_uses_historical_price_at_date_to`.

**Total:** 129 tests (115 originales + 14 nuevos).
