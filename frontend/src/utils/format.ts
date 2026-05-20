export function formatEur(value: number, decimals = 2): string {
  return new Intl.NumberFormat('es-ES', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

/** Format a value in any ISO currency. Falls back to "1.234,56 USD" if the code is unknown. */
export function formatCcy(value: number, currency: string, decimals = 2): string {
  if (currency === 'EUR') return formatEur(value, decimals)
  // GBX is pence sterling — not an ISO 4217 code, Intl would throw
  if (currency === 'GBX') {
    return `${new Intl.NumberFormat('es-ES', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value)} p`
  }
  try {
    return new Intl.NumberFormat('es-ES', {
      style: 'currency',
      currency,
      currencyDisplay: 'narrowSymbol',
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(value)
  } catch {
    return `${new Intl.NumberFormat('es-ES', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value)} ${currency}`
  }
}

const _CCY_SYMBOL: Record<string, string> = {
  EUR: '€', USD: '$', GBP: '£', GBX: 'p', JPY: '¥', CHF: 'Fr.', SEK: 'kr', NOK: 'kr', DKK: 'kr', CAD: 'CA$', AUD: 'A$',
}

/** Short axis tick: "$170", "€4k", "$1.2M" — no decimals for readability */
export function fmtAxisCcy(value: number, currency: string): string {
  const sym = _CCY_SYMBOL[currency] ?? (currency + ' ')
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${sym}${(value / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000)     return `${sym}${(value / 1_000).toFixed(0)}k`
  return `${sym}${value.toFixed(0)}`
}

export function formatPct(value: number, decimals = 2): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(decimals)}%`
}

export function formatNumber(value: number, decimals = 4): string {
  return new Intl.NumberFormat('es-ES', {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  }).format(value)
}

export function pnlClass(value: number): string {
  if (value > 0) return 'text-green-600 dark:text-green-400'
  if (value < 0) return 'text-red-500 dark:text-red-400'
  return 'text-gray-500 dark:text-gray-400'
}

export function pnlClassMuted(value: number): string {
  if (value > 0) return 'text-green-700 dark:text-green-600'
  if (value < 0) return 'text-red-700 dark:text-red-600'
  return 'text-gray-500 dark:text-gray-600'
}
