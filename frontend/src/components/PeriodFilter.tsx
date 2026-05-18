const PERIODS = [
  { label: '1D', value: '1d' },
  { label: '1S', value: '1w' },
  { label: '1M', value: '1m' },
  { label: '6M', value: '6m' },
  { label: 'YTD', value: 'ytd' },
  { label: '1A', value: '1y' },
  { label: '5A', value: '5y' },
  { label: 'Todo', value: 'all' },
]

interface Props {
  value: string
  onChange: (period: string) => void
  dateFrom?: string
  dateTo?: string
  onDateRange?: (from: string, to: string) => void
}

export function PeriodFilter({ value, onChange, dateFrom = '', dateTo = '', onDateRange }: Props) {
  const isCustom = value === 'custom'

  const handleFrom = (from: string) => {
    onDateRange?.(from, dateTo)
    if (from || dateTo) onChange('custom')
  }

  const handleTo = (to: string) => {
    onDateRange?.(dateFrom, to)
    if (dateFrom || to) onChange('custom')
  }

  const handlePeriod = (p: string) => {
    onChange(p)
    onDateRange?.('', '')
  }

  const inputClass = (active: boolean) =>
    `px-2 py-1.5 text-sm rounded-md border focus:outline-none focus:ring-1 focus:ring-blue-400 ${
      active
        ? 'border-blue-400 dark:border-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white'
        : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400'
    }`

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
        {PERIODS.map(p => (
          <button
            key={p.value}
            onClick={() => handlePeriod(p.value)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              !isCustom && value === p.value
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
      {onDateRange && (
        <div className="flex items-center gap-1">
          <input
            type="date"
            value={dateFrom}
            onChange={e => handleFrom(e.target.value)}
            className={inputClass(isCustom)}
          />
          <span className="text-gray-400 text-sm">—</span>
          <input
            type="date"
            value={dateTo}
            onChange={e => handleTo(e.target.value)}
            className={inputClass(isCustom)}
          />
          {isCustom && (
            <button
              onClick={() => { onDateRange('', ''); onChange('all') }}
              className="ml-1 text-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
              title="Limpiar rango"
            >
              ✕
            </button>
          )}
        </div>
      )}
    </div>
  )
}
