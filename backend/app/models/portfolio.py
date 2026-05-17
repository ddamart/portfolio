from pydantic import BaseModel
from datetime import date
from typing import Optional


class PortfolioSummary(BaseModel):
    total_value_eur: float
    total_invested_eur: float
    total_pnl_eur: float
    total_pnl_pct: float
    last_updated: Optional[date]


class HoldingRow(BaseModel):
    asset_id: int
    name: str
    ticker: str
    type: str
    currency: str
    broker: Optional[str]  # None when asset held across multiple brokers
    image_url: Optional[str]
    manual_price: bool
    total_shares: float
    avg_buy_price_eur: float
    current_price: float
    current_price_eur: float
    value_eur: float
    value_ccy: float
    pnl_eur: float
    pnl_ccy: float
    gain_pct: float
    daily_change_pct: Optional[float]
    allocation_pct: float


class ChartPoint(BaseModel):
    date: date
    value_eur: float


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
