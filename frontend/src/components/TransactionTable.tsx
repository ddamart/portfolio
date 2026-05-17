import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import type { SortingState } from '@tanstack/react-table'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import type { Transaction } from '../api/client'
import { transactionsApi } from '../api/client'
import { formatEur, formatNumber } from '../utils/format'
import { PeriodFilter } from './PeriodFilter'
import { TransactionForm } from './TransactionForm'

const BROKER_LABELS: Record<string, string> = {
  openbank: 'Openbank',
  trade_republic: 'Trade Republic',
  revolut: 'Revolut',
  degiro: 'Degiro',
}

const col = createColumnHelper<Transaction>()

export function TransactionTable() {
  const [period, setPeriod] = useState('all')
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'date', desc: true }])
  const [editTx, setEditTx] = useState<Transaction | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const load = () => {
    setLoading(true)
    transactionsApi.list({ period }).then(d => {
      setTransactions(d)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  useEffect(() => { load() }, [period])

  const handleDelete = async (tx: Transaction) => {
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
  }

  const columns = [
    col.accessor('date', {
      header: 'Fecha',
      cell: info => <span className="text-gray-600 dark:text-gray-400 text-sm">{info.getValue()}</span>,
    }),
    col.accessor('asset_name', {
      header: 'Activo',
      cell: info => (
        <div>
          <span className="font-medium text-gray-900 dark:text-white">{info.getValue()}</span>
          <span className="text-xs text-gray-400 ml-1">{info.row.original.asset_ticker}</span>
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
    col.accessor('price', {
      header: 'Precio',
      cell: info => `${formatNumber(info.getValue(), 4)} ${info.row.original.currency}`,
    }),
    col.accessor('price_eur', {
      header: 'Precio (€)',
      cell: info => formatEur(info.getValue()),
    }),
    col.display({
      id: 'cost_eur',
      header: 'Coste (€)',
      cell: info => formatEur(info.row.original.shares * info.row.original.price_eur),
    }),
    col.accessor('commission', {
      header: 'Comisión',
      cell: info => info.getValue() > 0
        ? `${formatNumber(info.getValue(), 2)} ${info.row.original.currency}`
        : <span className="text-gray-400">—</span>,
    }),
  ]

  const table = useReactTable({
    data: transactions,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Transacciones</h2>
        <div className="flex items-center gap-3">
          <PeriodFilter value={period} onChange={setPeriod} />
          <button
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            + Nueva
          </button>
        </div>
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
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Acciones</th>
              </tr>
            ))}
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length + 1} className="text-center py-12 text-gray-400">Cargando...</td></tr>
            ) : transactions.length === 0 ? (
              <tr><td colSpan={columns.length + 1} className="text-center py-12 text-gray-400 text-sm">Sin transacciones para el período seleccionado.</td></tr>
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
