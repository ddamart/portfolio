import { useState } from 'react'
import { PortfolioChart } from '../components/PortfolioChart'
import { PortfolioSummaryCard } from '../components/PortfolioSummaryCard'
import { PortfolioTable } from '../components/PortfolioTable'
import { PeriodFilter } from '../components/PeriodFilter'

export function PortfolioPage() {
  const [period, setPeriod] = useState('ytd')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const handleDateRange = (from: string, to: string) => {
    setDateFrom(from)
    setDateTo(to)
  }

  return (
    <div className="max-w-[1720px] mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
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
      <PortfolioSummaryCard period={period} dateFrom={dateFrom} dateTo={dateTo} />
      <PortfolioChart period={period} dateFrom={dateFrom} dateTo={dateTo} />
      <PortfolioTable period={period} dateFrom={dateFrom} dateTo={dateTo} />
    </div>
  )
}
