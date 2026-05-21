import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import type { Asset, AssetLookup, Market } from '../api/client'
import { assetsApi, pricesApi } from '../api/client'
import { AssetDetailDrawer } from '../components/AssetDetailDrawer'
import { AssetLogo } from '../components/AssetLogo'
import { BalanceDrawer } from '../components/BalanceDrawer'
import { ManualPriceModal } from '../components/ManualPriceModal'

const MARKET_CURRENCY: Record<string, string> = {
  XETR: 'EUR', XAMS: 'EUR', XMAD: 'EUR', CNMV: 'EUR',
  XLON: 'GBX', XNYS: 'USD', XNAS: 'USD', XSTO: 'SEK',
}

interface CreateDraft {
  ticker: string
  isin: string
  name: string
  type: 'stock' | 'etf' | 'fund' | 'balance'
  market_id: number | null
  currency: string
  manual_price: boolean
  image_url: string
}

const DEFAULT_CREATE: CreateDraft = {
  ticker: '', isin: '', name: '', type: 'stock', market_id: null, currency: 'EUR',
  manual_price: false, image_url: '',
}

function CreateAssetModal({
  markets, onClose, onSaved,
}: { markets: Market[]; onClose: () => void; onSaved: () => void }) {
  const [query, setQuery] = useState('')
  const [lookupResult, setLookupResult] = useState<AssetLookup | null>(null)
  const [lookingUp, setLookingUp] = useState(false)
  const [draft, setDraft] = useState<CreateDraft>(DEFAULT_CREATE)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) { setLookupResult(null); return }
    setLookingUp(true)
    const t = setTimeout(() => {
      assetsApi.lookup(q)
        .then(r => {
          setLookupResult(r)
          setDraft({
            ticker:       r.ticker,
            isin:         r.isin ?? '',
            name:         r.name,
            type:         r.type,
            market_id:    r.market_id,
            currency:     r.currency,
            manual_price: !r.found,
            image_url:    r.image_url ?? '',
          })
        })
        .catch(() => {
          setLookupResult(null)
          setDraft(d => ({ ...d, ticker: q }))
        })
        .finally(() => setLookingUp(false))
    }, 600)
    return () => clearTimeout(t)
  }, [query])

  const handleMarketChange = (marketId: number | null) => {
    const mic = markets.find(m => m.id === marketId)?.mic ?? ''
    setDraft(d => ({ ...d, market_id: marketId, currency: MARKET_CURRENCY[mic] ?? d.currency }))
  }

  const save = async () => {
    if (!draft.ticker.trim()) { toast.error('El ticker es obligatorio'); return }
    setSaving(true)
    try {
      await assetsApi.create({
        name:         draft.name || draft.ticker,
        ticker:       draft.ticker.trim().toUpperCase(),
        type:         draft.type,
        currency:     draft.type === 'balance' ? 'EUR' : draft.currency,
        market_id:    draft.type === 'balance' ? null : draft.market_id,
        image_url:    draft.image_url.trim() || null,
        manual_price: draft.type === 'balance' ? true : draft.manual_price,
        isin:         draft.isin.trim().toUpperCase() || null,
      })
      toast.success(`Activo "${draft.ticker.toUpperCase()}" creado`)
      onSaved()
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const msg = typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((e: { msg?: string }) => e.msg).filter(Boolean).join('; ')
          : 'Error al crear el activo'
      toast.error(msg)
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
          <h2 className="font-semibold text-gray-900 dark:text-white">Nuevo activo</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">×</button>
        </div>

        <div className="px-5 py-4 space-y-3">
          {/* Lookup */}
          <div>
            <label className={labelCls}>Buscar por ISIN o ticker</label>
            <div className="relative">
              <input
                value={query}
                onChange={e => setQuery(e.target.value.toUpperCase())}
                placeholder="ES0170960015 · AAPL · SOI.PA…"
                className={`${inputCls} font-mono pr-8`}
                autoFocus
              />
              {lookingUp && (
                <span className="absolute right-2 top-2 text-gray-400 text-xs animate-spin">↻</span>
              )}
            </div>
            {lookupResult && !lookingUp && (
              <div className={`mt-1 text-xs px-2 py-1 rounded flex items-center gap-1.5 ${
                lookupResult.found
                  ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                  : 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300'
              }`}>
                <span>{lookupResult.found ? '✓' : '⚠'}</span>
                <span>{lookupResult.found ? `Encontrado: ${lookupResult.name}` : 'No encontrado — rellena los campos manualmente'}</span>
              </div>
            )}
          </div>

          {/* Fields */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Ticker</label>
              <input value={draft.ticker} onChange={e => setDraft(d => ({ ...d, ticker: e.target.value.toUpperCase() }))}
                className={`${inputCls} font-mono`} placeholder="AAPL" />
            </div>
            <div>
              <label className={labelCls}>ISIN</label>
              <input value={draft.isin} onChange={e => setDraft(d => ({ ...d, isin: e.target.value.toUpperCase() }))}
                className={`${inputCls} font-mono`} maxLength={12} placeholder="US0378331005" />
            </div>
          </div>
          <div>
            <label className={labelCls}>Nombre</label>
            <input value={draft.name} onChange={e => setDraft(d => ({ ...d, name: e.target.value }))}
              className={inputCls} placeholder="Apple Inc." />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Tipo</label>
              <select
                value={draft.type}
                onChange={e => {
                  const t = e.target.value as CreateDraft['type']
                  setDraft(d => ({ ...d, type: t, manual_price: t === 'balance' ? true : d.manual_price }))
                }}
                className={inputCls}
              >
                <option value="stock">Acción</option>
                <option value="etf">ETF</option>
                <option value="fund">Fondo</option>
                <option value="balance">Cartera / Cuenta</option>
              </select>
            </div>
            {draft.type !== 'balance' && (
              <div>
                <label className={labelCls}>Divisa</label>
                <input value={draft.currency} onChange={e => setDraft(d => ({ ...d, currency: e.target.value.toUpperCase() }))}
                  className={`${inputCls} font-mono`} maxLength={3} placeholder="EUR" />
              </div>
            )}
          </div>
          {draft.type !== 'balance' && (
            <div>
              <label className={labelCls}>Mercado</label>
              <select value={draft.market_id ?? ''} onChange={e => handleMarketChange(e.target.value ? Number(e.target.value) : null)}
                className={inputCls}>
                <option value="">Sin asignar</option>
                {markets.map(m => <option key={m.id} value={m.id}>{m.name} ({m.country})</option>)}
              </select>
            </div>
          )}
          {draft.type === 'balance' ? (
            <p className="text-xs text-gray-400 dark:text-gray-500 pt-1">
              Las carteras/cuentas se valoran mediante aportaciones y snapshots manuales, sin cotización de mercado.
            </p>
          ) : (
            <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-pointer pt-1">
              <input type="checkbox" checked={draft.manual_price}
                onChange={e => setDraft(d => ({ ...d, manual_price: e.target.checked }))}
                className="rounded" />
              Precio manual (desactiva fetch automático)
            </label>
          )}
        </div>

        <div className="flex gap-3 px-5 py-4 border-t border-gray-200 dark:border-gray-700">
          <button onClick={onClose}
            className="flex-1 px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
            Cancelar
          </button>
          <button onClick={save} disabled={saving || !draft.ticker.trim()}
            className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
            {saving ? 'Creando…' : 'Crear activo'}
          </button>
        </div>
      </div>
    </div>
  )
}

interface EditDraft {
  name: string
  ticker: string
  currency: string
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
    ticker: asset.ticker,
    currency: asset.currency,
    isin: asset.isin ?? '',
    market_id: asset.market_id,
    manual_price: asset.manual_price,
    image_url: asset.image_url ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)

  const syncMetadata = async () => {
    setSyncing(true)
    try {
      const meta = await assetsApi.metadata(asset.ticker)
      setDraft(d => ({
        ...d,
        name: meta.name,
        image_url: meta.image_url ?? d.image_url,
      }))
      toast.success('Metadatos sincronizados desde yfinance')
    } catch {
      toast.error('No se pudieron obtener los metadatos')
    } finally {
      setSyncing(false)
    }
  }

  const save = async () => {
    setSaving(true)
    try {
      await assetsApi.update(asset.id, {
        name: draft.name || undefined,
        ticker: draft.ticker.trim().toUpperCase() || undefined,
        currency: draft.currency || undefined,
        isin: draft.isin.trim().toUpperCase() || null,
        market_id: draft.market_id,
        manual_price: draft.manual_price,
        image_url: draft.image_url.trim() || null,
      })
      toast.success('Activo actualizado')
      onSaved()
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((e: { msg?: string }) => e.msg).filter(Boolean).join('; ') : 'Error al guardar'
      toast.error(msg)
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
            <div className="flex items-center justify-between mb-1">
              <label className={labelCls} style={{ marginBottom: 0 }}>Nombre</label>
              <button
                onClick={syncMetadata}
                disabled={syncing || asset.type === 'fund'}
                title={asset.type === 'fund' ? 'No disponible para fondos' : 'Obtener nombre e imagen desde yfinance'}
                className="text-xs text-blue-500 hover:text-blue-600 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {syncing ? '↻ Sincronizando…' : '↻ Sync desde yfinance'}
              </button>
            </div>
            <input value={draft.name} onChange={e => setDraft(d => ({ ...d, name: e.target.value }))}
              className={inputCls} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Ticker</label>
              <input value={draft.ticker} onChange={e => setDraft(d => ({ ...d, ticker: e.target.value.toUpperCase() }))}
                className={`${inputCls} font-mono`} placeholder="SOI.PA" />
            </div>
            <div>
              <label className={labelCls}>Divisa</label>
              <input value={draft.currency} onChange={e => setDraft(d => ({ ...d, currency: e.target.value.toUpperCase() }))}
                className={`${inputCls} font-mono`} maxLength={3} placeholder="EUR" />
            </div>
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
  const [showCreate, setShowCreate] = useState(false)
  const [refreshingId, setRefreshingId] = useState<number | null>(null)
  const [clearingPricesId, setClearingPricesId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [onlyPortfolio, setOnlyPortfolio] = useState(false)

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
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((e: { msg?: string }) => e.msg).filter(Boolean).join('; ') : 'Error al eliminar'
      toast.error(msg)
    }
  }

  const handleClearPrices = async (asset: Asset) => {
    const isBalance = asset.type === 'balance'
    const confirmMsg = isBalance
      ? `¿Borrar todas las entradas (valoraciones, aportaciones, retiradas) de "${asset.ticker}"?`
      : `¿Borrar todo el historial de precios de "${asset.ticker}"?`
    if (!confirm(confirmMsg)) return
    setClearingPricesId(asset.id)
    try {
      await assetsApi.clearPrices(asset.id)
      if (isBalance) {
        toast.success(`Entradas de ${asset.ticker} borradas`)
        load()
      } else if (!asset.manual_price) {
        await pricesApi.refreshAsset(asset.id)
        toast.success(`Precios de ${asset.ticker} borrados y recargados`)
      } else {
        toast.success(`Historial de precios de ${asset.ticker} borrado`)
      }
    } catch {
      toast.error(isBalance ? 'Error al borrar las entradas' : 'Error al borrar los precios')
    } finally {
      setClearingPricesId(null)
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
    const matchSearch = !q || a.ticker.toLowerCase().includes(q) || a.name.toLowerCase().includes(q) || (a.isin ?? '').toLowerCase().includes(q)
    return matchSearch && (!onlyPortfolio || a.in_portfolio)
  })

  const marketName = (id: number | null) => markets.find(m => m.id === id)?.mic ?? '—'

  const typeBadge = (type: string) => {
    const cls: Record<string, string> = {
      stock:   'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
      etf:     'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
      fund:    'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
      balance: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    }
    const label: Record<string, string> = {
      stock: 'Stock', etf: 'ETF', fund: 'Fondo', balance: 'Cartera',
    }
    return (
      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls[type] ?? ''}`}>
        {label[type] ?? type.toUpperCase()}
      </span>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Activos</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setOnlyPortfolio(v => !v)}
            className={`text-xs px-3 py-1.5 rounded-full border font-medium transition-colors ${
              onlyPortfolio
                ? 'bg-emerald-100 border-emerald-300 text-emerald-700 dark:bg-emerald-900/40 dark:border-emerald-700 dark:text-emerald-300'
                : 'border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-gray-400'
            }`}
          >
            En cartera
          </button>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Filtrar por ticker, nombre o ISIN…"
            className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 w-72"
          />
          <button
            onClick={() => setShowCreate(true)}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium whitespace-nowrap"
          >
            + Nuevo activo
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-700">
                {['Activo', 'ISIN', 'Tipo', 'Cartera', 'Divisa', 'Mercado', 'Precio', ''].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="text-center py-12 text-gray-400">Cargando…</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={8} className="text-center py-12 text-gray-400 text-sm">
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
                  <td className="px-4 py-3">
                    {asset.in_portfolio ? (
                      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300 font-medium">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
                        Sí
                      </span>
                    ) : (
                      <span className="text-gray-300 dark:text-gray-600 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{asset.currency}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{marketName(asset.market_id)}</td>
                  <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                    <div className="flex flex-col gap-0.5">
                      {asset.manual_price ? (
                        <button onClick={() => setPriceAsset(asset)}
                          className="text-xs text-amber-500 hover:text-amber-600 underline whitespace-nowrap text-left">
                          ✎ Manual
                        </button>
                      ) : (
                        <button onClick={() => handleRefreshPrice(asset)} disabled={refreshingId === asset.id}
                          className="text-xs text-blue-500 hover:text-blue-600 disabled:opacity-40 whitespace-nowrap text-left">
                          {refreshingId === asset.id ? '↻ …' : '↻ Auto'}
                        </button>
                      )}
                      <button
                        onClick={() => handleClearPrices(asset)}
                        disabled={clearingPricesId === asset.id}
                        className="text-xs text-gray-400 hover:text-red-500 disabled:opacity-40 whitespace-nowrap text-left"
                      >
                        {clearingPricesId === asset.id ? '…' : asset.type === 'balance' ? 'Borrar entradas' : 'Borrar precios'}
                      </button>
                    </div>
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

      {showCreate && (
        <CreateAssetModal markets={markets}
          onClose={() => setShowCreate(false)} onSaved={load} />
      )}

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
        detailAsset.type === 'balance'
          ? <BalanceDrawer asset={detailAsset} onClose={() => setDetailAsset(null)} />
          : <AssetDetailDrawer asset={detailAsset} onClose={() => setDetailAsset(null)} />
      )}
    </div>
  )
}
