import { useEffect, useMemo, useState } from 'react'
import {
  Area, CartesianGrid, ComposedChart, ReferenceArea, ReferenceDot,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { ChartPoint, Transaction } from '../api/client'
import { portfolioApi, transactionsApi } from '../api/client'
import { useRefresh } from '../contexts/RefreshContext'
import { fmtAxisCcy, formatEur, formatNumber, formatPct } from '../utils/format'

const INVESTED_COLOR = '#3b82f6'

type ViewMode = 'value' | 'pnl' | 'pnl_pct'

interface Props {
  period: string
  dateFrom?: string
  dateTo?: string
  onRangeSelect?: (from: string, to: string) => void
  broker?: string
  assetType?: string
}

export function PortfolioChart({ period, dateFrom, dateTo, onRangeSelect, broker, assetType }: Props) {
  const [data, setData] = useState<ChartPoint[]>([])
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [showInvested, setShowInvested] = useState(true)
  const [viewMode, setViewMode] = useState<ViewMode>('value')
  const { lastRefreshAt } = useRefresh()

  // Drag-to-select state
  const [dragStart, setDragStart] = useState<string | null>(null)
  const [dragEnd, setDragEnd] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  useEffect(() => {
    setLoading(true)
    const params: Record<string, string> = period === 'custom'
      ? { ...(dateFrom && { date_from: dateFrom }), ...(dateTo && { date_to: dateTo }) }
      : { period }
    if (broker) params.broker = broker
    if (assetType) params.asset_type = assetType
    Promise.all([
      portfolioApi.chart(params),
      transactionsApi.list({ ...params, sort_by: 'date', sort_dir: 'asc' }),
    ])
      .then(([chartData, txs]) => { setData(chartData); setTransactions(txs) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [period, dateFrom, dateTo, broker, assetType, lastRefreshAt])

  const displayData = useMemo(() => {
    return data.map(d => {
      if (viewMode === 'value') return { ...d, display_y: d.value_eur }
      if (d.invested_eur == null) return { ...d, display_y: null as number | null }
      const pnl = d.value_eur - d.invested_eur
      if (viewMode === 'pnl') return { ...d, display_y: pnl }
      const pct = d.invested_eur > 0 ? (pnl / d.invested_eur) * 100 : 0
      return { ...d, display_y: pct }
    })
  }, [data, viewMode])

  const snapToDisplay = (dateStr: string) => {
    if (displayData.length === 0) return null
    const exact = displayData.find(d => d.date === dateStr)
    if (exact) return exact
    const before = displayData.filter(d => d.date <= dateStr)
    return before.length > 0 ? before[before.length - 1] : displayData[0]
  }

  const visibleTransactions = useMemo(() => {
    if (displayData.length === 0) return []
    return transactions.filter(
      tx => tx.date >= displayData[0].date && tx.date <= displayData[displayData.length - 1].date
    )
  }, [transactions, displayData])

  const eventDots = useMemo(() => {
    const map = new Map<string, { snap: typeof displayData[0]; txs: Transaction[] }>()
    for (const tx of visibleTransactions) {
      const snap = snapToDisplay(tx.date)
      if (!snap) continue
      if (!map.has(snap.date)) map.set(snap.date, { snap, txs: [] })
      map.get(snap.date)!.txs.push(tx)
    }
    return Array.from(map.values())
  }, [visibleTransactions, displayData])

  const eventsByDate = useMemo(() => {
    const m = new Map<string, Transaction[]>()
    for (const { snap, txs } of eventDots) m.set(snap.date, txs)
    return m
  }, [eventDots])

  const lastY = displayData.length >= 2 ? displayData[displayData.length - 1].display_y : null
  const firstY = displayData.length >= 2 ? displayData[0].display_y : null
  const isPositive = lastY != null && firstY != null ? lastY >= firstY : true
  const valueColor = isPositive ? '#22c55e' : '#ef4444'
  const hasInvested = data.some(d => d.invested_eur != null)

  const yFormatter = viewMode === 'pnl_pct'
    ? (v: number) => `${v.toFixed(1)}%`
    : (v: number) => fmtAxisCcy(v, 'EUR')

  const VIEW_MODES: { key: ViewMode; label: string }[] = [
    { key: 'value',   label: 'Valor' },
    { key: 'pnl',     label: 'G/P €' },
    { key: 'pnl_pct', label: 'G/P %' },
  ]

  // Drag handlers — only active when onRangeSelect is wired
  const handleMouseDown = (e: any) => {
    if (!onRangeSelect || !e?.activeLabel) return
    setDragStart(e.activeLabel)
    setDragEnd(e.activeLabel)
    setIsDragging(true)
  }

  const handleMouseMove = (e: any) => {
    if (!isDragging || !e?.activeLabel) return
    setDragEnd(e.activeLabel)
  }

  const handleMouseUp = (e: any) => {
    if (!isDragging || !dragStart) { setIsDragging(false); return }
    const end = e?.activeLabel ?? dragEnd ?? dragStart
    const from = dragStart <= end ? dragStart : end
    const to   = dragStart <= end ? end : dragStart
    setDragStart(null)
    setDragEnd(null)
    setIsDragging(false)
    if (from !== to) onRangeSelect?.(from, to)
  }

  const handleMouseLeave = () => {
    if (isDragging) {
      setDragStart(null); setDragEnd(null); setIsDragging(false)
    }
  }

  const selX1 = dragStart && dragEnd ? (dragStart <= dragEnd ? dragStart : dragEnd) : null
  const selX2 = dragStart && dragEnd ? (dragStart <= dragEnd ? dragEnd : dragStart) : null

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Evolución del Portfolio</h2>
          {onRangeSelect && (
            <span className="text-xs text-gray-400 dark:text-gray-500">· arrastra para filtrar</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden text-xs font-medium">
            {VIEW_MODES.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setViewMode(key)}
                className={`px-3 py-1.5 transition-colors ${
                  viewMode === key
                    ? 'bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {viewMode === 'value' && hasInvested && (
            <button
              onClick={() => setShowInvested(v => !v)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                showInvested
                  ? 'bg-blue-500/10 border-blue-500/40 text-blue-400'
                  : 'border-gray-200 dark:border-gray-700 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              <svg width="16" height="8" viewBox="0 0 16 8">
                <line x1="0" y1="4" x2="5" y2="4" stroke={showInvested ? INVESTED_COLOR : '#6b7280'} strokeWidth="2" strokeDasharray="3 2" />
                <line x1="7" y1="4" x2="12" y2="4" stroke={showInvested ? INVESTED_COLOR : '#6b7280'} strokeWidth="2" strokeDasharray="3 2" />
              </svg>
              Invertido
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-gray-400">Cargando...</div>
      ) : displayData.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
          Sin datos para el período seleccionado
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart
            data={displayData}
            margin={{ top: 8, right: 4, left: 0, bottom: 0 }}
            style={{ cursor: onRangeSelect ? (isDragging ? 'col-resize' : 'crosshair') : 'default' }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseLeave}
          >
            <defs>
              <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={valueColor} stopOpacity={0.18} />
                <stop offset="95%" stopColor={valueColor} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorInvested" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={INVESTED_COLOR} stopOpacity={0.22} />
                <stop offset="95%" stopColor={INVESTED_COLOR} stopOpacity={0.04} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="#374151" strokeOpacity={0.4} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: '#9ca3af' }}
              tickFormatter={d => d.slice(5)}
            />
            <YAxis
              tick={{ fontSize: 12, fill: '#9ca3af' }}
              tickFormatter={yFormatter}
              width={52}
            />

            {/* Suppress tooltip while dragging to keep the UI clean */}
            {!isDragging && (
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null
                  const events = eventsByDate.get(label as string) ?? []
                  return (
                    <div style={{
                      background: '#1f2937', borderRadius: 8,
                      padding: '10px 14px', fontSize: 13, color: '#f9fafb', minWidth: 190,
                    }}>
                      <div className="mb-2 text-gray-400 text-xs">{label as string}</div>
                      {payload.map(entry => {
                        const key = entry.dataKey as string
                        const val = Number(entry.value)
                        let tooltipLabel = 'Valor'
                        let formatted = formatEur(val)
                        if (key === 'display_y') {
                          if (viewMode === 'pnl') { tooltipLabel = 'Beneficio'; formatted = formatEur(val) }
                          else if (viewMode === 'pnl_pct') { tooltipLabel = 'Beneficio'; formatted = formatPct(val) }
                        } else if (key === 'invested_eur') {
                          tooltipLabel = 'Invertido'
                        }
                        return (
                          <div key={key} className="flex items-center justify-between gap-4 mb-1">
                            <span className="text-gray-400 text-xs">{tooltipLabel}</span>
                            <span style={{ color: entry.color as string }} className="font-semibold">
                              {formatted}
                            </span>
                          </div>
                        )
                      })}
                      {events.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-gray-600 space-y-1.5">
                          {events.map(tx => (
                            <div key={tx.id} className="flex items-center gap-2 text-xs">
                              <span className={`shrink-0 px-1.5 py-0.5 rounded font-bold ${
                                tx.type === 'buy' ? 'bg-green-900/60 text-green-400' : 'bg-red-900/60 text-red-400'
                              }`}>
                                {tx.type === 'buy' ? 'Compra' : 'Venta'}
                              </span>
                              <span className="font-mono text-gray-300">{tx.asset_ticker}</span>
                              <span className="text-gray-400 ml-auto">
                                {formatNumber(tx.shares, 3)} × {formatEur(tx.price_eur)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                }}
              />
            )}

            {viewMode === 'value' && showInvested && hasInvested && (
              <Area
                type="stepAfter"
                dataKey="invested_eur"
                stroke={INVESTED_COLOR}
                strokeWidth={1.5}
                strokeDasharray="5 3"
                fill="url(#colorInvested)"
                dot={false}
                activeDot={{ r: 3, fill: INVESTED_COLOR }}
              />
            )}

            <Area
              type="monotone"
              dataKey="display_y"
              stroke={valueColor}
              strokeWidth={2}
              fill="url(#colorValue)"
              dot={false}
              activeDot={{ r: 4, fill: valueColor }}
            />

            {/* Drag selection highlight */}
            {isDragging && selX1 && selX2 && (
              <ReferenceArea
                x1={selX1}
                x2={selX2}
                fill="#6366f1"
                fillOpacity={0.15}
                stroke="#6366f1"
                strokeOpacity={0.4}
                strokeWidth={1}
              />
            )}

            {eventDots.map(({ snap, txs }) => {
              if (snap.display_y == null) return null
              const hasBuy = txs.some(t => t.type === 'buy')
              const hasSell = txs.some(t => t.type === 'sell')
              const mixed = hasBuy && hasSell
              const dotColor = mixed ? '#9ca3af' : hasBuy ? '#22c55e' : '#ef4444'
              return (
                <ReferenceDot
                  key={snap.date}
                  x={snap.date}
                  y={snap.display_y}
                  r={5}
                  fill={dotColor}
                  stroke="#111827"
                  strokeWidth={1.5}
                  label={mixed ? undefined : {
                    value: hasBuy ? 'C' : 'V',
                    position: 'top',
                    fontSize: 9,
                    fontWeight: 700,
                    fill: dotColor,
                  }}
                />
              )
            })}
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
