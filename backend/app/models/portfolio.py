from pydantic import BaseModel
from datetime import date
from typing import Optional


class PortfolioSummary(BaseModel):
    total_value_eur: float
    total_invested_eur: float
    total_pnl_eur: float
    total_pnl_pct: float
    last_updated: Optional[date]
    # Realized P&L from closed / partially-closed positions (AVCO running method)
    realized_pnl_eur: float = 0.0       # price-only P&L (no commissions)
    realized_pnl_pct: float = 0.0
    total_invested_ever_eur: float = 0.0
    realized_pnl_net_eur: float = 0.0   # net of all commissions (buy + sell)
    realized_pnl_net_pct: float = 0.0
    # Period-scoped return — None when period='all' or not provided
    period_start_value_eur: Optional[float] = None
    period_return_eur: Optional[float] = None
    period_return_pct: Optional[float] = None


class HoldingRow(BaseModel):
    asset_id: int
    name: str
    ticker: str
    type: str
    currency: str
    broker: Optional[str]
    image_url: Optional[str]
    manual_price: bool
    total_shares: float
    avg_buy_price_eur: float
    avg_buy_price: float
    # These are None when no price data has been loaded yet for the asset
    current_price: Optional[float]
    current_price_eur: Optional[float]
    value_eur: Optional[float]
    value_ccy: Optional[float]
    pnl_eur: Optional[float]
    pnl_ccy: Optional[float]
    gain_pct: Optional[float]
    daily_change_pct: Optional[float]
    allocation_pct: float
    # Period-specific performance (None when period='all' or no period active)
    period_start_value_eur: Optional[float] = None  # V_ini: EUR value at period start (before period txns)
    period_invested_eur: Optional[float] = None     # V_ini + buy_cost − sell_proceeds across the period
    period_avg_price_eur: Optional[float] = None    # period_invested_eur / total_shares
    period_gain_eur: Optional[float] = None         # Modified Dietz gain €
    period_gain_pct: Optional[float] = None         # Modified Dietz %
    # Balance asset fields (only populated when asset type='balance')
    balance_value_eur: Optional[float] = None
    balance_contributions_eur: Optional[float] = None
    balance_last_snapshot_date: Optional[str] = None
    period_net_flows_eur: Optional[float] = None  # deposits − withdrawals within the period window


class ChartPoint(BaseModel):
    date: date
    value_eur: float
    invested_eur: Optional[float] = None


class PriceStatusAsset(BaseModel):
    asset_id: int
    ticker: str
    last_price_date: Optional[date]
    stale: bool


class PriceStatus(BaseModel):
    last_refresh: Optional[str]
    stale: bool
    refreshing: bool
    assets: list[PriceStatusAsset]
