from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class MarketOut(BaseModel):
    id: int
    mic: str
    name: str
    timezone: str
    country: str


class AssetCreate(BaseModel):
    name: str
    ticker: str
    type: str  # etf | stock | fund
    currency: str = "EUR"
    market_id: Optional[int] = None
    image_url: Optional[str] = None
    manual_price: bool = False


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    image_url: Optional[str] = None
    manual_price: Optional[bool] = None
    market_id: Optional[int] = None


class AssetOut(BaseModel):
    id: int
    name: str
    ticker: str
    type: str
    currency: str
    market_id: Optional[int]
    image_url: Optional[str]
    manual_price: bool
    created_at: datetime
