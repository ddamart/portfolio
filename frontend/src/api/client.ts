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
}

export interface Transaction {
  id: number
  asset_id: number
  asset_name: string
  asset_ticker: string
  asset_type: string
  type: 'buy' | 'sell'
  broker: string
  shares: number
  price: number
  price_eur: number
  currency: string
  commission: number
  commission_eur: number
  date: string
  notes: string | null
  created_at: string
  updated_at: string
}

export interface TransactionCreate {
  asset_id: number
  type: 'buy' | 'sell'
  broker: string
  shares: number
  price: number
  currency: string
  commission: number
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
  current_price: number
  current_price_eur: number
  value_eur: number
  value_ccy: number
  pnl_eur: number
  pnl_ccy: number
  gain_pct: number
  daily_change_pct: number | null
  allocation_pct: number
}

export interface PortfolioSummary {
  total_value_eur: number
  total_invested_eur: number
  total_pnl_eur: number
  total_pnl_pct: number
  last_updated: string | null
}

export interface ChartPoint {
  date: string
  value_eur: number
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

export const assetsApi = {
  list: () => api.get<Asset[]>('/assets').then(r => r.data),
  search: (q: string) => api.get<Asset[]>(`/assets/search?q=${encodeURIComponent(q)}`).then(r => r.data),
  create: (body: Omit<Asset, 'id' | 'created_at' | 'isin'> & { isin?: string | null }) => api.post<Asset>('/assets', body).then(r => r.data),
  setManualPrice: (id: number, price: number, date: string, currency: string) =>
    api.put(`/assets/${id}/price`, null, { params: { price, price_date: date, currency } }).then(r => r.data),
  markets: () => api.get<Market[]>('/assets/markets').then(r => r.data),
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
