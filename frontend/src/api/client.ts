import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Types matching backend Pydantic models

export interface Asset {
  id: number
  name: string
  ticker: string
  type: 'etf' | 'stock' | 'fund'
  currency: string
  market_id: number | null
  image_url: string | null
  manual_price: boolean
  isin: string | null
  created_at: string
  in_portfolio: boolean
}

export interface Transaction {
  id: number
  asset_id: number
  asset_name: string
  asset_ticker: string
  asset_type: string
  asset_image_url: string | null
  type: 'buy' | 'sell'
  broker: string
  shares: number
  price: number
  price_eur: number
  currency: string
  commission: number
  commission_currency: string
  commission_eur: number
  date: string
  notes: string | null
  created_at: string
  updated_at: string
  // only populated on sell transactions in list view
  cost_basis_eur: number | null
  realized_pnl_eur: number | null
}

export interface TransactionCreate {
  asset_id: number
  type: 'buy' | 'sell'
  broker: string
  shares: number
  price: number
  price_eur?: number
  currency: string
  commission: number
  commission_currency?: string
  date: string
  notes?: string
}

export interface Market {
  id: number
  mic: string
  name: string
  country: string
}

export interface HoldingRow {
  asset_id: number
  name: string
  ticker: string
  type: string
  currency: string
  broker: string | null
  image_url: string | null
  manual_price: boolean
  total_shares: number
  avg_buy_price_eur: number
  avg_buy_price: number
  // null when no price data has been loaded yet for this asset
  current_price: number | null
  current_price_eur: number | null
  value_eur: number | null
  value_ccy: number | null
  pnl_eur: number | null
  pnl_ccy: number | null
  gain_pct: number | null
  daily_change_pct: number | null
  allocation_pct: number
}

export interface PortfolioSummary {
  total_value_eur: number
  total_invested_eur: number
  total_pnl_eur: number
  total_pnl_pct: number
  last_updated: string | null
  realized_pnl_eur: number
  realized_pnl_pct: number
  total_invested_ever_eur: number
  realized_pnl_net_eur: number
  realized_pnl_net_pct: number
}

export interface ChartPoint {
  date: string
  value_eur: number
  invested_eur?: number
}

export interface PriceStatus {
  last_refresh: string | null
  stale: boolean
  refreshing: boolean
  assets: Array<{
    asset_id: number
    ticker: string
    last_price_date: string | null
    stale: boolean
  }>
}

// --- API calls ---

export interface AssetMeta {
  name: string
  currency: string
  image_url: string | null
}

export interface AssetLookup {
  found: boolean
  ticker: string
  isin: string | null
  name: string
  currency: string
  type: 'stock' | 'etf' | 'fund'
  image_url: string | null
  market_id: number | null
}

export interface AssetPricePoint {
  date: string
  price: number
  price_eur: number
  currency: string
}

export const assetsApi = {
  list: () => api.get<Asset[]>('/assets').then(r => r.data),
  search: (q: string) => api.get<Asset[]>(`/assets/search?q=${encodeURIComponent(q)}`).then(r => r.data),
  create: (body: Omit<Asset, 'id' | 'created_at' | 'isin'> & { isin?: string | null }) => api.post<Asset>('/assets', body).then(r => r.data),
  update: (id: number, body: { name?: string; isin?: string | null; market_id?: number | null; manual_price?: boolean; image_url?: string | null }) =>
    api.put<Asset>(`/assets/${id}`, body).then(r => r.data),
  delete: (id: number) => api.delete(`/assets/${id}`),
  setManualPrice: (id: number, price: number, date: string, currency: string) =>
    api.put(`/assets/${id}/price`, null, { params: { price, price_date: date, currency } }).then(r => r.data),
  importPrices: (id: number, rows: { date: string; price: number }[]) =>
    api.post<{ inserted: number; errors: { date: string; error: string }[] }>(`/assets/${id}/prices/import`, rows).then(r => r.data),
  markets: () => api.get<Market[]>('/assets/markets').then(r => r.data),
  metadata: (ticker: string) => api.get<AssetMeta>(`/assets/metadata?ticker=${encodeURIComponent(ticker)}`).then(r => r.data),
  lookup: (q: string) => api.get<AssetLookup>(`/assets/lookup?q=${encodeURIComponent(q)}`).then(r => r.data),
  history: (id: number, period: string) =>
    api.get<AssetPricePoint[]>(`/assets/${id}/history?period=${period}`).then(r => r.data),
}

export const transactionsApi = {
  list: (params?: Record<string, string>) =>
    api.get<Transaction[]>('/transactions', { params }).then(r => r.data),
  create: (body: TransactionCreate) => api.post<Transaction>('/transactions', body).then(r => r.data),
  update: (id: number, body: Partial<TransactionCreate>) =>
    api.put<Transaction>(`/transactions/${id}`, body).then(r => r.data),
  delete: (id: number) => api.delete(`/transactions/${id}`),
}

export const portfolioApi = {
  summary: () => api.get<PortfolioSummary>('/portfolio/summary').then(r => r.data),
  holdings: (params?: Record<string, string>) =>
    api.get<HoldingRow[]>('/portfolio/holdings', { params }).then(r => r.data),
  chart: (params?: Record<string, string>) =>
    api.get<ChartPoint[]>('/portfolio/chart', { params }).then(r => r.data),
}

export const pricesApi = {
  status: () => api.get<PriceStatus>('/prices/status').then(r => r.data),
  refresh: () => api.post('/prices/refresh').then(r => r.data),
  refreshAsset: (id: number) => api.post(`/prices/refresh/${id}`).then(r => r.data),
  fxRate: (currency: string, date: string) =>
    api.get<{ rate: number | null; found: boolean }>(`/prices/fx-rate?currency=${currency}&date=${date}`).then(r => r.data),
}

export interface ParsedTransaction {
  ticker: string
  asset_name: string | null
  asset_type: 'stock' | 'etf' | 'fund'
  transaction_type: 'buy' | 'sell'
  date: string
  shares: number
  price: number
  currency: string
  commission: number
  broker: string
  notes: string | null
  asset_id: number | null
  price_eur: number | null
  commission_eur: number | null
}

export const importApi = {
  parse: (raw_text: string, broker_hint?: string) =>
    api.post<{ transactions: ParsedTransaction[] }>('/import/parse', { raw_text, broker_hint }).then(r => r.data),
  confirm: (transactions: ParsedTransaction[]) =>
    api.post<{ imported: number; errors: string[] }>('/import/confirm', { transactions }).then(r => r.data),
}
