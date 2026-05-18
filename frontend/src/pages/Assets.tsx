import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import type { Asset, Market } from '../api/client'
import { assetsApi, pricesApi } from '../api/client'
import { AssetDetailDrawer } from '../components/AssetDetailDrawer'
import { AssetLogo } from '../components/AssetLogo'
import { ManualPriceModal } from '../components/ManualPriceModal'

interface EditDraft {
  name: string
  isin: string
  market_id: number | null
  manual_price: boolean
  image_url: string
}

function EditModal({
  asset, markets, onClose, onSaved,
}: {
  asset: Asset; markets: Market[]; onClose: () => void; onSaved: () => void
}) {
  const [draft, setDraft] = useState<EditDraft>({
    name: asset.name,
    isin: asset.isin ?? '',
    market_id: asset.market_id,
    manual_price: asset.manual_price,
    image_url: asset.image_url ?? '',
  })
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      await assetsApi.update(asset.id, {
        name: draft.name || undefined,
        isin: draft.isin.trim().toUpperCase() || null,
        market_id: draft.market_id,
        manual_price: draft.manual_price,
        image_url: draft.image_url.trim() || null,
      })
      toast.success('Activo actualizado')
      onSaved()
      onClose()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'Error al guardar')
    } finally {
      setSaving(false)
    }
  }

  const inputCls = "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
  const labelCls = "block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl w-full max-w-md shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <AssetLogo asset={{ ...asset, image_url: draft.image_url || null }} />
            <div>
              <p className="font-semibold text-gray-900 dark:text-white">{asset.ticker}</p>
              <p className="text-xs text-gray-400">{asset.type.toUpperCase()} · {asset.currency}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">×</button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <div>
            <label className={labelCls}>Nombre</label>
            <input value={draft.name} onChange={e => setDraft(d => ({ ...d, name: e.target.value }))}
              className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>ISIN</label>
            <input value={draft.isin} onChange={e => setDraft(d => ({ ...d, isin: e.target.value.toUpperCase() }))}
              className={`${inputCls} font-mono`} maxLength={12} placeholder="ES0170960015" />
          </div>
          <div>
            <label className={labelCls}>Mercado</label>
            <select value={draft.market_id ?? ''} onChange={e => setDraft(d => ({ ...d, market_id: e.target.value ? Number(e.target.value) : null }))}
              className={inputCls}>
              <option value="">Sin asignar</option>
              {markets.map(m => <option key={m.id} value={m.id}>{m.name} ({m.country})</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls}>URL imagen (logo)</label>
            <input value={draft.image_url} onChange={e => setDraft(d => ({ ...d, image_url: e.target.value }))}
              className={inputCls} placeholder="https://…" />
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-pointer pt-1">
            <input type="checkbox" checked={draft.manual_price}
              onChange={e => setDraft(d => ({ ...d, manual_price: e.target.checked }))}
              className="rounded" />
            Precio manual (desactiva fetch automático)
          </label>
        </div>

        <div className="flex gap-3 px-5 py-4 border-t border-gray-200 dark:border-gray-700">
          <button onClick={onClose}
            className="flex-1 px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
            Cancelar
          </button>
          <button onClick={save} disabled={saving}
            className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
            {saving ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function AssetsPage() {
  const [assets, setAssets] = useState<Asset[]>([])
  const [markets, setMarkets] = useState<Market[]>([])
  const [loading, setLoading] = useState(true)
  const [editAsset, setEditAsset] = useState<Asset | null>(null)
  const [priceAsset, setPriceAsset] = useState<Asset | null>(null)
  const [detailAsset, setDetailAsset] = useState<Asset | null>(null)
  const [refreshingId, setRefreshingId] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  const load = () => {
    setLoading(true)
    Promise.all([assetsApi.list(), assetsApi.markets()])
      .then(([a, m]) => { setAssets(a); setMarkets(m) })
      .catch(() => toast.error('Error al cargar activos'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (asset: Asset) => {
    if (!confirm(`¿Eliminar "${asset.ticker}"? Esta acción no se puede deshacer.`)) return
    try {
      await assetsApi.delete(asset.id)
      toast.success(`"${asset.ticker}" eliminado`)
      load()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'Error al eliminar')
    }
  }

  const handleRefreshPrice = async (asset: Asset) => {
    setRefreshingId(asset.id)
    try {
      await pricesApi.refreshAsset(asset.id)
      toast.success(`Precio de ${asset.ticker} actualizado`)
    } catch {
      toast.error('Error al actualizar precio')
    } finally {
      setRefreshingId(null)
    }
  }

  const filtered = assets.filter(a => {
    const q = search.toLowerCase()
    return !q || a.ticker.toLowerCase().includes(q) || a.name.toLowerCase().includes(q) || (a.isin ?? '').toLowerCase().includes(q)
  })

  const marketName = (id: number | null) => markets.find(m => m.id === id)?.mic ?? '—'

  const typeBadge = (type: string) => {
    const cls: Record<string, string> = {
      stock: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
      etf:   'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
      fund:  'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    }
    return (
      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls[type] ?? ''}`}>
        {type.toUpperCase()}
      </span>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Activos</h1>
        <input
          value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Filtrar por ticker, nombre o ISIN…"
          className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 w-72"
        />
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-700">
                {['Activo', 'ISIN', 'Tipo', 'Divisa', 'Mercado', 'Precio', ''].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="text-center py-12 text-gray-400">Cargando…</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={7} className="text-center py-12 text-gray-400 text-sm">
                  {assets.length === 0 ? 'No hay activos. Crea uno desde el formulario de transacciones.' : 'Sin resultados.'}
                </td></tr>
              ) : filtered.map(asset => (
                <tr
                  key={asset.id}
                  onClick={() => setDetailAsset(asset)}
                  className="border-b border-gray-50 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors cursor-pointer"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <AssetLogo asset={asset} />
                      <div>
                        <p className="font-medium text-gray-900 dark:text-white">{asset.name}</p>
                        <p className="text-xs font-mono text-gray-400">{asset.ticker}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">{asset.isin ?? '—'}</td>
                  <td className="px-4 py-3">{typeBadge(asset.type)}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{asset.currency}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{marketName(asset.market_id)}</td>
                  <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                    {asset.manual_price ? (
                      <button onClick={() => setPriceAsset(asset)}
                        className="text-xs text-amber-500 hover:text-amber-600 underline whitespace-nowrap">
                        ✎ Manual
                      </button>
                    ) : (
                      <button onClick={() => handleRefreshPrice(asset)} disabled={refreshingId === asset.id}
                        className="text-xs text-blue-500 hover:text-blue-600 disabled:opacity-40 whitespace-nowrap">
                        {refreshingId === asset.id ? '↻ …' : '↻ Auto'}
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                    <div className="flex items-center gap-2 justify-end">
                      <button onClick={() => setEditAsset(asset)}
                        className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
                        Editar
                      </button>
                      <button onClick={() => handleDelete(asset)}
                        className="text-xs px-2 py-1 rounded border border-red-200 dark:border-red-800 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20">
                        Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {editAsset && (
        <EditModal asset={editAsset} markets={markets}
          onClose={() => setEditAsset(null)} onSaved={load} />
      )}

      {priceAsset && (
        <ManualPriceModal
          asset={{ asset_id: priceAsset.id, ticker: priceAsset.ticker, currency: priceAsset.currency }}
          onClose={() => setPriceAsset(null)}
          onSaved={load}
        />
      )}

      {detailAsset && (
        <AssetDetailDrawer
          asset={detailAsset}
          onClose={() => setDetailAsset(null)}
        />
      )}
    </div>
  )
}
