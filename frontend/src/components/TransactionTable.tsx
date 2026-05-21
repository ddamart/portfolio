import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import type { SortingState } from '@tanstack/react-table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import type { Transaction } from '../api/client'
import { transactionsApi } from '../api/client'
import { formatEur, formatNumber, formatPct, pnlClass } from '../utils/format'
import { AssetLogo } from './AssetLogo'
import { PeriodFilter } from './PeriodFilter'
import { TransactionForm } from './TransactionForm'

const BROKER_LABELS: Record<string, string> = {
  openbank: 'Openbank',
  trade_republic: 'Trade Republic',
  revolut: 'Revolut',
  degiro: 'Degiro',
}

const BROKERS = Object.keys(BROKER_LABELS) as (keyof typeof BROKER_LABELS)[]

function FilterPills<T extends string>({
  label, options, value, onChange,
}: {
  label: string
  options: { value: T; label: string }[]
  value: T | 'all'
  onChange: (v: T | 'all') => void
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">{label}:</span>
      {options.map(opt => (
        <button
          key={opt.value}
          onClick={() => onChange(value === opt.value ? 'all' : opt.value)}
          className={`text-xs px-2.5 py-1 rounded-full border font-medium transition-colors whitespace-nowrap ${
            value === opt.value
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

const col = createColumnHelper<Transaction>()

export function TransactionTable() {
  const [period, setPeriod] = useState('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'date', desc: true }])
  const [editTx, setEditTx] = useState<Transaction | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [filterType, setFilterType]     = useState<'stock' | 'etf' | 'fund' | 'all'>('all')
  const [filterOp, setFilterOp]         = useState<'buy' | 'sell' | 'all'>('all')
  const [filterBroker, setFilterBroker] = useState<string>('all')

  const load = useCallback(() => {
    setLoading(true)
    const params: Record<string, string> = period === 'custom'
      ? { ...(dateFrom && { date_from: dateFrom }), ...(dateTo && { date_to: dateTo }) }
      : { period }
    transactionsApi.list(params).then(d => {
      setTransactions(d)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [period, dateFrom, dateTo])

  useEffect(() => { load() }, [load])

  const handleDelete = useCallback(async (tx: Transaction) => {
    if (!confirm(`¿Eliminar transacción de ${tx.shares} × ${tx.asset_ticker}?`)) return
    setDeletingId(tx.id)
    try {
      await transactionsApi.delete(tx.id)
      toast.success('Transacción eliminada')
      load()
    } catch {
      toast.error('Error al eliminar')
    } finally {
      setDeletingId(null)
    }
  }, [load])

  const columns = useMemo(() => [
    col.accessor('date', {
      header: 'Fecha',
      cell: info => <span className="text-gray-600 dark:text-gray-400 text-sm">{info.getValue()}</span>,
    }),
    col.accessor('asset_name', {
      header: 'Activo',
      cell: info => (
        <div className="flex items-center gap-2">
          <AssetLogo
            asset={{ image_url: info.row.original.asset_image_url, ticker: info.row.original.asset_ticker }}
            className="w-7 h-7"
          />
          <div>
            <span className="font-medium text-gray-900 dark:text-white">{info.getValue()}</span>
            <span className="block text-xs font-mono text-gray-400">{info.row.original.asset_ticker}</span>
          </div>
        </div>
      ),
    }),
    col.accessor('asset_type', {
      header: 'Tipo',
      cell: info => (
        <span className="capitalize text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
          {info.getValue()}
        </span>
      ),
    }),
    col.accessor('type', {
      header: 'Operación',
      cell: info => (
        <span className={`text-xs font-medium px-2 py-1 rounded-full ${
          info.getValue() === 'buy'
            ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
            : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
        }`}>
          {info.getValue() === 'buy' ? 'Compra' : 'Venta'}
        </span>
      ),
    }),
    col.accessor('broker', {
      header: 'Broker',
      cell: info => BROKER_LABELS[info.getValue()] ?? info.getValue(),
    }),
    col.accessor('shares', {
      header: 'Participaciones',
      cell: info => formatNumber(info.getValue()),
    }),
    col.accessor('price_eur', {
      id: 'price',
      header: 'Precio',
      cell: info => {
        const row = info.row.original
        const isEur = row.currency === 'EUR'
        return (
          <div>
            <div>{formatNumber(row.price, 4)} {row.currency}</div>
            {!isEur && <div className="text-xs text-gray-400">{formatEur(row.price_eur)}</div>}
          </div>
        )
      },
    }),
    col.accessor(row => row.shares * row.price_eur, {
      id: 'cost',
      header: 'Coste',
      cell: info => {
        const row = info.row.original
        const isEur = row.currency === 'EUR'
        const costEur = row.shares * row.price_eur
        const costLocal = row.shares * row.price
        return (
          <div>
            <div>{formatEur(costEur)}</div>
            {!isEur && <div className="text-xs text-gray-400">{formatNumber(costLocal, 2)} {row.currency}</div>}
          </div>
        )
      },
    }),
    col.accessor('commission', {
      header: 'Comisión',
      cell: info => {
        const row = info.row.original
        if (info.getValue() <= 0) return <span className="text-gray-400">—</span>
        const commCcy = row.commission_currency
        return (
          <div>
            <div>{formatNumber(info.getValue(), 2)} {commCcy}</div>
            {commCcy !== 'EUR' && <div className="text-xs text-gray-400">{formatEur(row.commission_eur)}</div>}
          </div>
        )
      },
    }),
    col.accessor(row => {
      const tradeEur = row.shares * row.price_eur
      return tradeEur > 0 ? (row.commission_eur / tradeEur) * 100 : 0
    }, {
      id: 'commission_pct',
      header: 'Com. %',
      cell: info => {
        const row = info.row.original
        const tradeEur = row.shares * row.price_eur
        if (row.commission_eur <= 0 || tradeEur <= 0) return <span className="text-gray-400">—</span>
        const pct = (row.commission_eur / tradeEur) * 100
        return (
          <span className="text-gray-500 dark:text-gray-400 text-xs">
            {pct.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 3 })}%
          </span>
        )
      },
    }),
    col.accessor('realized_pnl_eur', {
      id: 'realized_pnl',
      header: 'P&L Real.',
      sortingFn: (a, b) => {
        const va = a.original.realized_pnl_eur ?? -Infinity
        const vb = b.original.realized_pnl_eur ?? -Infinity
        return va - vb
      },
      cell: info => {
        const row = info.row.original
        if (row.type !== 'sell' || row.realized_pnl_eur == null || row.cost_basis_eur == null) {
          return <span className="text-gray-400">—</span>
        }
        const gainPct = (row.price_eur / row.cost_basis_eur - 1) * 100
        return (
          <div className={pnlClass(row.realized_pnl_eur)}>
            <div className="font-medium">{formatEur(row.realized_pnl_eur)}</div>
            <div className="text-xs">{formatPct(gainPct)}</div>
          </div>
        )
      },
    }),
  ], [handleDelete, setEditTx])

  const activeBrokers = useMemo(
    () => [...new Set(transactions.map(t => t.broker))].filter(b => BROKERS.includes(b as typeof BROKERS[number])),
    [transactions]
  )

  const filtered = useMemo(
    () => transactions.filter(t =>
      (filterType   === 'all' || t.asset_type === filterType) &&
      (filterOp     === 'all' || t.type       === filterOp) &&
      (filterBroker === 'all' || t.broker     === filterBroker)
    ),
    [transactions, filterType, filterOp, filterBroker]
  )

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="flex-1 min-h-0 flex flex-col bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 border-b border-gray-100 dark:border-gray-700/50">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Transacciones</h2>
        <div className="flex items-center gap-3">
          <PeriodFilter
              value={period}
              onChange={setPeriod}
              dateFrom={dateFrom}
              dateTo={dateTo}
              onDateRange={(from, to) => { setDateFrom(from); setDateTo(to) }}
            />
          <button
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            + Nueva
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4 px-4 py-2.5 border-b border-gray-100 dark:border-gray-700">
        <FilterPills
          label="Tipo"
          value={filterType}
          onChange={setFilterType}
          options={[
            { value: 'stock', label: 'Acciones' },
            { value: 'etf',   label: 'ETF' },
            { value: 'fund',  label: 'Fondos' },
          ]}
        />
        <FilterPills
          label="Operación"
          value={filterOp}
          onChange={setFilterOp}
          options={[
            { value: 'buy',  label: 'Compra' },
            { value: 'sell', label: 'Venta' },
          ]}
        />
        <FilterPills
          label="Broker"
          value={filterBroker}
          onChange={setFilterBroker}
          options={activeBrokers.map(b => ({ value: b, label: BROKER_LABELS[b] ?? b }))}
        />
        {(filterType !== 'all' || filterOp !== 'all' || filterBroker !== 'all') && (
          <button
            onClick={() => { setFilterType('all'); setFilterOp('all'); setFilterBroker('all') }}
            className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 underline ml-auto"
          >
            Limpiar filtros
          </button>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
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
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Acciones</th>
              </tr>
            ))}
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length + 1} className="text-center py-12 text-gray-400">Cargando...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={columns.length + 1} className="text-center py-12 text-gray-400 text-sm">
                {transactions.length === 0 ? 'Sin transacciones para el período seleccionado.' : 'Sin resultados para los filtros activos.'}
              </td></tr>
            ) : (
              table.getRowModel().rows.map(row => (
                <tr key={row.id} className="border-b border-gray-50 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                  {row.getVisibleCells().map(cell => (
                    <td key={cell.id} className="px-4 py-3 whitespace-nowrap">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button
                      onClick={() => setEditTx(row.original)}
                      className="text-xs text-blue-500 hover:text-blue-700 mr-3"
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => handleDelete(row.original)}
                      disabled={deletingId === row.original.id}
                      className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {(showAdd || editTx) && (
        <TransactionForm
          existing={editTx ?? undefined}
          onClose={() => { setShowAdd(false); setEditTx(null) }}
          onSaved={load}
        />
      )}
    </div>
  )
}
