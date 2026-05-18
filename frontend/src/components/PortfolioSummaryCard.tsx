import { useEffect, useState } from 'react'
import type { PortfolioSummary } from '../api/client'
import { portfolioApi } from '../api/client'
import { useRefresh } from '../contexts/RefreshContext'
import { formatEur, formatPct, pnlClass } from '../utils/format'

export function PortfolioSummaryCard() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const { lastRefreshAt } = useRefresh()

  useEffect(() => {
    portfolioApi.summary().then(setSummary).catch(() => {})
  }, [lastRefreshAt])

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

  const hasRealized = summary.realized_pnl_eur !== 0 || summary.total_invested_ever_eur > 0

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Valor total"
          value={formatEur(summary.total_value_eur)}
          sub={summary.last_updated ? `Actualizado: ${summary.last_updated}` : 'Sin precios'}
        />
        <StatCard
          label="Invertido (en cartera)"
          value={formatEur(summary.total_invested_eur)}
        />
        <StatCard
          label="Ganancia / Pérdida"
          value={formatEur(summary.total_pnl_eur)}
          sub={formatPct(summary.total_pnl_pct)}
          valueClass={pnlClass(summary.total_pnl_eur)}
        />
      </div>
      {hasRealized && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard
            label="Total invertido (histórico)"
            value={formatEur(summary.total_invested_ever_eur)}
            sub="Incluyendo posiciones cerradas"
            compact
          />
          <StatCard
            label="Ganancia realizada"
            value={formatEur(summary.realized_pnl_eur)}
            sub={formatPct(summary.realized_pnl_pct)}
            valueClass={pnlClass(summary.realized_pnl_eur)}
            compact
          />
          <StatCard
            label="Ganancia realizada (neta)"
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
