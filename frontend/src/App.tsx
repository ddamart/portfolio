import { Component, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { Navbar } from './components/Navbar'
import { AssetsPage } from './pages/Assets'
import { PortfolioPage } from './pages/Portfolio'
import { TransactionsPage } from './pages/Transactions'
import { ImportPage } from './pages/Import'

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-8">
          <div className="max-w-lg w-full bg-white dark:bg-gray-900 rounded-xl border border-red-200 dark:border-red-800 p-6 space-y-3">
            <h2 className="text-lg font-semibold text-red-600 dark:text-red-400">Error al cargar la aplicación</h2>
            <pre className="text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 rounded p-3 overflow-auto whitespace-pre-wrap">
              {(this.state.error as Error).message}
            </pre>
            <p className="text-sm text-gray-500">Abre la consola del navegador (F12) para ver el stack completo.</p>
            <button
              onClick={() => this.setState({ error: null })}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Reintentar
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
        <Navbar />
        <main>
          <Routes>
            <Route path="/" element={<Navigate to="/portfolio" replace />} />
            <Route path="/portfolio" element={<PortfolioPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/assets" element={<AssetsPage />} />
            <Route path="/import" element={<ImportPage />} />
          </Routes>
        </main>
        <Toaster position="bottom-right" />
      </div>
    </ErrorBoundary>
  )
}
