import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import type { Asset, BalanceEntry } from '../api/client'
import { balanceApi } from '../api/client'
import { formatEur } from '../utils/format'
import { AssetLogo } from './AssetLogo'

const TYPE_LABEL: Record<string, string> = {
  deposit: 'Aportación',
  withdrawal: 'Retirada',
  snapshot: 'Valoración',
}

const TYPE_COLOR: Record<string, string> = {
  deposit: 'bg-blue-900/40 text-blue-300',
  withdrawal: 'bg-red-900/40 text-red-300',
  snapshot: 'bg-purple-900/40 text-purple-300',
}

interface Props {
  asset: Asset
  onClose: () => void
}

/** Normalise a user-typed amount that may use Spanish decimal format (1.234,56 or 1234,56). */
function parseAmount(v: string): number {
  const s = v.trim()
  if (!s) return NaN
  if (s.includes('.') && s.includes(',')) return parseFloat(s.replace(/\./g, '').replace(',', '.'))
  if (s.includes(',')) return parseFloat(s.replace(',', '.'))
  return parseFloat(s)
}

/** Parse a CSV/TSV text into import rows.
 *  Accepted column order: date, value[, type]
 *  Date formats handled: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY
 *  Numeric separators: 1.234,56 (ES) and 1,234.56 (EN) both accepted.
 */
function parseCsvText(raw: string): { date: string; amount_eur: number; type: string }[] {
  const rows: { date: string; amount_eur: number; type: string }[] = []
  for (const line of raw.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    // Split on comma or tab/semicolon
    const sep = trimmed.includes('\t') ? '\t' : trimmed.includes(';') ? ';' : ','
    const parts = trimmed.split(sep).map(p => p.trim().replace(/^"|"$/g, ''))
    if (parts.length < 2) continue
    const [dateRaw, valRaw, typeRaw = 'snapshot'] = parts
    // Normalise ES number format: 1.234,56 → 1234.56
    const normalised = valRaw.replace(/\./g, '').replace(',', '.')
    const amount_eur = parseFloat(normalised)
    if (!dateRaw || isNaN(amount_eur)) continue
    const type = typeRaw.toLowerCase().trim()
    rows.push({ date: dateRaw, amount_eur, type: ['deposit', 'withdrawal', 'snapshot'].includes(type) ? type : 'snapshot' })
  }
  return rows
}

