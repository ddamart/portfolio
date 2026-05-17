import { useState } from 'react'
import type { HoldingRow } from '../api/client'
import { assetsApi } from '../api/client'
import toast from 'react-hot-toast'

interface Props {
  asset: HoldingRow
  onClose: () => void
  onSaved: () => void
}

export function ManualPriceModal({ asset, onClose, onSaved }: Props) {
  const today = new Date().toISOString().slice(0, 10)
  const [price, setPrice] = useState('')
  const [priceDate, setPriceDate] = useState(today)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (!price || isNaN(Number(price))) return
    setSaving(true)
    try {
      await assetsApi.setManualPrice(asset.asset_id, Number(price), priceDate, asset.currency)
      toast.success('Precio actualizado')
      onSaved()
      onClose()
    } catch {
      toast.error('Error al guardar el precio')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 w-full max-w-sm shadow-xl">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Precio manual — {asset.ticker}
        </h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Precio ({asset.currency})</label>
            <input
              type="number"
              step="0.0001"
              value={price}
              onChange={e => setPrice(e.target.value)}
              className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              placeholder="0.00"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Fecha</label>
            <input
              type="date"
              value={priceDate}
              max={today}
              onChange={e => setPriceDate(e.target.value)}
              className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
        </div>
        <div className="flex gap-2 mt-6">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancelar
          </button>
          <button
            onClick={save}
            disabled={saving || !price}
            className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? 'Guardando...' : 'Guardar'}
          </button>
        </div>
      </div>
    </div>
  )
}
