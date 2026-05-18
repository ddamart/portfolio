import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { pricesApi } from '../api/client'
import toast from 'react-hot-toast'

export function Navbar() {
  const [status, setStatus] = useState<{ last_refresh: string | null; stale: boolean; refreshing: boolean } | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const loadStatus = () => {
    pricesApi.status().then(s => {
      setStatus(s)
      if (s.stale && !s.refreshing && !refreshing) {
        triggerRefresh()
      }
    }).catch(() => {})
  }

  const triggerRefresh = async () => {
    setRefreshing(true)
    try {
      await pricesApi.refresh()
      // Poll until done
      const interval = setInterval(() => {
        pricesApi.status().then(s => {
          setStatus(s)
          if (!s.refreshing) {
            clearInterval(interval)
            setRefreshing(false)
            toast.success('Precios actualizados')
          }
        })
      }, 3000)
    } catch {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadStatus()
  }, [])

  return (
    <nav className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          <div className="flex items-center gap-6">
            <span className="font-bold text-gray-900 dark:text-white text-lg">📈 Portfolio</span>
            <div className="flex gap-1">
              <NavLink
                to="/portfolio"
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-white'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                  }`
                }
              >
                Portfolio
              </NavLink>
              <NavLink
                to="/transactions"
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-white'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                  }`
                }
              >
                Transacciones
              </NavLink>
              <NavLink
                to="/assets"
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-white'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                  }`
                }
              >
                Activos
              </NavLink>
              <NavLink
                to="/import"
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-white'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                  }`
                }
              >
                Importar
              </NavLink>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {status?.last_refresh && (
              <span className="text-xs text-gray-400 hidden sm:block">
                Actualizado: {status.last_refresh}
              </span>
            )}
            <button
              onClick={triggerRefresh}
              disabled={refreshing}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
            >
              <span className={refreshing ? 'animate-spin' : ''}>↻</span>
              {refreshing ? 'Actualizando...' : 'Actualizar precios'}
            </button>
          </div>
        </div>
      </div>
    </nav>
  )
}
