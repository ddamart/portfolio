/**
 * Build API query params from the period filter state.
 * Used identically by PortfolioSummaryCard, PortfolioTable, and PortfolioChart.
 */
export function getPeriodParams(
  period: string,
  dateFrom?: string,
  dateTo?: string,
): Record<string, string> {
  return period === 'custom'
    ? { ...(dateFrom && { date_from: dateFrom }), ...(dateTo && { date_to: dateTo }) }
    : { period }
}