export function BalanceDrawer({ asset, onClose }: Props) {
  const [entries, setEntries] = useState<BalanceEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ type: 'snapshot', date: new Date().toISOString().slice(0, 10), amount: '', notes: '' })
  const [saving, setSaving] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [csvText, setCsvText] = useState('')
  const [importing, setImporting] = useState(false)

  const load = () => {
    setLoading(true)
    balanceApi.list(asset.id)
      .then(setEntries)
      .catch(() => toast.error('Error al cargar entradas'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [asset.id])

  const latestSnapshot = entries.find(e => e.type === 'snapshot')
  const netContributions = entries.reduce((sum, e) => {
    if (e.type === 'deposit') return sum + e.amount_eur
    if (e.type === 'withdrawal') return sum - e.amount_eur
    return sum
  }, 0)
  const pnl = latestSnapshot ? latestSnapshot.amount_eur - netContributions : null

  const handleAdd = async () => {
    const amount = parseAmount(form.amount)
    if (!form.date || isNaN(amount) || amount <= 0) {
      toast.error('Fecha y cantidad requeridas')
      return
    }
    setSaving(true)
    try {
      await balanceApi.create(asset.id, {
        date: form.date,
        type: form.type,
        amount_eur: amount,
        notes: form.notes.trim() || undefined,
      })
      setForm(f => ({ ...f, amount: '', notes: '' }))
      load()
    } catch {
      toast.error('Error al guardar')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await balanceApi.delete(id)
      load()
    } catch {
      toast.error('Error al eliminar')
    }
  }

  const handleImport = async () => {
    const rows = parseCsvText(csvText)
    if (rows.length === 0) { toast.error('No se encontraron filas válidas'); return }
    setImporting(true)
    try {
      const result = await balanceApi.import(asset.id, rows)
      toast.success(`${result.inserted} entradas importadas`)
      if (result.errors.length > 0) toast.error(`${result.errors.length} filas con error`)
      setCsvText('')
      setShowImport(false)
      load()
    } catch {
      toast.error('Error al importar')
    } finally {
      setImporting(false)
    }
  }

  const importPreview = csvText.trim() ? parseCsvText(csvText) : []

  const inputCls = 'w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500'

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div
        className="relative w-full max-w-md bg-white dark:bg-gray-900 h-full flex flex-col shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <AssetLogo asset={asset} className="w-9 h-9" />
            <div>
              <p className="font-semibold text-gray-900 dark:text-white">{asset.name}</p>
              <p className="text-xs text-gray-400 font-mono">{asset.ticker}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-xl leading-none">✕</button>
        </div>

        {/* Summary stats */}
        {!loading && (
          <div className="grid grid-cols-3 gap-3 px-5 py-4 border-b border-gray-200 dark:border-gray-700">
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">Valor actual</p>
              <p className="text-lg font-bold text-gray-900 dark:text-white">
                {latestSnapshot ? formatEur(latestSnapshot.amount_eur) : '—'}
              </p>
              {latestSnapshot && (
                <p className="text-xs text-gray-400">{latestSnapshot.date}</p>
              )}
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">Aportado neto</p>
              <p className="text-lg font-bold text-gray-900 dark:text-white">{formatEur(netContributions)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">G/P</p>
              <p className={`text-lg font-bold ${pnl == null ? 'text-gray-400' : pnl >= 0 ? 'text-green-500' : 'text-red-400'}`}>
                {pnl == null ? '—' : formatEur(pnl)}
              </p>
              {pnl != null && netContributions > 0 && (
                <p className={`text-xs ${pnl >= 0 ? 'text-green-500' : 'text-red-400'}`}>
                  {pnl >= 0 ? '+' : ''}{((pnl / netContributions) * 100).toFixed(2)}%
                </p>
              )}
            </div>
          </div>
        )}

        {/* Add entry form */}
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700 space-y-3">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Nueva entrada</p>
          <div className="grid grid-cols-2 gap-2">
            <select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))} className={inputCls}>
              <option value="snapshot">Valoración</option>
              <option value="deposit">Aportación</option>
              <option value="withdrawal">Retirada</option>
            </select>
            <input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))} className={inputCls} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="text" inputMode="decimal"
              placeholder={form.type === 'snapshot' ? 'Valor total (€)' : 'Importe (€)'}
              value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))}
              className={inputCls}
            />
            <input
              placeholder="Nota (opcional)"
              value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              className={inputCls}
            />
          </div>
          <button
            onClick={handleAdd} disabled={saving}
            className="w-full py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Guardando...' : 'Añadir entrada'}
          </button>
        </div>

        {/* Bulk import */}
        <div className="border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setShowImport(v => !v)}
            className="w-full flex items-center justify-between px-5 py-3 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
          >
            <span className="font-medium">Importar CSV histórico</span>
            <span className="text-xs">{showImport ? '▲' : '▼'}</span>
          </button>
          {showImport && (
            <div className="px-5 pb-4 space-y-3">
              <p className="text-xs text-gray-400 leading-relaxed">
                Columnas: <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">fecha,valor[,tipo]</code> —
                tipo es <em>snapshot</em> por defecto.
                Separadores: coma, punto y coma o tabulador.
                Números en formato español (1.234,56) o inglés (1234.56).
                La importación borra entradas existentes del mismo tipo antes de insertar.
              </p>
              <textarea
                value={csvText}
                onChange={e => setCsvText(e.target.value)}
                placeholder={"2024-09-04,9655.00\n2024-09-05,9662.30\n04/09/2024,9655,snapshot"}
                rows={6}
                className="w-full font-mono text-xs border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
              />
              {importPreview.length > 0 && (
                <p className="text-xs text-gray-400">
                  {importPreview.length} filas detectadas — del {importPreview[0].date} al {importPreview[importPreview.length - 1].date}
                </p>
              )}
              <button
                onClick={handleImport}
                disabled={importing || importPreview.length === 0}
                className="w-full py-2 bg-purple-600 text-white text-sm font-medium rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors"
              >
                {importing ? 'Importando...' : `Importar ${importPreview.length} filas`}
              </button>
            </div>
          )}
        </div>

        {/* Entry list */}
        <div className="flex-1 overflow-y-auto px-5 py-3">
          {loading ? (
            <p className="text-center text-gray-400 py-8 text-sm">Cargando...</p>
          ) : entries.length === 0 ? (
            <p className="text-center text-gray-400 py-8 text-sm">Sin entradas. Añade una valoración o aportación.</p>
          ) : (
            <div className="space-y-2">
              {entries.map(e => (
                <div key={e.id} className="flex items-center gap-3 py-2 border-b border-gray-100 dark:border-gray-800 group">
                  <span className={`shrink-0 text-xs px-2 py-0.5 rounded font-medium ${TYPE_COLOR[e.type]}`}>
                    {TYPE_LABEL[e.type]}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="font-semibold text-gray-900 dark:text-white">{formatEur(e.amount_eur)}</span>
                      <span className="text-xs text-gray-400">{e.date}</span>
                    </div>
                    {e.notes && <p className="text-xs text-gray-400 truncate">{e.notes}</p>}
                  </div>
                  <button
                    onClick={() => handleDelete(e.id)}
                    className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 text-xs transition-opacity"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
