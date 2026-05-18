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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PortfolioSummaryCard />
        <div className="shrink-0">
          <PeriodFilter
            value={period}
            onChange={setPeriod}
            dateFrom={dateFrom}
            dateTo={dateTo}
            onDateRange={handleDateRange}
          />
        </div>
      </div>
      <PortfolioChart period={period} dateFrom={dateFrom} dateTo={dateTo} />
      <PortfolioTable period={period} dateFrom={dateFrom} dateTo={dateTo} />
    </div>
  )
}
