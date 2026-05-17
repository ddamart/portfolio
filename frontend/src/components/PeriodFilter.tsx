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
}

export function PeriodFilter({ value, onChange }: Props) {
  return (
    <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
      {PERIODS.map(p => (
        <button
          key={p.value}
          onClick={() => onChange(p.value)}
          className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
            value === p.value
              ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
          }`}
        >
          {p.label}
        </button>
      ))}
    </div>
  )
}
