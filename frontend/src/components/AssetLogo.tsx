import { useState } from 'react'

interface AssetLogoProps {
  asset: { image_url: string | null; ticker: string }
  className?: string
}

export function AssetLogo({ asset, className = 'w-8 h-8' }: AssetLogoProps) {
  const [err, setErr] = useState(false)
  if (asset.image_url && !err) {
    return (
      <img
        src={asset.image_url}
        alt=""
        className={`${className} rounded-full object-contain bg-white border border-gray-100 dark:border-gray-700 shrink-0`}
        onError={() => setErr(true)}
      />
    )
  }
  return (
    <div className={`${className} rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center shrink-0`}>
      <span className="text-xs font-bold text-gray-500 dark:text-gray-400">
        {asset.ticker.slice(0, 2).toUpperCase()}
      </span>
    </div>
  )
}
