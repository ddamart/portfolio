import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import type { SortingState } from '@tanstack/react-table'
import { useEffect, useMemo, useState } from 'react'
import type { Asset, HoldingRow } from '../api/client'
import { portfolioApi } from '../api/client'
import { useRefresh } from '../contexts/RefreshContext'
import { formatCcy, formatEur, formatNumber, formatPct, pnlClass, pnlClassMuted } from '../utils/format'
import { getPeriodParams } from '../utils/period'
import { AssetDetailDrawer } from './AssetDetailDrawer'
import { AssetLogo } from './AssetLogo'
import { BalanceDrawer } from './BalanceDrawer'
import { ManualPriceModal } from './ManualPriceModal'

const col = createColumnHelper<HoldingRow>()

const BROKER_LABEL: Record<string, string> = {
  openbank: 'Openbank',
  trade_republic: 'Trade Republic',
  revolut: 'Revolut',
  degiro: 'Degiro',
}

const TYPE_LABEL: Record<string, string> = {
  stock: 'Stock', etf: 'ETF', fund: 'Fondo', balance: 'Cartera',
}

function buildCambioTip(row: HoldingRow, pStart: number): string {
  const pIniEur = pStart / row.total_shares
  // Only EUR for period-start: back-converting to native using today's FX rate
  // would be wrong (historical FX differs). End values are visible in the columns.
  const priceIni = formatEur(pIniEur, 4)
  return [
    `Precio inicio: ${priceIni}`,
    `Valor inicio:  ${formatEur(pStart)}`,
  ].join('\n')
}

