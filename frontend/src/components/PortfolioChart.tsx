import { useEffect, useState } from 'react'
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import type { ChartPoint } from '../api/client'
import { portfolioApi } from '../api/client'
import { formatEur } from '../utils/format'
import { PeriodFilter } from './PeriodFilter'

export function PortfolioChart() {
  const [period, setPeriod] = useState('ytd')
  const [data, setData] = useState<ChartPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    portfolioApi.chart({ period }).then(d => {
      setData(d)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [period])

  const isPositive = data.length >= 2
    ? data[data.length - 1].value_eur >= data[0].value_eur
    : true

  const color = isPositive ? '#22c55e' : '#ef4444'

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Evolución del Portfolio</h2>
        <PeriodFilter value={period} onChange={setPeriod} />
      </div>
      {loading ? (
        <div className="h-64 flex items-center justify-center text-gray-400">Cargando...</div>
      ) : data.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
          Sin datos para el período seleccionado
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.15} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: '#9ca3af' }}
              tickFormatter={d => d.slice(5)}
            />
            <YAxis
              tick={{ fontSize: 12, fill: '#9ca3af' }}
              tickFormatter={v => `${(v / 1000).toFixed(0)}k`}
              width={48}
            />
            <Tooltip
              formatter={(value) => [formatEur(Number(value)), 'Valor']}
              labelFormatter={l => `Fecha: ${l}`}
              contentStyle={{
                background: '#1f2937',
                border: 'none',
                borderRadius: 8,
                color: '#f9fafb',
                fontSize: 13,
              }}
            />
            <Area
              type="monotone"
              dataKey="value_eur"
              stroke={color}
              strokeWidth={2}
              fill="url(#colorValue)"
              dot={false}
              activeDot={{ r: 4, fill: color }}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
