import { useEffect, useState } from 'react'
import {
  Area, CartesianGrid, ComposedChart, ReferenceArea, ReferenceDot,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { Asset, AssetPricePoint, Transaction } from '../api/client'
import { assetsApi, transactionsApi } from '../api/client'
import { fmtAxisCcy, formatCcy, formatEur, formatNumber } from '../utils/format'
import { getPeriodParams } from '../utils/period'
import { AssetLogo } from './AssetLogo'
import { PeriodFilter } from './PeriodFilter'
import { PriceImportModal } from './PriceImportModal'

function Paginator({ page, totalPages, total, onChange, pageSize, onPageSize }: {
  page: number; totalPages: number; total: number; onChange: (p: number) => void
  pageSize?: number; onPageSize?: (n: number) => void
}) {
  if (totalPages <= 1 && !onPageSize) return null
  return (
    <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
      <span>{total} registros · página {page + 1} de {Math.max(totalPages, 1)}</span>
      <div className="flex items-center gap-2">
        {onPageSize && pageSize !== undefined && (
          <select
            value={pageSize}
            onChange={e => { onPageSize(Number(e.target.value)) }}
            className="px-1.5 py-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 focus:outline-none"
          >
            {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n} / pág.</option>)}
          </select>
        )}
        {totalPages > 1 && (
          <div className="flex gap-1">
            <button
              onClick={() => onChange(page - 1)}
              disabled={page === 0}
              className="px-2 py-1 rounded border border-gray-200 dark:border-gray-700 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              ‹
            </button>
            <button
              onClick={() => onChange(page + 1)}
              disabled={page >= totalPages - 1}
              className="px-2 py-1 rounded border border-gray-200 dark:border-gray-700 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              ›
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export function AssetDetailDrawer({ asset, onClose }: { asset: Asset; onClose: () => void }) {
  const [period, setPeriod] = useState('ytd')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [prices, setPrices] = useState<AssetPricePoint[]>([])
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loadingPrices, setLoadingPrices] = useState(true)
  const [loadingTx, setLoadingTx] = useState(true)
  const [tab, setTab] = useState<'operaciones' | 'precios'>('operaciones')
  const [showImport, setShowImport] = useState(false)
  const [txPage, setTxPage] = useState(0)
  const [pricePage, setPricePage] = useState(0)
  const [pricePageSize, setPricePageSize] = useState(20)

  // Drag-to-zoom state
  const [dragStart, setDragStart] = useState<string | null>(null)
  const [dragEnd, setDragEnd] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  const TX_PAGE_SIZE = 10

  useEffect(() => {
    setLoadingPrices(true)
    setPricePage(0)
    const params = getPeriodParams(period, dateFrom, dateTo)
    assetsApi.history(asset.id, params)
      .then(setPrices)
      .catch(() => setPrices([]))
      .finally(() => setLoadingPrices(false))
  }, [asset.id, period, dateFrom, dateTo])

  useEffect(() => {
    setLoadingTx(true)
    transactionsApi.list({ asset_id: String(asset.id), sort_by: 'date', sort_dir: 'asc' })
      .then(setTransactions)
      .catch(() => setTransactions([]))
      .finally(() => setLoadingTx(false))
  }, [asset.id])

  const handleDateRange = (from: string, to: string) => {
    setDateFrom(from)
    setDateTo(to)
  }

  // Drag handlers
  const handleMouseDown = (e: any) => {
    if (!e?.activeLabel) return
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
    if (from !== to) {
      setDateFrom(from)
      setDateTo(to)
      setPeriod('custom')
    }
  }

  const handleMouseLeave = () => {
    if (isDragging) { setDragStart(null); setDragEnd(null); setIsDragging(false) }
  }

  const selX1 = dragStart && dragEnd ? (dragStart <= dragEnd ? dragStart : dragEnd) : null
  const selX2 = dragStart && dragEnd ? (dragStart <= dragEnd ? dragEnd : dragStart) : null

  // Snap a transaction date to the nearest available price data point.
  const snapToPrice = (dateStr: string): AssetPricePoint | null => {
    if (prices.length === 0) return null
    const exact = prices.find(p => p.date === dateStr)
    if (exact) return exact
    const before = prices.filter(p => p.date <= dateStr)
    if (before.length > 0) return before[before.length - 1]
    return prices[0]
  }

  const visibleTransactions = transactions.filter(tx =>
    prices.length > 0 &&
    tx.date >= prices[0].date &&
    tx.date <= prices[prices.length - 1].date
  )

  const currency = prices[0]?.currency ?? asset.currency
  const currentPrice = prices[prices.length - 1]?.price
  const firstPrice = prices[0]?.price
  const isPositive = currentPrice != null && firstPrice != null ? currentPrice >= firstPrice : true
  const color = isPositive ? '#22c55e' : '#ef4444'
  const changePct =
    currentPrice != null && firstPrice != null && firstPrice !== 0
      ? ((currentPrice - firstPrice) / firstPrice) * 100
      : null

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/40 z-40" onClick={onClose} />

      {/* Drawer */}
      <div className="fixed top-0 right-0 h-full w-full max-w-2xl bg-white dark:bg-gray-900 shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <AssetLogo asset={asset} className="w-10 h-10" />
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-gray-900 dark:text-white">{asset.name}</span>
                <span className="text-xs text-gray-400 font-mono shrink-0">{asset.ticker}</span>
                {asset.isin && (
                  <span className="text-xs text-gray-400 font-mono shrink-0">{asset.isin}</span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                {currentPrice != null && (
                  <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                    {formatCcy(currentPrice, currency)}
                  </span>
                )}
                {changePct != null && (
                  <span className={`text-xs font-medium ${changePct >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                    {changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}% en el período
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="ml-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-2xl leading-none shrink-0"
          >
            ×
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto">
          {/* Chart section */}
          <div className="px-6 pt-4 pb-2">
            {/* Period filter + drag hint */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <PeriodFilter
                value={period}
                onChange={setPeriod}
                dateFrom={dateFrom}
                dateTo={dateTo}
                onDateRange={handleDateRange}
              />
              <span className="text-xs text-gray-400 dark:text-gray-500">· arrastra para filtrar</span>
            </div>

            {loadingPrices ? (
              <div className="h-52 flex items-center justify-center text-gray-400 text-sm">Cargando…</div>
            ) : prices.length === 0 ? (
              <div className="h-52 flex items-center justify-center text-gray-400 text-sm">
                Sin datos de precio para este período
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <ComposedChart
                  data={prices}
                  margin={{ top: 10, right: 8, left: 0, bottom: 0 }}
                  style={{ cursor: isDragging ? 'col-resize' : 'crosshair' }}
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={handleMouseUp}
                  onMouseLeave={handleMouseLeave}
                >
                  <defs>
                    <linearGradient id={`assetGrad${asset.id}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={color} stopOpacity={0.18} />
                      <stop offset="95%" stopColor={color} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                    tickFormatter={d => d.slice(5)}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                    tickFormatter={v => fmtAxisCcy(v, currency)}
                    width={64}
                  />
                  {!isDragging && (
                    <Tooltip
                      formatter={(v) => [formatCcy(Number(v), currency), 'Precio']}
                      labelFormatter={l => `Fecha: ${l}`}
                      contentStyle={{
                        background: '#1f2937',
                        border: 'none',
                        borderRadius: 8,
                        color: '#f9fafb',
                        fontSize: 12,
                      }}
                    />
                  )}
                  <Area
                    type="monotone"
                    dataKey="price"
                    stroke={color}
                    strokeWidth={2}
                    fill={`url(#assetGrad${asset.id})`}
                    dot={false}
                    activeDot={{ r: 3, fill: color }}
                  />
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
                  {visibleTransactions.map(tx => {
                    const snap = snapToPrice(tx.date)
                    if (!snap) return null
                    const isBuy = tx.type === 'buy'
                    return (
                      <ReferenceDot
                        key={tx.id}
                        x={snap.date}
                        y={snap.price}
                        r={5}
                        fill={isBuy ? '#22c55e' : '#ef4444'}
                        stroke="white"
                        strokeWidth={2}
                        label={{
                          value: isBuy ? 'C' : 'V',
                          position: isBuy ? 'top' : 'bottom',
                          fontSize: 9,
                          fontWeight: 700,
                          fill: isBuy ? '#16a34a' : '#dc2626',
                        }}
                      />
                    )
                  })}
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Legend */}
          {!loadingPrices && prices.length > 0 && visibleTransactions.length > 0 && (
            <div className="px-6 pb-2 flex gap-4 text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500" />
                Compra
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-500" />
                Venta
              </span>
            </div>
          )}

          {/* Tabs */}
          <div className="px-6 pb-8 mt-2">
            <div className="flex items-center justify-between mb-3">
              <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
                <button
                  onClick={() => setTab('operaciones')}
                  className={`px-3 py-1.5 text-xs rounded-md font-medium transition-colors ${
                    tab === 'operaciones'
                      ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700'
                  }`}
                >
                  Operaciones ({transactions.length})
                </button>
                <button
                  onClick={() => setTab('precios')}
                  className={`px-3 py-1.5 text-xs rounded-md font-medium transition-colors ${
                    tab === 'precios'
                      ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700'
                  }`}
                >
                  Precios ({prices.length})
                </button>
              </div>
              {tab === 'precios' && asset.manual_price && (
                <button
                  onClick={() => setShowImport(true)}
                  className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  + Importar CSV
                </button>
              )}
            </div>

            {tab === 'operaciones' && (
              loadingTx ? (
                <p className="text-sm text-gray-400">Cargando…</p>
              ) : transactions.length === 0 ? (
                <p className="text-sm text-gray-400">Sin transacciones registradas</p>
              ) : (() => {
                const sorted = [...transactions].reverse()
                const totalPages = Math.ceil(sorted.length / TX_PAGE_SIZE)
                const page = sorted.slice(txPage * TX_PAGE_SIZE, (txPage + 1) * TX_PAGE_SIZE)
                return (
                  <>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-gray-100 dark:border-gray-700">
                            {['Fecha', 'Tipo', 'Particip.', 'Precio', 'Total €', 'Comisión', 'Broker'].map(h => (
                              <th key={h} className="py-2 pr-3 text-left font-medium text-gray-400 uppercase tracking-wide whitespace-nowrap">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {page.map(tx => (
                            <tr key={tx.id} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/60">
                              <td className="py-2 pr-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{tx.date}</td>
                              <td className="py-2 pr-3">
                                <span className={`px-1.5 py-0.5 rounded font-semibold text-[10px] ${
                                  tx.type === 'buy'
                                    ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400'
                                    : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400'
                                }`}>
                                  {tx.type === 'buy' ? 'COMPRA' : 'VENTA'}
                                </span>
                              </td>
                              <td className="py-2 pr-3 text-gray-700 dark:text-gray-300">{formatNumber(tx.shares)}</td>
                              <td className="py-2 pr-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">{tx.price.toFixed(4)} {tx.currency}</td>
                              <td className="py-2 pr-3 font-medium text-gray-900 dark:text-white whitespace-nowrap">{formatEur(tx.shares * tx.price_eur)}</td>
                              <td className="py-2 pr-3 text-gray-500 whitespace-nowrap">{tx.commission_eur > 0 ? formatEur(tx.commission_eur) : '—'}</td>
                              <td className="py-2 text-gray-500 capitalize whitespace-nowrap">{tx.broker.replace(/_/g, ' ')}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <Paginator page={txPage} totalPages={totalPages} total={sorted.length} onChange={setTxPage} />
                  </>
                )
              })()
            )}

            {tab === 'precios' && (
              loadingPrices ? (
                <p className="text-sm text-gray-400">Cargando…</p>
              ) : prices.length === 0 ? (
                <p className="text-sm text-gray-400">Sin datos de precio para el período seleccionado</p>
              ) : (() => {
                const sorted = [...prices].reverse()
                const totalPages = Math.ceil(sorted.length / pricePageSize)
                const page = sorted.slice(pricePage * pricePageSize, (pricePage + 1) * pricePageSize)
                return (
                  <>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-gray-100 dark:border-gray-700">
                            {['Fecha', `Precio (${prices[0]?.currency ?? asset.currency})`, 'Precio (€)'].map(h => (
                              <th key={h} className="py-2 pr-3 text-left font-medium text-gray-400 uppercase tracking-wide whitespace-nowrap">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {page.map(p => (
                            <tr key={p.date} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/60">
                              <td className="py-2 pr-3 text-gray-600 dark:text-gray-400 whitespace-nowrap font-mono">{p.date}</td>
                              <td className="py-2 pr-3 text-gray-700 dark:text-gray-300">{formatNumber(p.price, 4)}</td>
                              <td className="py-2 pr-3 text-gray-700 dark:text-gray-300">{formatEur(p.price_eur)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <Paginator
                      page={pricePage}
                      totalPages={totalPages}
                      total={sorted.length}
                      onChange={setPricePage}
                      pageSize={pricePageSize}
                      onPageSize={n => { setPricePageSize(n); setPricePage(0) }}
                    />
                  </>
                )
              })()
            )}
          </div>
        </div>
      </div>

      {showImport && (
        <PriceImportModal
          asset={asset}
          onClose={() => setShowImport(false)}
          onSaved={() => {
            setShowImport(false)
            setLoadingPrices(true)
            const params = getPeriodParams(period, dateFrom, dateTo)
            assetsApi.history(asset.id, params).then(setPrices).finally(() => setLoadingPrices(false))
          }}
        />
      )}
    </>
  )
}
