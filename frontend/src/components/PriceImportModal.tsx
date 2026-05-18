import { useState } from 'react'
import toast from 'react-hot-toast'
import type { Asset } from '../api/client'
import { assetsApi } from '../api/client'

interface ParsedRow {
  date: string
  price: number
  raw: string
}

function parseCSV(text: string): { valid: ParsedRow[]; invalid: string[] } {
  const valid: ParsedRow[] = []
  const invalid: string[] = []
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim()
    if (!line) continue
    const parts = line.split(/[,;\t]/).map(p => p.trim())
    if (parts.length < 2) { invalid.push(line); continue }
    const [datePart, pricePart] = parts
    const price = parseFloat(pricePart.replace(',', '.'))
    // Basic date validation: accept YYYY-MM-DD or DD/MM/YYYY
    const isoDate = /^\d{4}-\d{2}-\d{2}$/.test(datePart)
      ? datePart
      : (() => {
          const m = datePart.match(/^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$/)
          return m ? `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}` : null
        })()
    if (!isoDate || isNaN(price) || price <= 0) { invalid.push(line); continue }
    valid.push({ date: isoDate, price, raw: line })
  }
  return { valid, invalid }
}

export function PriceImportModal({
  asset,
  onClose,
  onSaved,
}: {
  asset: Asset
  onClose: () => void
  onSaved: () => void
}) {
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const { valid, invalid } = parseCSV(text)

  const handleSave = async () => {
    if (valid.length === 0) return
    setSaving(true)
    try {
      const result = await assetsApi.importPrices(asset.id, valid.map(r => ({ date: r.date, price: r.price })))
      if (result.errors.length === 0) {
        toast.success(`${result.inserted} precio(s) importado(s)`)
      } else {
        toast.success(`${result.inserted} importado(s), ${result.errors.length} error(es)`)
      }
      onSaved()
      onClose()
    } catch {
      toast.error('Error al importar precios')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl w-full max-w-lg shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <p className="font-semibold text-gray-900 dark:text-white">Importar precios — {asset.ticker}</p>
            <p className="text-xs text-gray-400 mt-0.5">Pega filas con formato <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">fecha,precio</code> (una por línea)</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl ml-4">×</button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            rows={10}
            placeholder={"2025-01-02,123.45\n2025-01-03,124.10\n02/01/2025,123.45"}
            className="w-full font-mono text-xs border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          />

          {text.trim() && (
            <div className="flex gap-4 text-xs">
              <span className="text-emerald-600 dark:text-emerald-400">
                ✓ {valid.length} fila(s) válida(s)
              </span>
              {invalid.length > 0 && (
                <span className="text-red-500">
                  ✗ {invalid.length} fila(s) ignorada(s)
                </span>
              )}
            </div>
          )}

          <p className="text-xs text-gray-400">
            Formatos de fecha aceptados: <code>YYYY-MM-DD</code> o <code>DD/MM/YYYY</code>. Separadores: coma, punto y coma o tabulador. Las filas existentes se sobreescriben.
          </p>
        </div>

        <div className="flex gap-3 px-5 py-4 border-t border-gray-200 dark:border-gray-700">
          <button onClick={onClose}
            className="flex-1 px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={saving || valid.length === 0}
            className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
            {saving ? 'Importando…' : `Importar ${valid.length > 0 ? valid.length : ''} precio(s)`}
          </button>
        </div>
      </div>
    </div>
  )
}
