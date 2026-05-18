import { createContext, useContext, useState, type ReactNode } from 'react'

interface RefreshContextValue {
  lastRefreshAt: number
  markRefreshed: () => void
}

const RefreshContext = createContext<RefreshContextValue>({ lastRefreshAt: 0, markRefreshed: () => {} })

export function RefreshProvider({ children }: { children: ReactNode }) {
  const [lastRefreshAt, setLastRefreshAt] = useState(0)
  const markRefreshed = () => setLastRefreshAt(Date.now())
  return (
    <RefreshContext.Provider value={{ lastRefreshAt, markRefreshed }}>
      {children}
    </RefreshContext.Provider>
  )
}

export const useRefresh = () => useContext(RefreshContext)
