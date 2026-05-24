import { useEffect, useState } from 'react'
import type { RealizedSale } from '../api/client'
import { portfolioApi } from '../api/client'
import { formatEur, formatPct, formatNumber, pnlClass } from '../utils/format'
import { getPeriodParams } from '../utils/period'

interface Props {
  open: boolean
  onClose: () => void
  period: string
  dateFrom: string
  dateTo: string
  broker?: string
  assetType?: string
}

const ASSET_TYPE_LABEL: Record<string, string> = {
  stock: 'Stock', etf: 'ETF', fund: 'Fondo',
}
const BROKER_LABEL: Record<string, string> = {
  openbank: 'Openbank', trade_republic: 'Trade Republic',
  revolut: 'Revolut', degiro: 'Degiro',
}

export function RealizedSalesModal({ open, onClose, period, dateFrom, dateTo, broker, assetType }: Props) {
  const [sales, setSales] = useState<RealizedSale[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    const params = getPeriodParams(period, dateFrom, dateTo)
    if (broker) params.broker = broker
    if (assetType) params.asset_type = assetType
    portfolioApi.realizedSales(params)
      .then(d => { setSales(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [open, period, dateFrom, dateTo, broker, assetType])

  if (!open) return null

  const totalPnl = sales.reduce((s, r) => s + r.realized_pnl_eur, 0)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative z-10 bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-3xl max-h-[80vh] flex flex-col mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">G/P Realizada — detalle de ventas</h2>
            {sales.length > 0 && (
              <p className="text-sm text-gray-500 mt-0.5">
                {sales.length} venta{sales.length !== 1 ? 's' : ''} ·{' '}
                <span className={pnlClass(totalPnl)}>{formatEur(totalPnl)}</span>
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="overflow-auto flex-1 px-6 py-4">
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : sales.length === 0 ? (
            <p className="text-center text-gray-400 py-12">No hay ventas en este período</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide border-b border-gray-200 dark:border-gray-700">
                  <th className="pb-2 pr-3">Fecha</th>
                  <th className="pb-2 pr-3">Activo</th>
                  <th className="pb-2 pr-3">Tipo</th>
                  <th className="pb-2 pr-3">Broker</th>
                  <th className="pb-2 pr-3 text-right">Participaciones</th>
                  <th className="pb-2 pr-3 text-right">P. Venta</th>
                  <th className="pb-2 pr-3 text-right">Base Coste</th>
                  <th className="pb-2 text-right">G/P</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {sales.map((s, i) => {
                  const c = pnlClass(s.realized_pnl_eur)
                  return (
                    <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                      <td className="py-2 pr-3 text-gray-500 font-mono text-xs">{s.date}</td>
                      <td className="py-2 pr-3">
                        <span className="font-medium text-gray-900 dark:text-white">{s.asset_name}</span>
                        <span className="ml-1 text-xs text-gray-400 font-mono">{s.ticker}</span>
                      </td>
                      <td className="py-2 pr-3">
                        <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                          {ASSET_TYPE_LABEL[s.asset_type] ?? s.asset_type}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-xs text-gray-500">
                        {s.broker ? (BROKER_LABEL[s.broker] ?? s.broker) : '—'}
                      </td>
                      <td className="py-2 pr-3 text-right font-mono">{formatNumber(s.shares)}</td>
                      <td className="py-2 pr-3 text-right font-mono">{formatEur(s.price_eur)}</td>
                      <td className="py-2 pr-3 text-right font-mono text-gray-500">{formatEur(s.cost_basis_eur)}</td>
                      <td className="py-2 text-right">
                        <span className={`font-semibold ${c}`}>{formatEur(s.realized_pnl_eur)}</span>
                        <br />
                        <span className={`text-xs ${c}`}>{formatPct(s.realized_pnl_pct)}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
