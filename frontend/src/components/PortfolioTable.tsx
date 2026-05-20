import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import type { SortingState } from '@tanstack/react-table'
import { useEffect, useMemo, useState } from 'react'
import type { HoldingRow } from '../api/client'
import { portfolioApi } from '../api/client'
import { useRefresh } from '../contexts/RefreshContext'
import { formatEur, formatNumber, formatPct, pnlClass, pnlClassMuted } from '../utils/format'
import { AssetLogo } from './AssetLogo'
import { ManualPriceModal } from './ManualPriceModal'

const col = createColumnHelper<HoldingRow>()

const BROKER_LABEL: Record<string, string> = {
  openbank: 'Openbank',
  trade_republic: 'Trade Republic',
  revolut: 'Revolut',
  degiro: 'Degiro',
}

export function PortfolioTable({ period, dateFrom, dateTo }: { period: string; dateFrom?: string; dateTo?: string }) {
  const [holdings, setHoldings] = useState<HoldingRow[]>([])
  const [loading, setLoading] = useState(true)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'value_eur', desc: true }])
  const [manualPriceAsset, setManualPriceAsset] = useState<HoldingRow | null>(null)
  const { lastRefreshAt } = useRefresh()

  const hasPeriod = period !== 'all'

  const load = () => {
    setLoading(true)
    const params: Record<string, string> = period === 'custom'
      ? { ...(dateFrom && { date_from: dateFrom }), ...(dateTo && { date_to: dateTo }) }
      : { period }
    portfolioApi.holdings(params).then(d => {
      setHoldings(d)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  useEffect(() => { load() }, [period, dateFrom, dateTo, lastRefreshAt])

  const columns = useMemo(() => [
    col.accessor('name', {
      header: 'Activo',
      cell: info => (
        <div className="flex items-center gap-2">
          <AssetLogo asset={info.row.original} className="w-7 h-7" />
          <div>
            <div className="flex items-center gap-1">
              <span className="font-medium text-gray-900 dark:text-white">{info.getValue()}</span>
              {info.row.original.manual_price && (
                <span title="Precio manual" className="text-xs text-amber-500">✎</span>
              )}
            </div>
            <span className="text-xs font-mono text-gray-400">{info.row.original.ticker}</span>
          </div>
        </div>
      ),
    }),
    col.accessor('type', {
      header: 'Tipo',
      cell: info => (
        <span className="capitalize text-sm px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
          {info.getValue()}
        </span>
      ),
    }),
    col.accessor('broker', {
      header: 'Broker',
      cell: info => {
        const v = info.getValue()
        if (!v) return <span className="text-gray-400">—</span>
        const labels = v.split(', ').map(b => BROKER_LABEL[b] ?? b).join(', ')
        return <span className="text-xs text-gray-500">{labels}</span>
      },
    }),
    col.accessor('total_shares', {
      header: 'Cantidad',
      cell: info => (
        <span>{formatNumber(info.getValue())} <span className="text-gray-400 text-xs">{info.row.original.ticker}</span></span>
      ),
    }),
    col.accessor('avg_buy_price_eur', {
      header: 'P. Medio',
      cell: info => {
        const row = info.row.original
        const isEur = row.currency === 'EUR'
        if (hasPeriod) {
          if (row.period_avg_price_eur == null)
            return <span className="text-gray-400">—</span>
          return (
            <div>
              <div>{formatEur(row.period_avg_price_eur)}</div>
            </div>
          )
        }
        return (
          <div>
            <div>{formatNumber(row.avg_buy_price, 4)} {row.currency}</div>
            {!isEur && <div className="text-xs text-gray-400">{formatEur(info.getValue())}</div>}
          </div>
        )
      },
    }),
    col.accessor('current_price_eur', {
      header: 'P. Actual',
      cell: info => {
        const row = info.row.original
        if (row.current_price == null) return <span className="text-amber-500 text-xs" title="Sin datos de precio. Actualiza el precio desde Activos.">Sin precio</span>
        const isEur = row.currency === 'EUR'
        return (
          <div>
            <div>{formatNumber(row.current_price, 4)} {row.currency}</div>
            {!isEur && info.getValue() != null && <div className="text-xs text-gray-400">{formatEur(info.getValue()!)}</div>}
          </div>
        )
      },
    }),
    col.display({
      id: 'total_invested',
      header: 'Invertido',
      cell: info => {
        const row = info.row.original
        const isEur = row.currency === 'EUR'
        if (hasPeriod) {
          if (row.period_invested_eur == null)
            return <span className="text-gray-400">—</span>
          return <div className="font-medium">{formatEur(row.period_invested_eur)}</div>
        }
        const investedEur = row.total_shares * row.avg_buy_price_eur
        const investedNative = row.total_shares * row.avg_buy_price
        return (
          <div>
            <div className="font-medium">{formatEur(investedEur)}</div>
            {!isEur && (
              <div className="text-xs text-gray-400">{formatNumber(investedNative, 2)} {row.currency}</div>
            )}
          </div>
        )
      },
    }),
    col.accessor('value_eur', {
      header: 'Valor (€) ↓',
      cell: info => {
        const row = info.row.original
        const eur = info.getValue()
        const isEur = row.currency === 'EUR'
        const valueCcy = row.current_price != null ? row.total_shares * row.current_price : null
        return (
          <div>
            <div className="font-medium">{eur != null ? formatEur(eur) : '—'}</div>
            {!isEur && valueCcy != null && (
              <div className="text-xs text-gray-400">{formatNumber(valueCcy, 2)} {row.currency}</div>
            )}
          </div>
        )
      },
    }),
    col.accessor('pnl_eur', {
      header: 'G/P',
      cell: info => {
        const row = info.row.original
        if (hasPeriod) {
          if (row.period_gain_eur == null) return <span className="text-gray-400">—</span>
          return (
            <div className={`font-medium ${pnlClass(row.period_gain_eur)}`}>
              {formatEur(row.period_gain_eur)}
            </div>
          )
        }
        const eur = info.getValue()
        const isEur = row.currency === 'EUR'
        const pnlNative = row.current_price != null
          ? row.total_shares * (row.current_price - row.avg_buy_price)
          : null
        if (eur == null) return <span className="text-gray-400">—</span>
        return (
          <div>
            <div className={pnlClass(eur)}>{formatEur(eur)}</div>
            {!isEur && pnlNative != null && (
              <div className={`text-xs ${pnlClassMuted(pnlNative)}`}>
                {pnlNative >= 0 ? '+' : ''}{formatNumber(pnlNative, 2)} {row.currency}
              </div>
            )}
          </div>
        )
      },
    }),
    col.accessor('gain_pct', {
      header: 'G/P %',
      cell: info => {
        const row = info.row.original
        if (hasPeriod) {
          if (row.period_gain_pct == null) return <span className="text-gray-400">—</span>
          return <span className={pnlClass(row.period_gain_pct)}>{formatPct(row.period_gain_pct)}</span>
        }
        const pctEur = info.getValue()
        const isEur = row.currency === 'EUR'
        const pctNative = row.current_price != null && row.avg_buy_price > 0
          ? (row.current_price / row.avg_buy_price - 1) * 100
          : null
        if (pctEur == null) return <span className="text-gray-400">—</span>
        return (
          <div>
            <div className={pnlClass(pctEur)}>{formatPct(pctEur)}</div>
            {!isEur && pctNative != null && (
              <div className={`text-xs ${pnlClassMuted(pctNative)}`} title="En moneda local (sin efecto divisa)">
                {formatPct(pctNative)} {row.currency}
              </div>
            )}
          </div>
        )
      },
    }),
    col.accessor('daily_change_pct', {
      header: 'Var. Diaria',
      cell: info => {
        const v = info.getValue()
        if (v == null) return <span className="text-gray-400">—</span>
        return <span className={pnlClass(v)}>{formatPct(v)}</span>
      },
    }),
    col.accessor('allocation_pct', {
      header: 'Asignación',
      cell: info => (
        <div className="flex items-center gap-2">
          <div className="w-16 bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
            <div
              className="bg-blue-500 h-1.5 rounded-full"
              style={{ width: `${Math.min(info.getValue(), 100)}%` }}
            />
          </div>
          <span className="text-sm text-gray-500">{info.getValue().toFixed(1)}%</span>
        </div>
      ),
    }),
  ], [hasPeriod])

  const table = useReactTable({
    data: holdings,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Composición</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id} className="border-b border-gray-100 dark:border-gray-700">
                {hg.headers.map(header => (
                  <th
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === 'asc' ? ' ↑' : header.column.getIsSorted() === 'desc' ? ' ↓' : ''}
                  </th>
                ))}
                <th className="px-3 py-2.5" />
              </tr>
            ))}
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length + 1} className="text-center py-12 text-gray-400">Cargando...</td></tr>
            ) : holdings.length === 0 ? (
              <tr><td colSpan={columns.length + 1} className="text-center py-12 text-gray-400 text-sm">Sin posiciones. Añade una transacción para empezar.</td></tr>
            ) : (
              table.getRowModel().rows.map(row => (
                <tr key={row.id} className="border-b border-gray-50 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                  {row.getVisibleCells().map(cell => (
                    <td key={cell.id} className="px-3 py-2.5 whitespace-nowrap">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                  <td className="px-3 py-2.5">
                    {row.original.manual_price && (
                      <button
                        onClick={() => setManualPriceAsset(row.original)}
                        className="text-xs text-amber-500 hover:text-amber-600 underline"
                      >
                        Actualizar precio
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {manualPriceAsset && (
        <ManualPriceModal
          asset={manualPriceAsset}
          onClose={() => setManualPriceAsset(null)}
          onSaved={load}
        />
      )}
    </div>
  )
}
