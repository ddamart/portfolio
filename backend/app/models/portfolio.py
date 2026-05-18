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
    realized_pnl_eur: float = 0.0
    realized_pnl_pct: float = 0.0
    total_invested_ever_eur: float = 0.0


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
