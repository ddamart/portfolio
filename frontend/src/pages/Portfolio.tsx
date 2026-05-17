import { PortfolioChart } from '../components/PortfolioChart'
import { PortfolioSummaryCard } from '../components/PortfolioSummaryCard'
import { PortfolioTable } from '../components/PortfolioTable'

export function PortfolioPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <PortfolioSummaryCard />
      <PortfolioChart />
      <PortfolioTable />
    </div>
  )
}
