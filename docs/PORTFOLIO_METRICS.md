# Portfolio Metrics Reference

Todas las métricas se calculan dinámicamente desde las tablas `transactions`, `prices`, `balance_entries`. No hay snapshots materializados.

Los parámetros de filtro `date_from` / `date_to` controlan el "intervalo" activo. La fecha final de intervalo siempre es la fecha actual si no se especifica `date_to`.

---

## Tabla de Holdings (stocks / ETFs / fondos)

### Métricas de posición (snapshot a `date_to`)

| Columna | Definición | Fórmula |
|---------|-----------|---------|
| **Cantidad** | Participaciones netas en cartera | `SUM(buy_shares) − SUM(sell_shares)` donde `date ≤ date_to` |
| **P. Medio (PMP)** | Precio medio ponderado de compra | `SUM(buy_shares × price_eur) / SUM(buy_shares)` (solo compras, en moneda local) |
| **Invertido** | Capital actualmente invertido | `Cantidad × PMP_eur` |
| **P. Actual** | Precio de mercado a `date_to` | Último precio conocido `≤ date_to` (ASOF fill-forward) |
| **Valor** | Valoración a `date_to` | `Cantidad × P.Actual` |

> **Nota sobre PMP y ventas:** Las ventas reducen la `Cantidad` pero NO modifican el PMP. El PMP solo cambia cuando se realizan nuevas compras.

### Métricas de resultado (siempre respecto a posición actual)

| Columna | Definición | Fórmula |
|---------|-----------|---------|
| **G/P** | Ganancia/Pérdida no realizada (todo tiempo) | `Valor − Invertido` = `pnl_eur` |
| **G/P %** | G/P como porcentaje del invertido | `100 × G/P / Invertido` |

### Métricas de variación (dentro del intervalo)

| Columna | Definición | Fórmula |
|---------|-----------|---------|
| **Cambio** | Apreciación de precio sobre la posición actual | `Cantidad × (P_actual − P_inicio_intervalo)` |
| **Cambio %** | Cambio normalizado por invertido | `100 × Cambio / Invertido` |

> **Cambio vs G/P:** G/P mide toda la ganancia latente respecto al coste de adquisición (todo tiempo). Cambio mide cuánto se ha movido el precio de la posición actual dentro del intervalo seleccionado.

> **Fallback de P_inicio_intervalo:** Si el activo no tenía precio en `date_from` (fue comprado durante el período), se usa el `PMP` como precio de inicio, de modo que `Cambio ≈ G/P` para posiciones nuevas.

### Asignación

| Columna | Definición | Fórmula |
|---------|-----------|---------|
| **Asignación** | Peso del activo en la cartera | `Invertido_activo / SUMA(Invertido_todos_activos_TX)` |

Las carteras/cuentas tienen su propio pool de asignación (suma 100% entre ellas por separado).

---

## Carteras / Cuentas (balance assets)

Los activos de tipo `balance` no tienen transacciones ni precios; su valor proviene de entradas manuales en `balance_entries` (`snapshot`, `deposit`, `withdrawal`).

| Columna | Definición |
|---------|-----------|
| **Inicio** | Primer snapshot `≥ date_from` dentro del período; fallback: último snapshot `≤ date_from` |
| **Invertido** | Suma neta de depósitos − retiradas desde el principio hasta `date_to` |
| **Fin** | Último snapshot `≤ date_to`; fallback: primer snapshot `≥ date_to` |
| **G/P** | `Fin − Invertido` (ganancia/pérdida todo tiempo) |
| **G/P %** | `(Fin − Invertido) / Invertido × 100` |
| **Cambio** | `Fin − Inicio − Aportaciones_netas_en_período` (Modified Dietz numerador) |
| **Cambio %** | Modified Dietz: `Cambio / (Inicio + Σ(CF_i × W_i)) × 100` |

---

## KPI Cards (PortfolioSummaryCard)

Grid fijo 3 × 2 (siempre visible independientemente del período):

| Posición | Label | Fórmula |
|----------|-------|---------|
| **(0,0)** | Valor total | `SUM(Valor_TX) + SUM(Fin_balance)` |
| **(0,1)** | G/P no realizada | `SUM(Cambio_EUR)` de todos los activos en el intervalo. Cuando `period='all'` equivale a G/P. |
| **(1,0)** | Total Invertido | `SUM(Invertido_TX) + SUM(Invertido_balance)` |
| **(1,1)** | G/P Realizada | Suma de G/P de todas las ventas en `[date_from, date_to]`. Clickable → lista de ventas. |
| **(2,0)** | Rendimiento total | `total_pnl_eur + realized_pnl_all_time_eur`. Ignora `date_from`, solo respeta `date_to`. `% = / total_invested_ever_eur` |
| **(2,1)** | Cambio | `G/P no realizada + G/P Realizada` = cambio total de riqueza en el período. `% = / period_start_value` |

---

## Gráfica (PortfolioChart)

- **Eje X:** Fecha (`date_from` → `date_to`)  
- **Eje Y:** Euros

| Serie | Definición |
|-------|-----------|
| **Valor** | `SUM(shares × price_eur)` por fecha + `SUM(latest_snapshot)` de balance assets |
| **Invertido** | AVCO cost basis acumulado por fecha + contribuciones netas de balance |
| **G/P (€)** | `Valor − Invertido` por fecha |
| **G/P (%)** | `(Valor − Invertido) / Invertido × 100` por fecha |

Las Carteras/Cuentas se incluyen automáticamente en la gráfica cuando no hay filtro de broker activo y el filtro de tipo incluye 'balance' (o está vacío).

---

## Cálculo de G/P en Ventas (AVCO)

El sistema usa **AVCO (Average Cost)** para calcular la ganancia realizada:

```
AVCO = SUM(buy_shares × price_eur) / SUM(buy_shares)  (running average, incluyendo historial completo)

G/P_venta = shares_vendidas × (precio_venta − AVCO) − comisión_venta
```

Las comisiones de compra se incluyen en el AVCO (`AVCO_neto = (shares × price + commission) / shares`). Las comisiones de venta se restan del beneficio.

> **AVCO vs FIFO:** El backend usa AVCO para la G/P de ventas en el KPI "G/P Realizada". El historial AVCO se construye desde el inicio de los tiempos, garantizando que los filtros de fecha no alteren el precio de coste.

---

## Coherencia de filtros

Los filtros `broker` y `asset_type` se aplican a los tres endpoints `/summary`, `/holdings`, `/chart` de forma idéntica:

- `broker` activo → activos balance excluidos (no tienen broker)
- `asset_type` sin 'balance' → activos balance excluidos
- `asset_type` solo 'balance' → solo carteras/cuentas en todo
