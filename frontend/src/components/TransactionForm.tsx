import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import type { Asset, Transaction, TransactionCreate } from '../api/client'
import { assetsApi, transactionsApi } from '../api/client'

const BROKERS = [
  { value: 'openbank', label: 'Openbank' },
  { value: 'trade_republic', label: 'Trade Republic' },
  { value: 'revolut', label: 'Revolut' },
  { value: 'degiro', label: 'Degiro' },
]

interface Props {
  existing?: Transaction
  onClose: () => void
  onSaved: () => void
}

export function TransactionForm({ existing, onClose, onSaved }: Props) {
  const today = new Date().toISOString().slice(0, 10)
  const [assets, setAssets] = useState<Asset[]>([])
  const [assetSearch, setAssetSearch] = useState(existing?.asset_ticker ?? '')
  const [assetResults, setAssetResults] = useState<Asset[]>([])
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null)
  const [form, setForm] = useState({
    type: existing?.type ?? 'buy',
    broker: existing?.broker ?? 'degiro',
    shares: existing?.shares?.toString() ?? '',
    price: existing?.price?.toString() ?? '',
    price_eur: existing?.price_eur?.toString() ?? '',
    currency: existing?.currency ?? 'EUR',
    commission: existing?.commission?.toString() ?? '0',
    commission_eur: existing?.commission_eur?.toString() ?? '0',
    date: existing?.date ?? today,
    notes: existing?.notes ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [showNewAsset, setShowNewAsset] = useState(false)
  const [newAsset, setNewAsset] = useState<{ name: string; ticker: string; type: 'stock' | 'etf' | 'fund'; currency: string; manual_price: boolean }>({ name: '', ticker: '', type: 'stock', currency: 'EUR', manual_price: false })

  useEffect(() => {
    assetsApi.list().then(setAssets).catch(() => {})
    if (existing) {
      const found = assets.find(a => a.id === existing.asset_id)
      if (found) setSelectedAsset(found)
    }
  }, [])

  useEffect(() => {
    if (assetSearch.length < 1) { setAssetResults([]); return }
    assetsApi.search(assetSearch).then(setAssetResults)
  }, [assetSearch])

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const handleSelectAsset = (a: Asset) => {
    setSelectedAsset(a)
    setAssetSearch(a.ticker)
    setAssetResults([])
    set('currency', a.currency)
  }

  const handleCreateAsset = async () => {
    try {
      const created = await assetsApi.create({
        ...newAsset,
        market_id: null,
        image_url: null,
      })
      setSelectedAsset(created)
      setAssetSearch(created.ticker)
      setAssetResults([])
      set('currency', created.currency)
      setShowNewAsset(false)
      setAssets(prev => [...prev, created])
      toast.success(`Activo "${created.ticker}" creado`)
    } catch {
      toast.error('Error al crear el activo')
    }
  }

  const handleSave = async () => {
    if (!selectedAsset) { toast.error('Selecciona un activo'); return }
    if (!form.shares || !form.price || !form.price_eur) { toast.error('Rellena precio y participaciones'); return }

    setSaving(true)
    const body: TransactionCreate = {
      asset_id: selectedAsset.id,
      type: form.type as 'buy' | 'sell',
      broker: form.broker,
      shares: Number(form.shares),
      price: Number(form.price),
      price_eur: Number(form.price_eur),
      currency: form.currency,
      commission: Number(form.commission) || 0,
      commission_eur: Number(form.commission_eur) || 0,
      date: form.date,
      notes: form.notes || undefined,
    }

    try {
      if (existing) {
        await transactionsApi.update(existing.id, body)
        toast.success('Transacción actualizada')
      } else {
        await transactionsApi.create(body)
        toast.success('Transacción registrada')
      }
      onSaved()
      onClose()
    } catch {
      toast.error('Error al guardar')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl w-full max-w-lg shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            {existing ? 'Editar transacción' : 'Nueva transacción'}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">×</button>
        </div>

        <div className="p-5 space-y-4">
          {/* Asset search */}
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Activo</label>
            <div className="relative">
              <input
                type="text"
                value={assetSearch}
                onChange={e => { setAssetSearch(e.target.value); setSelectedAsset(null) }}
                placeholder="Buscar ticker o nombre..."
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
              {assetResults.length > 0 && (
                <ul className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg text-sm">
                  {assetResults.map(a => (
                    <li
                      key={a.id}
                      onClick={() => handleSelectAsset(a)}
                      className="px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-600 cursor-pointer"
                    >
                      <span className="font-mono font-medium">{a.ticker}</span>
                      <span className="text-gray-500 ml-2">{a.name}</span>
                    </li>
                  ))}
                  <li
                    onClick={() => setShowNewAsset(true)}
                    className="px-3 py-2 text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 cursor-pointer border-t border-gray-100 dark:border-gray-600"
                  >
                    + Crear nuevo activo "{assetSearch}"
                  </li>
                </ul>
              )}
            </div>
            {selectedAsset && (
              <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                ✓ {selectedAsset.name} ({selectedAsset.currency})
              </p>
            )}
          </div>

          {/* New asset inline form */}
          {showNewAsset && (
            <div className="border border-blue-200 dark:border-blue-800 rounded-lg p-4 bg-blue-50 dark:bg-blue-900/20 space-y-3">
              <p className="text-sm font-medium text-blue-700 dark:text-blue-300">Nuevo activo</p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Ticker / ISIN</label>
                  <input
                    type="text"
                    value={newAsset.ticker || assetSearch}
                    onChange={e => setNewAsset(a => ({ ...a, ticker: e.target.value }))}
                    className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Nombre</label>
                  <input
                    type="text"
                    value={newAsset.name}
                    onChange={e => setNewAsset(a => ({ ...a, name: e.target.value }))}
                    className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Tipo</label>
                  <select
                    value={newAsset.type}
                    onChange={e => setNewAsset(a => ({ ...a, type: e.target.value as 'stock' | 'etf' | 'fund' }))}
                    className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  >
                    <option value="stock">Stock</option>
                    <option value="etf">ETF</option>
                    <option value="fund">Fondo</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Divisa</label>
                  <input
                    type="text"
                    value={newAsset.currency}
                    onChange={e => setNewAsset(a => ({ ...a, currency: e.target.value.toUpperCase() }))}
                    className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    maxLength={3}
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                <input
                  type="checkbox"
                  checked={newAsset.manual_price}
                  onChange={e => setNewAsset(a => ({ ...a, manual_price: e.target.checked }))}
                />
                Precio manual (Fondo sin precio automático)
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowNewAsset(false)}
                  className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded text-gray-600 dark:text-gray-400 hover:bg-gray-50"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleCreateAsset}
                  className="flex-1 px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                  Crear activo
                </button>
              </div>
            </div>
          )}

          {/* Type + Broker */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Operación</label>
              <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden">
                {(['buy', 'sell'] as const).map(t => (
                  <button
                    key={t}
                    onClick={() => set('type', t)}
                    className={`flex-1 py-2 text-sm font-medium transition-colors ${
                      form.type === t
                        ? t === 'buy'
                          ? 'bg-green-500 text-white'
                          : 'bg-red-500 text-white'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
                    }`}
                  >
                    {t === 'buy' ? 'Compra' : 'Venta'}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Broker</label>
              <select
                value={form.broker}
                onChange={e => set('broker', e.target.value)}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              >
                {BROKERS.map(b => <option key={b.value} value={b.value}>{b.label}</option>)}
              </select>
            </div>
          </div>

          {/* Shares + Date */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Participaciones</label>
              <input
                type="number" step="0.0001" min="0"
                value={form.shares}
                onChange={e => set('shares', e.target.value)}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Fecha</label>
              <input
                type="date"
                value={form.date}
                max={today}
                onChange={e => set('date', e.target.value)}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
          </div>

          {/* Price fields */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                Precio ({form.currency})
              </label>
              <input
                type="number" step="0.0001" min="0"
                value={form.price}
                onChange={e => set('price', e.target.value)}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Precio (€)</label>
              <input
                type="number" step="0.0001" min="0"
                value={form.price_eur}
                onChange={e => set('price_eur', e.target.value)}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
          </div>

          {/* Commission */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                Comisión ({form.currency})
              </label>
              <input
                type="number" step="0.01" min="0"
                value={form.commission}
                onChange={e => set('commission', e.target.value)}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Comisión (€)</label>
              <input
                type="number" step="0.01" min="0"
                value={form.commission_eur}
                onChange={e => set('commission_eur', e.target.value)}
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Notas (opcional)</label>
            <input
              type="text"
              value={form.notes}
              onChange={e => set('notes', e.target.value)}
              className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
        </div>

        <div className="flex gap-3 p-5 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? 'Guardando...' : existing ? 'Actualizar' : 'Registrar'}
          </button>
        </div>
      </div>
    </div>
  )
}