export function PortfolioTable({ period, dateFrom, dateTo, broker, assetType }: {
  period: string
  dateFrom?: string
  dateTo?: string
  broker?: string
  assetType?: string
}) {
  const [holdings, setHoldings] = useState<HoldingRow[]>([])
  const [loading, setLoading] = useState(true)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'value_eur', desc: true }])
  const [manualPriceAsset, setManualPriceAsset] = useState<HoldingRow | null>(null)
  const [balanceDrawerAsset, setBalanceDrawerAsset] = useState<HoldingRow | null>(null)
  const [detailAsset, setDetailAsset] = useState<Asset | null>(null)
  const { lastRefreshAt } = useRefresh()

  const regularHoldings = useMemo(() => holdings.filter(h => h.type !== 'balance'), [holdings])
  const balanceHoldings = useMemo(() => holdings.filter(h => h.type === 'balance'), [holdings])
  const hasPeriod = period !== 'all' && !(period === 'custom' && !dateFrom)

  const load = () => {
    setLoading(true)
    const params = getPeriodParams(period, dateFrom, dateTo)
    if (broker) params.broker = broker
    if (assetType) params.asset_type = assetType
    portfolioApi.holdings(params).then(d => {
      setHoldings(d)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  useEffect(() => { load() }, [period, dateFrom, dateTo, broker, assetType, lastRefreshAt])

  const holdingToAsset = (h: HoldingRow): Asset => ({
    id: h.asset_id, name: h.name, ticker: h.ticker,
    type: h.type as Asset['type'], currency: h.currency,
    image_url: h.image_url, manual_price: h.manual_price,
    market_id: null, isin: null, created_at: '', in_portfolio: true,
  })

  const columns = useMemo(() => [
    col.accessor('name', {
      header: 'Activo',
      cell: info => {
        const h = info.row.original
        return (
          <button
            className="flex items-center gap-2 text-left hover:opacity-80 transition-opacity"
            onClick={() => setDetailAsset(holdingToAsset(h))}
          >
            <AssetLogo asset={h} className="w-7 h-7" />
            <div>
              <div className="flex items-center gap-1">
                <span className="font-medium text-gray-900 dark:text-white">{info.getValue()}</span>
                {h.manual_price && (
                  <span title="Precio manual" className="text-xs text-amber-500">✎</span>
                )}
              </div>
              <span className="text-xs font-mono text-gray-400">{h.ticker}</span>
            </div>
          </button>
        )
      },
    }),
    col.accessor('type', {
      header: 'Tipo',
      cell: info => (
        <span className="text-sm px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
          {TYPE_LABEL[info.getValue()] ?? info.getValue()}
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
    col.accessor(row => row.total_shares * row.avg_buy_price_eur, {
      id: 'total_invested',
      header: 'Invertido',
      cell: info => {
        const row = info.row.original
        const isEur = row.currency === 'EUR'
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
        const eur = info.getValue()
        const isEur = row.currency === 'EUR'
        const pnlNative = row.current_price != null
          ? row.total_shares * (row.current_price - row.avg_buy_price)
          : null
        if (eur == null) return <span className="text-gray-400">—</span>
        return (
          <div>
            <div className={`font-medium ${pnlClass(eur)}`}>{formatEur(eur)}</div>
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
        const v = info.getValue()
        if (v == null) return <span className="text-gray-400">—</span>
        return <span className={pnlClass(v)}>{formatPct(v)}</span>
      },
    }),
    col.accessor('cambio_eur', {
      header: 'Cambio',
      sortUndefined: 'last',
      cell: info => {
        const row = info.row.original
        if (row.cambio_eur == null) return <span className="text-gray-400">—</span>
        const pStart = row.period_start_value_eur
        const tip = pStart != null && row.total_shares > 0
          ? buildCambioTip(row, pStart)
          : undefined
        return <span className={`font-medium ${pnlClass(row.cambio_eur)}`} title={tip}>{formatEur(row.cambio_eur)}</span>
      },
    }),
    col.accessor('cambio_pct', {
      header: 'Cambio %',
      sortUndefined: 'last',
      cell: info => {
        const v = info.getValue()
        const row = info.row.original
        if (v == null) return <span className="text-gray-400">—</span>
        const pStart = row.period_start_value_eur
        const tip = pStart != null && row.total_shares > 0
          ? buildCambioTip(row, pStart)
          : undefined
        return <span className={pnlClass(v)} title={tip}>{formatPct(v)}</span>
      },
    }),
    ...(!hasPeriod ? [col.accessor('daily_change_pct', {
      header: 'Var. Diaria',
      cell: info => {
        const v = info.getValue()
        if (v == null) return <span className="text-gray-400">—</span>
        return <span className={pnlClass(v)}>{formatPct(v)}</span>
      },
    })] : []),
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
    data: regularHoldings,
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
            ) : regularHoldings.length === 0 ? (
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

      {/* Balance assets section */}
      {!loading && balanceHoldings.length > 0 && (
        <div className="border-t border-gray-200 dark:border-gray-700">
          <div className="px-4 py-2 bg-gray-50 dark:bg-gray-700/30">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Carteras / Cuentas</span>
          </div>
          {balanceHoldings.map(h => (
            <div
              key={h.asset_id}
              onClick={() => setBalanceDrawerAsset(h)}
              className="flex items-center gap-3 px-4 py-3 border-b border-gray-50 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30 cursor-pointer transition-colors"
            >
              <AssetLogo asset={{ id: h.asset_id, ticker: h.ticker, name: h.name, image_url: h.image_url, type: h.type } as Asset} className="w-7 h-7 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="font-medium text-gray-900 dark:text-white text-sm">{h.name}</p>
                <p className="text-xs font-mono text-gray-400">{h.ticker}</p>
              </div>
              {/* Inicio: first snapshot >= date_from (or last <= as fallback) */}
              <div className="text-right w-28">
                <p className="text-xs text-gray-400">Inicio</p>
                <p className="text-sm text-gray-700 dark:text-gray-300">
                  {h.balance_inicio_eur != null ? formatEur(h.balance_inicio_eur) : '—'}
                </p>
              </div>
              {/* Invertido: all-time net contributions <= date_to */}
              <div className="text-right w-28">
                <p className="text-xs text-gray-400">Invertido</p>
                <p className="text-sm text-gray-700 dark:text-gray-300">
                  {h.balance_contributions_eur != null ? formatEur(h.balance_contributions_eur) : '—'}
                </p>
              </div>
              {/* Fin: last snapshot <= date_to */}
              <div className="text-right w-28">
                <p className="text-xs text-gray-400">Fin</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {h.balance_value_eur != null ? formatEur(h.balance_value_eur) : '—'}
                </p>
                {h.balance_last_snapshot_date && (
                  <p className="text-xs text-gray-400">{h.balance_last_snapshot_date}</p>
                )}
              </div>
              {/* G/P all-time: Fin - Invertido */}
              <div className="text-right w-24">
                <p className="text-xs text-gray-400">G/P</p>
                {h.pnl_eur != null
                  ? <p className={`text-sm font-medium ${pnlClass(h.pnl_eur)}`}>{formatEur(h.pnl_eur)}</p>
                  : <p className="text-sm text-gray-400">—</p>}
              </div>
              <div className="text-right w-16">
                <p className="text-xs text-gray-400">G/P %</p>
                {h.gain_pct != null
                  ? <p className={`text-sm ${pnlClass(h.gain_pct)}`}>{formatPct(h.gain_pct)}</p>
                  : <p className="text-sm text-gray-400">—</p>}
              </div>
              {/* Cambio (period): Fin - Inicio - period_flows */}
              <div className="text-right w-24">
                <p className="text-xs text-gray-400">Cambio</p>
                {h.period_gain_eur != null
                  ? <p className={`text-sm font-medium ${pnlClass(h.period_gain_eur)}`}>{formatEur(h.period_gain_eur)}</p>
                  : <p className="text-sm text-gray-400">—</p>}
              </div>
              <div className="text-right w-16">
                <p className="text-xs text-gray-400">Cambio %</p>
                {h.period_gain_pct != null
                  ? <p className={`text-sm ${pnlClass(h.period_gain_pct)}`}>{formatPct(h.period_gain_pct)}</p>
                  : <p className="text-sm text-gray-400">—</p>}
              </div>
              <div className="text-right w-16">
                <div className="flex items-center gap-1.5 justify-end">
                  <div className="w-12 bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                    <div className="bg-purple-500 h-1.5 rounded-full" style={{ width: `${Math.min(h.allocation_pct, 100)}%` }} />
                  </div>
                  <span className="text-xs text-gray-500">{h.allocation_pct.toFixed(1)}%</span>
                </div>
              </div>
              <span className="text-gray-400 text-xs">›</span>
            </div>
          ))}
        </div>
      )}

      {balanceDrawerAsset && (
        <BalanceDrawer
          asset={{ id: balanceDrawerAsset.asset_id, ticker: balanceDrawerAsset.ticker, name: balanceDrawerAsset.name, image_url: balanceDrawerAsset.image_url, type: 'balance', currency: 'EUR', market_id: null, manual_price: true, isin: null, created_at: '', in_portfolio: true } as Asset}
          onClose={() => setBalanceDrawerAsset(null)}
        />
      )}

      {detailAsset && (
        <AssetDetailDrawer asset={detailAsset} onClose={() => setDetailAsset(null)} />
      )}
    </div>
  )
}
