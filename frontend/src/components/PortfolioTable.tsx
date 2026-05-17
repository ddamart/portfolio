import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import type { SortingState } from '@tanstack/react-table'
import { useEffect, useState } from 'react'
import type { HoldingRow } from '../api/client'
import { portfolioApi } from '../api/client'
import { formatEur, formatNumber, formatPct, pnlClass } from '../utils/format'
import { PeriodFilter } from './PeriodFilter'
import { ManualPriceModal } from './ManualPriceModal'

const col = createColumnHelper<HoldingRow>()

const columns = [
  col.accessor('name', {
    header: 'Activo',
    cell: info => (
      <div className="flex items-center gap-2">
        {info.row.original.image_url && (
          <img
            src={info.row.original.image_url}
            alt=""
            className="w-6 h-6 rounded-full object-contain"
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
        )}
        <span className="font-medium text-gray-900 dark:text-white">{info.getValue()}</span>
        {info.row.original.manual_price && (
          <span title="Precio manual" className="text-xs text-amber-500">✎</span>
        )}
      </div>
    ),
  }),
  col.accessor('ticker', {
    header: 'Símbolo',
    cell: info => <span className="font-mono text-sm text-gray-500">{info.getValue()}</span>,
  }),
  col.accessor('type', {
    header: 'Tipo',
    cell: info => (
      <span className="capitalize text-sm px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
        {info.getValue()}
      </span>
    ),
  }),
  col.accessor('total_shares', {
    header: 'Participaciones',
    cell: info => formatNumber(info.getValue()),
  }),
  col.accessor('avg_buy_price_eur', {
    header: 'P. Medio Compra',
    cell: info => formatEur(info.getValue()),
  }),
  col.accessor('current_price_eur', {
    header: 'P. Actual',
    cell: info => formatEur(info.getValue()),
  }),
  col.accessor('value_eur', {
    header: 'Valor (€)',
    cell: info => <span className="font-medium">{formatEur(info.getValue())}</span>,
  }),
  col.accessor('value_ccy', {
    header: 'Valor (divisa)',
    cell: info => {
      const row = info.row.original
      return `${formatNumber(info.getValue(), 2)} ${row.currency}`
    },
  }),
  col.accessor('pnl_eur', {
    header: 'G/P (€)',
    cell: info => (
      <span className={pnlClass(info.getValue())}>
        {formatEur(info.getValue())}
      </span>
    ),
  }),
  col.accessor('gain_pct', {
    header: 'G/P %',
    cell: info => (
      <span className={pnlClass(info.getValue())}>
        {formatPct(info.getValue())}
      </span>
    ),
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
        <div className="w-20 bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
          <div
            className="bg-blue-500 h-1.5 rounded-full"
            style={{ width: `${Math.min(info.getValue(), 100)}%` }}
          />
        </div>
        <span className="text-sm text-gray-500">{info.getValue().toFixed(1)}%</span>
      </div>
    ),
  }),
]

export function PortfolioTable() {
  const [period, setPeriod] = useState('all')
  const [holdings, setHoldings] = useState<HoldingRow[]>([])
  const [loading, setLoading] = useState(true)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'value_eur', desc: true }])
  const [manualPriceAsset, setManualPriceAsset] = useState<HoldingRow | null>(null)

  const load = () => {
    setLoading(true)
    portfolioApi.holdings({ period }).then(d => {
      setHoldings(d)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  useEffect(() => { load() }, [period])

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
      <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Composición</h2>
        <PeriodFilter value={period} onChange={setPeriod} />
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
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none whitespace-nowrap"
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === 'asc' ? ' ↑' : header.column.getIsSorted() === 'desc' ? ' ↓' : ''}
                  </th>
                ))}
                <th className="px-4 py-3" />
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
                    <td key={cell.id} className="px-4 py-3 whitespace-nowrap">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                  <td className="px-4 py-3">
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
