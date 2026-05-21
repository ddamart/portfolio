import { useEffect, useState } from 'react'
import type { PortfolioSummary } from '../api/client'
import { portfolioApi } from '../api/client'
import { useRefresh } from '../contexts/RefreshContext'
import { formatEur, formatPct, pnlClass } from '../utils/format'

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

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Valor total"
          value={formatEur(summary.total_value_eur)}
          sub={summary.last_updated ? `Actualizado: ${summary.last_updated}` : 'Sin precios'}
        />
        {hasPeriod ? (
          <StatCard
            label="Valor inicio período"
            value={formatEur(summary.period_start_value_eur!)}
          />
        ) : (
          <StatCard
            label="Invertido (en cartera)"
            value={formatEur(summary.total_invested_eur)}
          />
        )}
        {hasPeriod ? (
          <StatCard
            label={`Rendimiento ${periodLabel}`}
            value={formatEur(summary.period_return_eur!)}
            sub={formatPct(summary.period_return_pct!)}
            valueClass={pnlClass(summary.period_return_eur!)}
          />
        ) : (
          <StatCard
            label="Ganancia / Pérdida"
            value={formatEur(summary.total_pnl_eur)}
            sub={formatPct(summary.total_pnl_pct)}
            valueClass={pnlClass(summary.total_pnl_eur)}
          />
        )}
      </div>
      {hasRealized && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard
            label="Total invertido"
            value={formatEur(summary.total_invested_eur)}
            compact
          />
          <StatCard
            label={hasPeriod ? `Ganancia realizada ${periodLabel}` : 'Ganancia realizada'}
            value={formatEur(summary.realized_pnl_eur)}
            sub={formatPct(summary.realized_pnl_pct)}
            valueClass={pnlClass(summary.realized_pnl_eur)}
            compact
          />
          <StatCard
            label={hasPeriod ? `G. realizada neta ${periodLabel}` : 'Ganancia realizada (neta)'}
            value={formatEur(summary.realized_pnl_net_eur)}
            sub={`${formatPct(summary.realized_pnl_net_pct)} · post comisiones`}
            valueClass={pnlClass(summary.realized_pnl_net_eur)}
            compact
          />
        </div>
      )}
    </div>
  )
}

function StatCard({
  label, value, sub, valueClass = '', compact = false,
}: { label: string; value: string; sub?: string; valueClass?: string; compact?: boolean }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">{label}</p>
      <p className={`${compact ? 'text-xl' : 'text-2xl'} font-bold text-gray-900 dark:text-white ${valueClass}`}>{value}</p>
      {sub && <p className={`text-sm mt-0.5 ${valueClass || 'text-gray-400'}`}>{sub}</p>}
    </div>
  )
}
