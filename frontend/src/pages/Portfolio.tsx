import { useState } from 'react'
import { PortfolioChart } from '../components/PortfolioChart'
import { PortfolioSummaryCard } from '../components/PortfolioSummaryCard'
import { PortfolioTable } from '../components/PortfolioTable'
import { PeriodFilter } from '../components/PeriodFilter'

export function PortfolioPage() {
  const [period, setPeriod] = useState('ytd')

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <PortfolioSummaryCard />
        <div className="shrink-0 ml-4">
          <PeriodFilter value={period} onChange={setPeriod} />
        </div>
      </div>
      <PortfolioChart period={period} />
      <PortfolioTable period={period} />
    </div>
  )
}
