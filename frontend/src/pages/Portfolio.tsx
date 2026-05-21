import { useState } from 'react'
import { PortfolioChart } from '../components/PortfolioChart'
import { PortfolioSummaryCard } from '../components/PortfolioSummaryCard'
import { PortfolioTable } from '../components/PortfolioTable'
import { PeriodFilter } from '../components/PeriodFilter'

const BROKER_OPTIONS = [
  { value: 'openbank', label: 'Openbank' },
  { value: 'trade_republic', label: 'Trade Republic' },
  { value: 'revolut', label: 'Revolut' },
  { value: 'degiro', label: 'Degiro' },
]

const TYPE_OPTIONS = [
  { value: 'stock', label: 'Acciones' },
  { value: 'etf', label: 'ETF' },
  { value: 'fund', label: 'Fondos' },
  { value: 'balance', label: 'Cartera' },
]

function FilterPills({
  label, options, values, onChange,
}: {
  label: string
  options: { value: string; label: string }[]
  values: string[]
  onChange: (vs: string[]) => void
}) {
  const toggle = (v: string) =>
    onChange(values.includes(v) ? values.filter(x => x !== v) : [...values, v])

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">{label}:</span>
      {options.map(opt => (
        <button
          key={opt.value}
          onClick={() => toggle(opt.value)}
          className={`text-xs px-2.5 py-1 rounded-full border font-medium transition-colors whitespace-nowrap ${
            values.includes(opt.value)
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

export function PortfolioPage() {
  const [period, setPeriod] = useState('ytd')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [brokers, setBrokers] = useState<string[]>([])
  const [assetTypes, setAssetTypes] = useState<string[]>([])

  const handleDateRange = (from: string, to: string) => {
    setDateFrom(from)
    setDateTo(to)
  }

  const handleChartRangeSelect = (from: string, to: string) => {
    setDateFrom(from)
    setDateTo(to)
    setPeriod('custom')
  }

  const hasFilters = brokers.length > 0 || assetTypes.length > 0
  const brokerParam = brokers.length > 0 ? brokers.join(',') : undefined
  const assetTypeParam = assetTypes.length > 0 ? assetTypes.join(',') : undefined

  return (
    <div className="max-w-[1720px] mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Cartera</h1>
          <PeriodFilter
            value={period}
            onChange={setPeriod}
            dateFrom={dateFrom}
            dateTo={dateTo}
            onDateRange={handleDateRange}
          />
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <FilterPills
            label="Tipo"
            options={TYPE_OPTIONS}
            values={assetTypes}
            onChange={setAssetTypes}
          />
          <FilterPills
            label="Broker"
            options={BROKER_OPTIONS}
            values={brokers}
            onChange={setBrokers}
          />
          {hasFilters && (
            <button
              onClick={() => { setBrokers([]); setAssetTypes([]) }}
              className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 underline ml-auto"
            >
              Limpiar filtros
            </button>
          )}
        </div>
      </div>
      <PortfolioSummaryCard
        period={period} dateFrom={dateFrom} dateTo={dateTo}
        broker={brokerParam} assetType={assetTypeParam}
      />
      <PortfolioChart
        period={period} dateFrom={dateFrom} dateTo={dateTo}
        onRangeSelect={handleChartRangeSelect}
        broker={brokerParam} assetType={assetTypeParam}
      />
      <PortfolioTable
        period={period} dateFrom={dateFrom} dateTo={dateTo}
        broker={brokerParam} assetType={assetTypeParam}
      />
    </div>
  )
}
