import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import type { Asset, AssetMeta, Market, Transaction, TransactionCreate } from '../api/client'
import { assetsApi, pricesApi, transactionsApi } from '../api/client'

const BROKERS = [
  { value: 'openbank',        label: 'Openbank' },
  { value: 'trade_republic',  label: 'Trade Republic' },
  { value: 'revolut',         label: 'Revolut' },
  { value: 'degiro',          label: 'Degiro' },
]

const ASSET_TYPES = [
  { value: 'stock', label: 'Acción' },
  { value: 'etf',   label: 'ETF' },
  { value: 'fund',  label: 'Fondo' },
]

const CURRENCIES = [
  'EUR', 'USD', 'GBP', 'CHF', 'SEK', 'DKK', 'NOK',
  'JPY', 'CAD', 'AUD', 'HKD', 'SGD', 'MXN', 'BRL', 'PLN',
]

// Default currency per market MIC
const MARKET_CURRENCY: Record<string, string> = {
  XETR: 'EUR', XAMS: 'EUR', XMAD: 'EUR', CNMV: 'EUR',
  XLON: 'GBP',
  XNYS: 'USD', XNAS: 'USD',
}

interface Props {
  existing?: Transaction
  onClose: () => void
  onSaved: () => void
}

interface NewAssetDraft {
  ticker: string
  isin: string
  name: string
  type: 'stock' | 'etf' | 'fund'
  market_id: number | null
  currency: string
  manual_price: boolean
}

