import { useEffect, useState } from 'react'
import type { PortfolioSummary } from '../api/client'
import { portfolioApi } from '../api/client'
import { useRefresh } from '../contexts/RefreshContext'
import { formatEur, formatPct, pnlClass } from '../utils/format'
import { RealizedSalesModal } from './RealizedSalesModal'
import { getPeriodParams } from '../utils/period'

interface Props {
  period: string
  dateFrom: string
  dateTo: string
  broker?: string
  assetType?: string
}

export function PortfolioSummaryCard({ period, dateFrom, dateTo, broker, assetType }: Props) {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [showSalesModal, setShowSalesModal] = useState(false)
  const { lastRefreshAt } = useRefresh()

  useEffect(() => {
    const params = getPeriodParams(period, dateFrom, dateTo)
    if (broker) params.broker = broker
    if (assetType) params.asset_type = assetType
    portfolioApi.summary(params).then(setSummary).catch(() => {})
  }, [period, dateFrom, dateTo, broker, assetType, lastRefreshAt])

  if (!summary) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 animate-pulse">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-20 bg-gray-100 dark:bg-gray-800 rounded-xl" />
        ))}
      </div>
    )
  }

  // ── G/P no realizada (period-scoped cambio sum) ───────────────────────────
  const unrealizedEur = summary.unrealized_cambio_eur ?? summary.total_pnl_eur
  const unrealizedPct = summary.unrealized_cambio_pct ?? summary.total_pnl_pct

  // ── Rendimiento total (all-time unrealized + all-time realized) ───────────
  const rendimientoEur = summary.rendimiento_total_eur ?? summary.total_pnl_eur
  const rendimientoPct = summary.rendimiento_total_pct ?? summary.total_pnl_pct

  // ── Cambio total (period G/P no realizada + period G/P realizada) ─────────
  const cambioEur = summary.cambio_total_eur ?? rendimientoEur
  const cambioPct = summary.cambio_total_pct ?? rendimientoPct

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {/* Row 1 */}
        <StatCard
          label="Valor total"
          value={formatEur(summary.total_value_eur)}
          sub={summary.last_updated ? `Actualizado: ${summary.last_updated}` : 'Sin precios'}
        />
        <StatCard
          label="G/P no realizada"
          value={formatEur(unrealizedEur)}
          sub={formatPct(unrealizedPct)}
          valueClass={pnlClass(unrealizedEur)}
          subClass={pnlClass(unrealizedEur)}
        />

        {/* Row 2 */}
        <StatCard
          label="Total invertido"
          value={formatEur(summary.total_invested_eur)}
        />
        <ClickableCard
          label="G/P realizada"
          value={formatEur(summary.realized_pnl_eur)}
          sub={formatPct(summary.realized_pnl_pct)}
          valueClass={pnlClass(summary.realized_pnl_eur)}
          subClass={pnlClass(summary.realized_pnl_eur)}
          onClick={() => setShowSalesModal(true)}
          hint="Ver detalle"
        />

        {/* Row 3 */}
        <StatCard
          label="Rendimiento total"
          value={formatEur(rendimientoEur)}
          sub={formatPct(rendimientoPct)}
          valueClass={pnlClass(rendimientoEur)}
          subClass={pnlClass(rendimientoEur)}
        />
        <StatCard
          label="Cambio"
          value={formatEur(cambioEur)}
          sub={cambioPct != null ? formatPct(cambioPct) : undefined}
          valueClass={pnlClass(cambioEur)}
          subClass={pnlClass(cambioEur)}
        />
      </div>

      <RealizedSalesModal
        open={showSalesModal}
        onClose={() => setShowSalesModal(false)}
        period={period}
        dateFrom={dateFrom}
        dateTo={dateTo}
        broker={broker}
        assetType={assetType}
      />
    </>
  )
}

// ── StatCard ──────────────────────────────────────────────────────────────────

function StatCard({
  label, value, sub, valueClass = '', subClass = '',
}: {
  label: string; value: string; sub?: string
  valueClass?: string; subClass?: string
}) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">{label}</p>
      <p className={`text-xl font-bold text-gray-900 dark:text-white ${valueClass}`}>{value}</p>
      {sub && <p className={`text-sm mt-0.5 ${subClass || 'text-gray-400'}`}>{sub}</p>}
    </div>
  )
}

// ── ClickableCard ─────────────────────────────────────────────────────────────

function ClickableCard({
  label, value, sub, valueClass = '', subClass = '', onClick, hint,
}: {
  label: string; value: string; sub?: string
  valueClass?: string; subClass?: string
  onClick: () => void; hint?: string
}) {
  return (
    <button
      onClick={onClick}
      className="text-left bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 hover:border-blue-400 dark:hover:border-blue-500 hover:shadow-sm transition-all group"
    >
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">{label}</p>
        {hint && (
          <span className="text-xs text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity">
            {hint} →
          </span>
        )}
      </div>
      <p className={`text-xl font-bold text-gray-900 dark:text-white ${valueClass}`}>{value}</p>
      {sub && <p className={`text-sm mt-0.5 ${subClass || 'text-gray-400'}`}>{sub}</p>}
    </button>
  )
}
