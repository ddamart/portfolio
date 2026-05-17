import { useState } from 'react'
import toast from 'react-hot-toast'
import type { ParsedTransaction } from '../api/client'
import { importApi } from '../api/client'

const VALID_BROKERS = ['openbank', 'trade_republic', 'revolut', 'degiro']
const ASSET_TYPES = ['stock', 'etf', 'fund'] as const
const TX_TYPES = ['buy', 'sell'] as const

export function ImportPage() {
  const [rawText, setRawText] = useState('')
  const [brokerHint, setBrokerHint] = useState('')
  const [parsing, setParsing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [rows, setRows] = useState<ParsedTransaction[]>([])
  const [result, setResult] = useState<{ imported: number; errors: string[] } | null>(null)

  const handleParse = async () => {
    if (!rawText.trim()) return
    setParsing(true)
    setRows([])
    setResult(null)
    try {
      const data = await importApi.parse(rawText, brokerHint || undefined)
      setRows(data.transactions)
      if (data.transactions.length === 0) {
        toast.error('No se encontraron transacciones en el texto')
      } else {
        toast.success(`${data.transactions.length} transacciones detectadas`)
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'Error al analizar el texto')
    } finally {
      setParsing(false)
    }
  }

  const handleConfirm = async () => {
    if (rows.length === 0) return
    const invalid = rows.filter(r => !VALID_BROKERS.includes(r.broker))
    if (invalid.length > 0) {
      toast.error(`Selecciona un broker válido para: ${invalid.map(r => r.ticker).join(', ')}`)
      return
    }
    setConfirming(true)
    try {
      const data = await importApi.confirm(rows)
      setResult(data)
      if (data.imported > 0) {
        toast.success(`${data.imported} transacciones importadas`)
        setRows([])
        setRawText('')
      }
      if (data.errors.length > 0) {
        toast.error(`${data.errors.length} error(es) — ver detalle abajo`)
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      if (detail) {
        // Show first line in toast, full detail in result panel
        const firstLine = detail.split('\n')[0]
        toast.error(firstLine)
        setResult({ imported: 0, errors: detail.split('\n').filter(Boolean) })
      } else {
        toast.error('Error al importar')
      }
    } finally {
      setConfirming(false)
    }
  }

  const updateRow = (idx: number, field: keyof ParsedTransaction, value: unknown) => {
    setRows(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }

  const deleteRow = (idx: number) => {
    setRows(prev => prev.filter((_, i) => i !== idx))
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Importar transacciones</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Pega datos en cualquier formato (CSV, tabla, texto de email) y la IA extraerá las transacciones.
        </p>
      </div>

      {/* Input area */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6 space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            Broker (opcional — ayuda al modelo a interpretar el formato)
          </label>
          <select
            value={brokerHint}
            onChange={e => setBrokerHint(e.target.value)}
            className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
          >
            <option value="">Detectar automáticamente</option>
            {VALID_BROKERS.map(b => (
              <option key={b} value={b}>{b.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            Datos del broker
          </label>
          <textarea
            value={rawText}
            onChange={e => setRawText(e.target.value)}
            placeholder={"Pega aquí: CSV de Degiro, tabla de Trade Republic, extracto de Openbank, etc.\n\nEjemplo:\nFecha,Producto,ISIN,Cantidad,Precio,Valor\n15-03-2024,Apple,US0378331005,10,170.50,1705.00"}
            className="w-full h-52 text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 font-mono resize-y"
          />
        </div>

        <button
          onClick={handleParse}
          disabled={parsing || !rawText.trim()}
          className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {parsing ? (
            <span className="flex items-center gap-2">
              <span className="animate-spin inline-block">⟳</span> Analizando...
            </span>
          ) : 'Analizar con IA'}
        </button>
      </div>

      {/* Preview table */}
      {rows.length > 0 && (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6 space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                Vista previa — {rows.length} transacciones
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                Revisa y edita los datos antes de confirmar. Las celdas son editables.
              </p>
            </div>
            <button
              onClick={handleConfirm}
              disabled={confirming}
              className="px-5 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              {confirming ? 'Importando...' : `Confirmar importación (${rows.length})`}
            </button>
          </div>

          <div className="overflow-x-auto -mx-2">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700 text-left">
                  <Th>Fecha</Th>
                  <Th>Ticker</Th>
                  <Th>Tipo</Th>
                  <Th>Op.</Th>
                  <Th right>Cantidad</Th>
                  <Th right>Precio</Th>
                  <Th>Divisa</Th>
                  <Th right>Precio EUR</Th>
                  <Th right>Comisión</Th>
                  <Th>Broker</Th>
                  <Th></Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {rows.map((row, idx) => (
                  <ImportRow
                    key={idx}
                    row={row}
                    onChange={(field, value) => updateRow(idx, field, value)}
                    onDelete={() => deleteRow(idx)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className={`rounded-xl border p-4 space-y-2 ${
          result.errors.length === 0
            ? 'bg-green-50 dark:bg-green-950 border-green-200 dark:border-green-800'
            : 'bg-yellow-50 dark:bg-yellow-950 border-yellow-200 dark:border-yellow-800'
        }`}>
          {result.imported > 0 && (
            <p className="text-sm font-medium text-green-800 dark:text-green-200">
              ✓ {result.imported} transacciones importadas correctamente
            </p>
          )}
          {result.errors.map((err, i) => (
            <p key={i} className="text-xs text-red-600 dark:text-red-400 font-mono">{err}</p>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Th({ children, right }: { children?: React.ReactNode; right?: boolean }) {
  return (
    <th className={`py-2 px-2 text-xs font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap ${right ? 'text-right' : 'text-left'}`}>
      {children}
    </th>
  )
}

function ImportRow({
  row,
  onChange,
  onDelete,
}: {
  row: ParsedTransaction
  onChange: (field: keyof ParsedTransaction, value: unknown) => void
  onDelete: () => void
}) {
  const isInvalidBroker = !VALID_BROKERS.includes(row.broker)

  const base = "py-1.5 px-2"
  const input = "w-full bg-transparent border-b border-transparent hover:border-gray-300 dark:hover:border-gray-600 focus:border-blue-500 outline-none text-sm text-gray-900 dark:text-white min-w-0"
  const sel = "bg-transparent text-sm text-gray-900 dark:text-white border border-transparent hover:border-gray-300 dark:hover:border-gray-600 focus:border-blue-500 outline-none rounded"

  return (
    <tr className="hover:bg-gray-50 dark:hover:bg-gray-800/40">
      <td className={base}>
        <input
          type="date"
          value={row.date}
          onChange={e => onChange('date', e.target.value)}
          className={`${input} w-32`}
        />
      </td>
      <td className={base}>
        <input
          value={row.ticker}
          onChange={e => onChange('ticker', e.target.value.toUpperCase())}
          className={`${input} uppercase font-mono w-24`}
        />
      </td>
      <td className={base}>
        <select
          value={row.asset_type}
          onChange={e => onChange('asset_type', e.target.value)}
          className={sel}
        >
          {ASSET_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </td>
      <td className={base}>
        <select
          value={row.transaction_type}
          onChange={e => onChange('transaction_type', e.target.value)}
          className={sel}
        >
          {TX_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </td>
      <td className={`${base} text-right`}>
        <input
          type="number"
          value={row.shares}
          min={0}
          step="any"
          onChange={e => onChange('shares', parseFloat(e.target.value) || 0)}
          className={`${input} text-right w-20`}
        />
      </td>
      <td className={`${base} text-right`}>
        <input
          type="number"
          value={row.price}
          min={0}
          step="any"
          onChange={e => onChange('price', parseFloat(e.target.value) || 0)}
          className={`${input} text-right w-24`}
        />
      </td>
      <td className={base}>
        <input
          value={row.currency}
          onChange={e => onChange('currency', e.target.value.toUpperCase())}
          className={`${input} uppercase w-12`}
          maxLength={3}
        />
      </td>
      <td className={`${base} text-right text-gray-400 dark:text-gray-500 tabular-nums`}>
        {row.price_eur != null ? row.price_eur.toFixed(4) : '—'}
      </td>
      <td className={`${base} text-right`}>
        <input
          type="number"
          value={row.commission}
          min={0}
          step="any"
          onChange={e => onChange('commission', parseFloat(e.target.value) || 0)}
          className={`${input} text-right w-20`}
        />
      </td>
      <td className={base}>
        <select
          value={row.broker}
          onChange={e => onChange('broker', e.target.value)}
          className={`${sel} ${isInvalidBroker ? 'text-red-500 dark:text-red-400 border-red-400' : ''}`}
        >
          {isInvalidBroker && <option value={row.broker}>{row.broker}</option>}
          {VALID_BROKERS.map(b => (
            <option key={b} value={b}>{b.replace(/_/g, ' ')}</option>
          ))}
        </select>
      </td>
      <td className={base}>
        <button
          onClick={onDelete}
          title="Eliminar fila"
          className="text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors px-1"
        >
          ✕
        </button>
      </td>
    </tr>
  )
}