export function TransactionForm({ existing, onClose, onSaved }: Props) {
  const today = new Date().toISOString().slice(0, 10)

  // --- asset selection ---
  const [assetQuery, setAssetQuery] = useState(existing?.asset_ticker ?? '')
  const [assetResults, setAssetResults] = useState<Asset[]>([])
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null)
  const [showNewAsset, setShowNewAsset] = useState(false)
  const [newAsset, setNewAsset] = useState<NewAssetDraft>({
    ticker: '', isin: '', name: '', type: 'stock', market_id: null, currency: 'EUR', manual_price: false,
  })
  const [markets, setMarkets] = useState<Market[]>([])
  const [creatingAsset, setCreatingAsset] = useState(false)
  const [tickerMeta, setTickerMeta] = useState<AssetMeta | null>(null)
  const [fetchingMeta, setFetchingMeta] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // --- transaction fields ---
  const [txType, setTxType]     = useState<'buy' | 'sell'>(existing?.type ?? 'buy')
  const [broker, setBroker]     = useState(existing?.broker ?? 'degiro')
  const [date, setDate]         = useState(existing?.date ?? today)
  const [shares, setShares]     = useState(existing?.shares?.toString() ?? '')
  const [price, setPrice]       = useState(existing?.price?.toString() ?? '')
  const [currency, setCurrency] = useState(existing?.currency ?? 'EUR')
  const [commission, setCommission] = useState(existing?.commission?.toString() ?? '0')
  const [notes, setNotes]       = useState(existing?.notes ?? '')
  const [saving, setSaving]     = useState(false)

  // --- EUR rate hint ---
  const [eurRate, setEurRate] = useState<number | null>(currency === 'EUR' ? 1 : null)

  // Load markets once
  useEffect(() => {
    assetsApi.markets().then(setMarkets).catch(() => {})
  }, [])

  // Pre-select asset when editing
  useEffect(() => {
    if (!existing) return
    assetsApi.search(existing.asset_ticker).then(results => {
      const found = results.find(a => a.id === existing.asset_id)
      if (found) setSelectedAsset(found)
    }).catch(() => {})
  }, [])

  // Search assets as user types
  useEffect(() => {
    if (assetQuery.length < 1) { setAssetResults([]); return }
    if (selectedAsset) return  // don't search when an asset is already selected
    assetsApi.search(assetQuery).then(setAssetResults).catch(() => {})
  }, [assetQuery, selectedAsset])

  // Fetch ticker metadata (name, currency, logo) when user types a ticker in the new-asset form
  useEffect(() => {
    const t = newAsset.ticker.trim()
    if (!showNewAsset || !t || t.length < 1 || newAsset.manual_price) {
      setTickerMeta(null)
      return
    }
    setFetchingMeta(true)
    const timer = setTimeout(() => {
      assetsApi.metadata(t)
        .then(meta => {
          setTickerMeta(meta)
          // Auto-fill name and currency only if user hasn't typed them manually
          setNewAsset(d => ({
            ...d,
            name: d.name || meta.name,
            currency: meta.currency || d.currency,
          }))
        })
        .catch(() => setTickerMeta(null))
        .finally(() => setFetchingMeta(false))
    }, 600)
    return () => clearTimeout(timer)
  }, [newAsset.ticker, showNewAsset, newAsset.manual_price])

  // Fetch EUR rate whenever currency or date changes
  useEffect(() => {
    if (currency === 'EUR') { setEurRate(1); return }
    pricesApi.fxRate(currency, date)
      .then(r => setEurRate(r.rate))
      .catch(() => setEurRate(null))
  }, [currency, date])

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setAssetResults([])
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSelectAsset = (a: Asset) => {
    setSelectedAsset(a)
    setAssetQuery(a.ticker)
    setAssetResults([])
    setCurrency(a.currency)
    setShowNewAsset(false)
  }

  const handleOpenNewAsset = () => {
    setAssetResults([])
    const q = assetQuery.toUpperCase()
    const isIsin = /^[A-Z]{2}[A-Z0-9]{10}$/.test(q)
    setNewAsset(d => ({
      ...d,
      ticker: isIsin ? '' : q,
      isin:   isIsin ? q  : '',
      type:   isIsin && q.startsWith('ES') ? 'fund' : d.type,
    }))
    setShowNewAsset(true)
  }

  const handleMarketChange = (marketId: number | null) => {
    setNewAsset(d => {
      const mic = markets.find(m => m.id === marketId)?.mic ?? ''
      return { ...d, market_id: marketId, currency: MARKET_CURRENCY[mic] ?? d.currency }
    })
  }

  const handleCreateAsset = async () => {
    if (!newAsset.ticker) { toast.error('El ticker es obligatorio'); return }
    setCreatingAsset(true)
    try {
      const created = await assetsApi.create({
        name: newAsset.name || newAsset.ticker,
        ticker: newAsset.ticker.toUpperCase(),
        type: newAsset.type,
        currency: newAsset.currency,
        market_id: newAsset.market_id,
        image_url: null,
        manual_price: newAsset.manual_price,
        isin: newAsset.isin.trim().toUpperCase() || null,
      })
      handleSelectAsset(created)
      toast.success(`Activo "${created.ticker}" creado`)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'Error al crear el activo')
    } finally {
      setCreatingAsset(false)
    }
  }

  const handleSave = async () => {
    if (!selectedAsset) { toast.error('Selecciona un activo'); return }
    const sharesN = parseFloat(shares)
    const priceN  = parseFloat(price)
    if (!sharesN || !priceN) { toast.error('Participaciones y precio son obligatorios'); return }

    setSaving(true)
    const body: TransactionCreate = {
      asset_id:   selectedAsset.id,
      type:       txType,
      broker,
      shares:     sharesN,
      price:      priceN,
      currency,
      commission: parseFloat(commission) || 0,
      date,
      notes:      notes || undefined,
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
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'Error al guardar')
    } finally {
      setSaving(false)
    }
  }

  const priceEur      = eurRate != null && price      ? parseFloat(price) * eurRate      : null
  const commissionEur = eurRate != null && commission ? parseFloat(commission) * eurRate : null
  const eurHint = (v: number | null) =>
    v != null && currency !== 'EUR'
      ? <span className="text-xs text-gray-400 mt-0.5 block">≈ {v.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 4 })} €</span>
      : null

  const inputCls = "w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
  const labelCls = "block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl w-full max-w-lg shadow-xl max-h-[92vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700 shrink-0">
          <h3 className="text-base font-semibold text-gray-900 dark:text-white">
            {existing ? 'Editar transacción' : 'Nueva transacción'}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-5 py-4 space-y-4">

          {/* ── Asset ─────────────────────────────────── */}
          <div>
            <label className={labelCls}>Activo</label>
            <div className="relative" ref={dropdownRef}>
              <input
                type="text"
                value={assetQuery}
                onChange={e => { setAssetQuery(e.target.value); setSelectedAsset(null); setShowNewAsset(false) }}
                placeholder="Buscar por ticker o nombre…"
                className={inputCls}
                autoFocus={!existing}
              />
              {/* Dropdown */}
              {assetResults.length > 0 && !showNewAsset && (
                <ul className="absolute z-20 w-full mt-1 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg text-sm max-h-48 overflow-y-auto">
                  {assetResults.map(a => (
                    <li key={a.id} onMouseDown={() => handleSelectAsset(a)}
                      className="px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-600 cursor-pointer flex items-center gap-2">
                      <span className="font-mono font-medium text-gray-900 dark:text-white">{a.ticker}</span>
                      <span className="text-gray-500 truncate">{a.name}</span>
                      <span className="ml-auto text-xs text-gray-400">{a.currency}</span>
                    </li>
                  ))}
                  <li onMouseDown={handleOpenNewAsset}
                    className="px-3 py-2 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 cursor-pointer border-t border-gray-100 dark:border-gray-600 font-medium">
                    + Crear activo "{assetQuery}"
                  </li>
                </ul>
              )}
              {assetQuery && assetResults.length === 0 && !selectedAsset && !showNewAsset && (
                <div className="absolute z-20 w-full mt-1 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg text-sm">
                  <div onMouseDown={handleOpenNewAsset}
                    className="px-3 py-2.5 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 cursor-pointer font-medium">
                    + Crear activo "{assetQuery}"
                  </div>
                </div>
              )}
            </div>
            {selectedAsset && (
              <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                ✓ {selectedAsset.name} · {selectedAsset.type.toUpperCase()} · {selectedAsset.currency}
              </p>
            )}
          </div>

          {/* ── New asset inline form ─────────────────── */}
          {showNewAsset && (
            <div className="border border-blue-200 dark:border-blue-800 rounded-xl p-4 bg-blue-50/50 dark:bg-blue-900/20 space-y-3">
              <p className="text-sm font-semibold text-blue-700 dark:text-blue-300">Nuevo activo</p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>Ticker</label>
                  <div className="flex items-center gap-2">
                    {tickerMeta?.image_url && (
                      <img src={tickerMeta.image_url} alt="" className="w-7 h-7 rounded-full object-contain shrink-0"
                        onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                    )}
                    <input value={newAsset.ticker}
                      onChange={e => { setNewAsset(d => ({ ...d, ticker: e.target.value.toUpperCase(), name: '' })); setTickerMeta(null) }}
                      className={`${inputCls} flex-1`} placeholder="AAPL · VWCE.DE · BNP1" />
                  </div>
                  {fetchingMeta && <span className="text-xs text-gray-400 mt-0.5 block">Buscando info…</span>}
                </div>
                <div>
                  <label className={labelCls}>ISIN (opcional)</label>
                  <input value={newAsset.isin}
                    onChange={e => setNewAsset(d => ({ ...d, isin: e.target.value.toUpperCase() }))}
                    className={`${inputCls} font-mono`} placeholder="ES0170960015"
                    maxLength={12} />
                </div>
                <div className="col-span-2">
                  <label className={labelCls}>Nombre</label>
                  <input value={newAsset.name}
                    onChange={e => setNewAsset(d => ({ ...d, name: e.target.value }))}
                    className={inputCls} placeholder={fetchingMeta ? 'Cargando…' : 'Auto para stocks/ETFs'} />
                </div>
                <div>
                  <label className={labelCls}>Tipo</label>
                  <select value={newAsset.type}
                    onChange={e => setNewAsset(d => ({ ...d, type: e.target.value as NewAssetDraft['type'] }))}
                    className={inputCls}>
                    {ASSET_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Mercado</label>
                  <select
                    value={newAsset.market_id ?? ''}
                    onChange={e => handleMarketChange(e.target.value ? Number(e.target.value) : null)}
                    className={inputCls}>
                    <option value="">Detectar por ticker</option>
                    {markets.map(m => (
                      <option key={m.id} value={m.id}>{m.name} ({m.country})</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Divisa</label>
                  <select value={newAsset.currency}
                    onChange={e => setNewAsset(d => ({ ...d, currency: e.target.value }))}
                    className={inputCls}>
                    {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="flex items-end pb-2">
                  <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400 cursor-pointer">
                    <input type="checkbox" checked={newAsset.manual_price}
                      onChange={e => setNewAsset(d => ({ ...d, manual_price: e.target.checked }))}
                      className="rounded" />
                    Precio manual<br/><span className="text-gray-400">(fondo sin cobertura auto)</span>
                  </label>
                </div>
              </div>
              <div className="flex gap-2 pt-1">
                <button onClick={() => setShowNewAsset(false)}
                  className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
                  Cancelar
                </button>
                <button onClick={handleCreateAsset} disabled={creatingAsset || !newAsset.ticker}
                  className="flex-1 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
                  {creatingAsset ? 'Creando…' : 'Crear activo'}
                </button>
              </div>
            </div>
          )}

          {/* ── Buy / Sell ────────────────────────────── */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Operación</label>
              <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden">
                {(['buy', 'sell'] as const).map(t => (
                  <button key={t} type="button" onClick={() => setTxType(t)}
                    className={`flex-1 py-2 text-sm font-medium transition-colors ${
                      txType === t
                        ? t === 'buy' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
                        : 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
                    }`}>
                    {t === 'buy' ? 'Compra' : 'Venta'}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className={labelCls}>Broker</label>
              <select value={broker} onChange={e => setBroker(e.target.value)} className={inputCls}>
                {BROKERS.map(b => <option key={b.value} value={b.value}>{b.label}</option>)}
              </select>
            </div>
          </div>

          {/* ── Shares + Date ─────────────────────────── */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Participaciones</label>
              <input type="number" step="any" min="0" value={shares}
                onChange={e => setShares(e.target.value)} className={inputCls} placeholder="0" />
            </div>
            <div>
              <label className={labelCls}>Fecha</label>
              <input type="date" value={date} max={today}
                onChange={e => setDate(e.target.value)} className={inputCls} />
            </div>
          </div>

          {/* ── Price + currency ──────────────────────── */}
          <div>
            <label className={labelCls}>Precio / participación</label>
            <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden focus-within:ring-2 focus-within:ring-blue-500">
              <input
                type="number" step="any" min="0" value={price}
                onChange={e => setPrice(e.target.value)}
                placeholder="0.00"
                className="flex-1 min-w-0 px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none"
              />
              <select
                value={currency}
                onChange={e => setCurrency(e.target.value)}
                className="border-l border-gray-300 dark:border-gray-600 px-2 py-2 text-sm bg-gray-50 dark:bg-gray-600 text-gray-700 dark:text-gray-200 focus:outline-none font-mono"
              >
                {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            {eurHint(priceEur)}
            {eurRate == null && currency !== 'EUR' && (
              <span className="text-xs text-amber-500 mt-0.5 block">Sin tasa FX — actualiza precios para conversión exacta</span>
            )}
          </div>

          {/* ── Commission ────────────────────────────── */}
          <div>
            <label className={labelCls}>Comisión en {currency} (opcional)</label>
            <input type="number" step="any" min="0" value={commission}
              onChange={e => setCommission(e.target.value)} className={inputCls} placeholder="0.00" />
            {eurHint(commissionEur)}
          </div>

          {/* ── Notes ─────────────────────────────────── */}
          <div>
            <label className={labelCls}>Notas (opcional)</label>
            <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
              className={inputCls} placeholder="Ej: DCA mensual" />
          </div>
        </div>

        {/* Footer */}
        <div className="flex gap-3 px-5 py-4 border-t border-gray-200 dark:border-gray-700 shrink-0">
          <button onClick={onClose}
            className="flex-1 px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
            Cancelar
          </button>
          <button onClick={handleSave} disabled={saving || !selectedAsset}
            className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
            {saving ? 'Guardando…' : existing ? 'Actualizar' : 'Registrar'}
          </button>
        </div>
      </div>
    </div>
  )
}
