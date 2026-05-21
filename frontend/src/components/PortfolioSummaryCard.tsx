import { useEffect, useState } from 'react'
import type { PortfolioSummary } from '../api/client'
import { portfolioApi } from '../api/client'
import { useRefresh } from '../contexts/RefreshContext'
import { formatEur, formatPct, pnlClass } from '../utils/format'

// ─── Debug mode ──────────────────────────────────────────────────────────────
// Set to true to show calculation breakdown on hover over each metric card.
const DEBUG_METRICS = true
// ─────────────────────────────────────────────────────────────────────────────

const PERIOD_LABELS: Record<string, string> = {
  '1d': '1D', '1w': '1S', '1m': '1M', '6m': '6M',
  'ytd': 'YTD', '1y': '1A', '5y': '5A', 'all': 'Total', 'custom': 'Período',
}

interface Props {
  period: string
  dateFrom: string
  dateTo: string
  broker?: string
  assetType?: string
}

export function PortfolioSummaryCard({ period, dateFrom, dateTo, broker, assetType }: Props) {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const { lastRefreshAt } = useRefresh()

  useEffect(() => {
    const params: Record<string, string> = period === 'custom'
      ? { ...(dateFrom && { date_from: dateFrom }), ...(dateTo && { date_to: dateTo }) }
      : { period }
    if (broker) params.broker = broker
    if (assetType) params.asset_type = assetType
    portfolioApi.summary(params).then(setSummary).catch(() => {})
  }, [period, dateFrom, dateTo, broker, assetType, lastRefreshAt])

  if (!summary) {
    return (
      <div className="space-y-3 animate-pulse">
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-24 bg-gray-100 dark:bg-gray-800 rounded-xl" />
          ))}
        </div>
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-20 bg-gray-100 dark:bg-gray-800 rounded-xl" />
          ))}
        </div>
      </div>
    )
  }

  const hasPeriod = summary.period_return_eur !== null
  const hasRealized = summary.total_invested_eur > 0 || summary.realized_pnl_eur !== 0
  const periodLabel = PERIOD_LABELS[period] ?? 'Período'

  // ── Debug line builders (only populated when DEBUG_METRICS is true) ─────────
  const f = formatEur
  const p = formatPct

  const dbgValorTotal = DEBUG_METRICS ? [
    'total_value_eur',
    `= ${f(summary.total_value_eur)}`,
    '',
    '· TX: shares × latest_price_eur',
    '· + balance: latest snapshot ≤ date_to',
    summary.last_updated ? `· Precios al: ${summary.last_updated}` : '· Sin precios cargados',
  ] : undefined

  const dbgVIni = DEBUG_METRICS && hasPeriod ? [
    'period_start_value_eur  (V_ini Dietz)',
    `= ${f(summary.period_start_value_eur!)}`,
    '',
    '· TX: shares@date_from × price@date_from',
    '· + balance: primer snapshot ≥ date_from',
  ] : undefined

  const dbgInvertido = DEBUG_METRICS && !hasPeriod ? [
    'total_invested_eur  (no hay período)',
    `= ${f(summary.total_invested_eur)}`,
    '',
    '· TX: shares × avg_buy_price_eur',
    '· + balance: Σdepósitos − Σretiradas ≤ date_to',
  ] : undefined

  const impliedCF = hasPeriod
    ? summary.total_value_eur - summary.period_start_value_eur! - summary.period_return_eur!
    : 0
  const dbgRendPeriodo = DEBUG_METRICS && hasPeriod ? [
    `Modified Dietz  [${periodLabel}]`,
    `V_fin = ${f(summary.total_value_eur)}`,
    `V_ini = ${f(summary.period_start_value_eur!)}`,
    `ΣCF   = ${f(impliedCF)}`,
    `  (buys + bal.dep − sells − bal.ret)`,
    'Gain = V_fin − V_ini − ΣCF',
    `     = ${f(summary.period_return_eur!)}`,
    `R%   = ${p(summary.period_return_pct!)}`,
  ] : undefined

  const dbgGPTotal = DEBUG_METRICS ? [
    'total_pnl_eur',
    '= total_value − total_invested',
    `= ${f(summary.total_value_eur)} − ${f(summary.total_invested_eur)}`,
    `= ${f(summary.total_pnl_eur)}`,
    `R% = ${p(summary.total_pnl_pct)}`,
    '',
    '· "Invertido" = TX cost basis',
    '·   + balance net contrib hasta date_to',
  ] : undefined

  const dbgGPSinPeriodo = DEBUG_METRICS && !hasPeriod ? [
    'total_pnl_eur',
    '= total_value − total_invested',
    `= ${f(summary.total_value_eur)} − ${f(summary.total_invested_eur)}`,
    `= ${f(summary.total_pnl_eur)}`,
    `R% = ${p(summary.total_pnl_pct)}`,
  ] : undefined

  const dbgTotalInv = DEBUG_METRICS ? [
    'total_invested_eur',
    `= ${f(summary.total_invested_eur)}`,
    '',
    '· TX: Σ(shares × avg_buy_price_eur)',
    '· + balance: Σdepósitos − Σretiradas ≤ date_to',
  ] : undefined

  const dbgRealized = DEBUG_METRICS ? [
    'AVCO — sells in window',
    `Gross = ${f(summary.realized_pnl_eur)}  (${p(summary.realized_pnl_pct)})`,
    `Net   = ${f(summary.realized_pnl_net_eur)}  (${p(summary.realized_pnl_net_pct)})`,
    '',
    `· Ever invested: ${f(summary.total_invested_ever_eur)}`,
    '· Net = gross − comisiones compra/venta',
    '· Balance no computa en realizada',
  ] : undefined

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Valor total"
          value={f(summary.total_value_eur)}
          sub={summary.last_updated ? `Actualizado: ${summary.last_updated}` : 'Sin precios'}
          debugLines={dbgValorTotal}
        />
        {hasPeriod ? (
          <StatCard
            label="Valor inicio período"
            value={f(summary.period_start_value_eur!)}
            debugLines={dbgVIni}
          />
        ) : (
          <StatCard
            label="Invertido (en cartera)"
            value={f(summary.total_invested_eur)}
            debugLines={dbgInvertido}
          />
        )}
        {hasPeriod ? (
          <StatCard
            label={`Rendimiento ${periodLabel}`}
            value={f(summary.period_return_eur!)}
            sub={p(summary.period_return_pct!)}
            valueClass={pnlClass(summary.period_return_eur!)}
            debugLines={dbgRendPeriodo}
          />
        ) : (
          <StatCard
            label="Ganancia / Pérdida"
            value={f(summary.total_pnl_eur)}
            sub={p(summary.total_pnl_pct)}
            valueClass={pnlClass(summary.total_pnl_eur)}
            debugLines={dbgGPSinPeriodo}
          />
        )}
      </div>
      {hasRealized && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard
            label="Total invertido"
            value={f(summary.total_invested_eur)}
            compact
            debugLines={dbgTotalInv}
          />
          <StatCard
            label="Rendimiento total"
            value={f(summary.total_pnl_eur)}
            sub={p(summary.total_pnl_pct)}
            valueClass={pnlClass(summary.total_pnl_eur)}
            compact
            debugLines={dbgGPTotal}
          />
          <RealizedCard
            label={hasPeriod ? `Ganancia realizada ${periodLabel}` : 'Ganancia realizada'}
            grossEur={summary.realized_pnl_eur}
            grossPct={summary.realized_pnl_pct}
            netEur={summary.realized_pnl_net_eur}
            netPct={summary.realized_pnl_net_pct}
            debugLines={dbgRealized}
          />
        </div>
      )}
    </div>
  )
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

