import { useEffect, useMemo, useState } from 'react'
import {
  Area, CartesianGrid, ComposedChart, ReferenceDot,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { ChartPoint, Transaction } from '../api/client'
import { portfolioApi, transactionsApi } from '../api/client'
import { useRefresh } from '../contexts/RefreshContext'
import { fmtAxisCcy, formatEur, formatNumber } from '../utils/format'

const INVESTED_COLOR = '#3b82f6'

export function PortfolioChart({ period, dateFrom, dateTo }: { period: string; dateFrom?: string; dateTo?: string }) {
  const [data, setData] = useState<ChartPoint[]>([])
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [showInvested, setShowInvested] = useState(true)
  const { lastRefreshAt } = useRefresh()

  useEffect(() => {
    setLoading(true)
    const params: Record<string, string> = period === 'custom'
      ? { ...(dateFrom && { date_from: dateFrom }), ...(dateTo && { date_to: dateTo }) }
      : { period }
    Promise.all([
      portfolioApi.chart(params),
      transactionsApi.list({ ...params, sort_by: 'date', sort_dir: 'asc' }),
    ])
      .then(([chartData, txs]) => { setData(chartData); setTransactions(txs) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [period, dateFrom, dateTo, lastRefreshAt])

  // Snap a date to the nearest chart point (handles weekends / holidays)
  const snapToChart = (dateStr: string): ChartPoint | null => {
    if (data.length === 0) return null
    const exact = data.find(d => d.date === dateStr)
    if (exact) return exact
    const before = data.filter(d => d.date <= dateStr)
    return before.length > 0 ? before[before.length - 1] : data[0]
  }

  const visibleTransactions = useMemo(() => {
    if (data.length === 0) return []
    return transactions.filter(
      tx => tx.date >= data[0].date && tx.date <= data[data.length - 1].date
    )
  }, [transactions, data])

  // Deduplicate: one dot per snapped chart date, collecting all txs on that date
  const eventDots = useMemo(() => {
    const map = new Map<string, { snap: ChartPoint; txs: Transaction[] }>()
    for (const tx of visibleTransactions) {
      const snap = snapToChart(tx.date)
      if (!snap) continue
      if (!map.has(snap.date)) map.set(snap.date, { snap, txs: [] })
      map.get(snap.date)!.txs.push(tx)
    }
    return Array.from(map.values())
  }, [visibleTransactions, data])

  // Index txs by snapped date so the tooltip can look them up by label
  const eventsByDate = useMemo(() => {
    const m = new Map<string, Transaction[]>()
    for (const { snap, txs } of eventDots) m.set(snap.date, txs)
    return m
  }, [eventDots])

  const isPositive = data.length >= 2
    ? data[data.length - 1].value_eur >= data[0].value_eur
    : true
  const valueColor = isPositive ? '#22c55e' : '#ef4444'
  const hasInvested = data.some(d => d.invested_eur != null)

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Evolución del Portfolio</h2>
        {hasInvested && (
          <button
            onClick={() => setShowInvested(v => !v)}
            className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              showInvested
                ? 'bg-blue-500/10 border-blue-500/40 text-blue-400'
                : 'border-gray-600 text-gray-500 hover:text-gray-300'
            }`}
          >
            {/* mini dashed line icon */}
            <svg width="16" height="8" viewBox="0 0 16 8">
              <line x1="0" y1="4" x2="5" y2="4" stroke={showInvested ? INVESTED_COLOR : '#6b7280'} strokeWidth="2" strokeDasharray="3 2" />
              <line x1="7" y1="4" x2="12" y2="4" stroke={showInvested ? INVESTED_COLOR : '#6b7280'} strokeWidth="2" strokeDasharray="3 2" />
            </svg>
            Invertido
          </button>
        )}
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-gray-400">Cargando...</div>
      ) : data.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
          Sin datos para el período seleccionado
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
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
              tickFormatter={v => fmtAxisCcy(v, 'EUR')}
              width={52}
            />

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
                    {payload.map(entry => (
                      <div key={entry.dataKey as string} className="flex items-center justify-between gap-4 mb-1">
                        <span className="text-gray-400 text-xs">
                          {entry.dataKey === 'value_eur' ? 'Valor' : 'Invertido'}
                        </span>
                        <span style={{ color: entry.color as string }} className="font-semibold">
                          {formatEur(Number(entry.value))}
                        </span>
                      </div>
                    ))}
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

            {/* Invested area — rendered before value so it sits behind */}
            {showInvested && hasInvested && (
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
              dataKey="value_eur"
              stroke={valueColor}
              strokeWidth={2}
              fill="url(#colorValue)"
              dot={false}
              activeDot={{ r: 4, fill: valueColor }}
            />

            {/* Transaction event dots on the value line */}
            {eventDots.map(({ snap, txs }) => {
              const hasBuy = txs.some(t => t.type === 'buy')
              const hasSell = txs.some(t => t.type === 'sell')
              const mixed = hasBuy && hasSell
              const dotColor = mixed ? '#9ca3af' : hasBuy ? '#22c55e' : '#ef4444'
              return (
                <ReferenceDot
                  key={snap.date}
                  x={snap.date}
                  y={snap.value_eur}
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
