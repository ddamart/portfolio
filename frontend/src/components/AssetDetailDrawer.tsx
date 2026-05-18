import { useEffect, useState } from 'react'
import {
  Area, CartesianGrid, ComposedChart, ReferenceDot,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { Asset, AssetPricePoint, Transaction } from '../api/client'
import { assetsApi, transactionsApi } from '../api/client'
import { formatEur, formatNumber } from '../utils/format'
import { AssetLogo } from './AssetLogo'

const PERIODS = [
  { key: '1m', label: '1M' },
  { key: '3m', label: '3M' },
  { key: '6m', label: '6M' },
  { key: '1y', label: '1A' },
  { key: 'all', label: 'Todo' },
]

export function AssetDetailDrawer({ asset, onClose }: { asset: Asset; onClose: () => void }) {
  const [period, setPeriod] = useState('1y')
  const [prices, setPrices] = useState<AssetPricePoint[]>([])
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loadingPrices, setLoadingPrices] = useState(true)
  const [loadingTx, setLoadingTx] = useState(true)

  useEffect(() => {
    setLoadingPrices(true)
    assetsApi.history(asset.id, period)
      .then(setPrices)
      .catch(() => setPrices([]))
      .finally(() => setLoadingPrices(false))
  }, [asset.id, period])

  useEffect(() => {
    setLoadingTx(true)
    transactionsApi.list({ asset_id: String(asset.id), sort_by: 'date', sort_dir: 'asc' })
      .then(setTransactions)
      .catch(() => setTransactions([]))
      .finally(() => setLoadingTx(false))
  }, [asset.id])

  // Snap a transaction date to the nearest available price data point.
  // This handles weekends/holidays where there's no price entry.
  const snapToPrice = (dateStr: string): { date: string; price_eur: number } | null => {
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

  const currentPrice = prices[prices.length - 1]?.price_eur
  const firstPrice = prices[0]?.price_eur
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
                    {formatEur(currentPrice)}
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
            {/* Period tabs */}
            <div className="flex gap-1 mb-3">
              {PERIODS.map(p => (
                <button
                  key={p.key}
                  onClick={() => setPeriod(p.key)}
                  className={`px-3 py-1 text-xs rounded-full font-medium transition-colors ${
                    period === p.key
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>

            {loadingPrices ? (
              <div className="h-52 flex items-center justify-center text-gray-400 text-sm">Cargando…</div>
            ) : prices.length === 0 ? (
              <div className="h-52 flex items-center justify-center text-gray-400 text-sm">
                Sin datos de precio para este período
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <ComposedChart data={prices} margin={{ top: 10, right: 8, left: 0, bottom: 0 }}>
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
                    tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v.toFixed(2))}
                    width={58}
                  />
                  <Tooltip
                    formatter={(v) => [formatEur(Number(v)), 'Precio']}
                    labelFormatter={l => `Fecha: ${l}`}
                    contentStyle={{
                      background: '#1f2937',
                      border: 'none',
                      borderRadius: 8,
                      color: '#f9fafb',
                      fontSize: 12,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="price_eur"
                    stroke={color}
                    strokeWidth={2}
                    fill={`url(#assetGrad${asset.id})`}
                    dot={false}
                    activeDot={{ r: 3, fill: color }}
                  />
                  {visibleTransactions.map(tx => {
                    const snap = snapToPrice(tx.date)
                    if (!snap) return null
                    const isBuy = tx.type === 'buy'
                    return (
                      <ReferenceDot
                        key={tx.id}
                        x={snap.date}
                        y={snap.price_eur}
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

          {/* Transactions table */}
          <div className="px-6 pb-8 mt-2">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              Historial de operaciones ({transactions.length})
            </h3>

            {loadingTx ? (
              <p className="text-sm text-gray-400">Cargando…</p>
            ) : transactions.length === 0 ? (
              <p className="text-sm text-gray-400">Sin transacciones registradas</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-100 dark:border-gray-700">
                      {['Fecha', 'Tipo', 'Particip.', 'Precio', 'Total €', 'Comisión', 'Broker'].map(h => (
                        <th
                          key={h}
                          className="py-2 pr-3 text-left font-medium text-gray-400 uppercase tracking-wide whitespace-nowrap"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...transactions].reverse().map(tx => (
                      <tr
                        key={tx.id}
                        className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/60"
                      >
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
                        <td className="py-2 pr-3 text-gray-700 dark:text-gray-300">
                          {formatNumber(tx.shares)}
                        </td>
                        <td className="py-2 pr-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">
                          {tx.price.toFixed(4)} {tx.currency}
                        </td>
                        <td className="py-2 pr-3 font-medium text-gray-900 dark:text-white whitespace-nowrap">
                          {formatEur(tx.shares * tx.price_eur)}
                        </td>
                        <td className="py-2 pr-3 text-gray-500 whitespace-nowrap">
                          {tx.commission_eur > 0 ? formatEur(tx.commission_eur) : '—'}
                        </td>
                        <td className="py-2 text-gray-500 capitalize whitespace-nowrap">
                          {tx.broker.replace(/_/g, ' ')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