function DebugTooltip({ lines }: { lines: string[] }) {
  if (!DEBUG_METRICS) return null
  return (
    <div className="pointer-events-none absolute z-50 hidden group-hover:block bottom-full left-0 mb-1.5 min-w-[260px] bg-gray-950 border border-gray-700 text-gray-200 text-[11px] rounded-lg px-3 py-2.5 font-mono shadow-2xl">
      {lines.map((line, i) =>
        line === '' ? (
          <div key={i} className="h-2" />
        ) : (
          <div key={i} className={`leading-[1.6] ${line.startsWith('·') ? 'text-gray-400' : ''}`}>
            {line}
          </div>
        )
      )}
    </div>
  )
}

// ── StatCard ──────────────────────────────────────────────────────────────────

function StatCard({
  label, value, sub, valueClass = '', compact = false, debugLines,
}: {
  label: string; value: string; sub?: string; valueClass?: string; compact?: boolean
  debugLines?: string[]
}) {
  return (
    <div className="relative group bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">{label}</p>
      <p className={`${compact ? 'text-xl' : 'text-2xl'} font-bold text-gray-900 dark:text-white ${valueClass}`}>{value}</p>
      {sub && <p className={`text-sm mt-0.5 ${valueClass || 'text-gray-400'}`}>{sub}</p>}
      {debugLines && <DebugTooltip lines={debugLines} />}
    </div>
  )
}

// ── RealizedCard ──────────────────────────────────────────────────────────────

function RealizedCard({
  label, grossEur, grossPct, netEur, netPct, debugLines,
}: {
  label: string; grossEur: number; grossPct: number; netEur: number; netPct: number
  debugLines?: string[]
}) {
  const gc = pnlClass(grossEur)
  const nc = pnlClass(netEur)
  return (
    <div className="relative group bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">{label}</p>
      <div className="flex items-baseline gap-2">
        <p className={`text-xl font-bold ${gc}`}>{formatEur(grossEur)}</p>
        <p className={`text-sm ${gc}`}>{formatPct(grossPct)}</p>
      </div>
      <div className="flex items-baseline gap-2 mt-0.5">
        <p className={`text-sm ${nc || 'text-gray-400 dark:text-gray-500'}`}>{formatEur(netEur)}</p>
        <p className={`text-xs ${nc || 'text-gray-400 dark:text-gray-500'}`}>{formatPct(netPct)} · neta</p>
      </div>
      {debugLines && <DebugTooltip lines={debugLines} />}
    </div>
  )
}
