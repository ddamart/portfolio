import { useEffect, useState } from 'react'
import type { PortfolioSummary } from '../api/client'
import { portfolioApi } from '../api/client'
import { formatEur, formatPct, pnlClass } from '../utils/format'

export function PortfolioSummaryCard() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)

  useEffect(() => {
    portfolioApi.summary().then(setSummary).catch(() => {})
  }, [])

  if (!summary) {
    return (
      <div className="grid grid-cols-3 gap-4 animate-pulse">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-24 bg-gray-100 dark:bg-gray-800 rounded-xl" />
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <StatCard
        label="Valor total"
        value={formatEur(summary.total_value_eur)}
        sub={summary.last_updated ? `Actualizado: ${summary.last_updated}` : 'Sin precios'}
      />
      <StatCard
        label="Invertido"
        value={formatEur(summary.total_invested_eur)}
      />
      <StatCard
        label="Ganancia / Pérdida"
        value={formatEur(summary.total_pnl_eur)}
        sub={formatPct(summary.total_pnl_pct)}
        valueClass={pnlClass(summary.total_pnl_eur)}
      />
    </div>
  )
}

function StatCard({
  label, value, sub, valueClass = '',
}: { label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">{label}</p>
      <p className={`text-2xl font-bold text-gray-900 dark:text-white ${valueClass}`}>{value}</p>
      {sub && <p className={`text-sm mt-0.5 ${valueClass || 'text-gray-400'}`}>{sub}</p>}
    </div>
  )
}
