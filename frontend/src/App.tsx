import { Navigate, Route, Routes } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { Navbar } from './components/Navbar'
import { PortfolioPage } from './pages/Portfolio'
import { TransactionsPage } from './pages/Transactions'

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/portfolio" replace />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
        </Routes>
      </main>
      <Toaster position="bottom-right" />
    </div>
  )
}
