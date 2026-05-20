import re
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class MarketOut(BaseModel):
    id: int
    mic: str
    name: str
    timezone: str
    country: str


def _validate_isin(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v = v.upper().strip()
    if not v:
        return None
    # Normalize standard ISINs; allow arbitrary strings for off-market / manual assets
    return v


class AssetCreate(BaseModel):
    name: str
    ticker: str
    type: str  # etf | stock | fund
    currency: str = "EUR"
    market_id: Optional[int] = None
    image_url: Optional[str] = None
    manual_price: bool = False
    isin: Optional[str] = None

    @field_validator('isin')
    @classmethod
    def validate_isin(cls, v: Optional[str]) -> Optional[str]:
        return _validate_isin(v)


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    ticker: Optional[str] = None
    isin: Optional[str] = None
    image_url: Optional[str] = None
    manual_price: Optional[bool] = None
    market_id: Optional[int] = None
    currency: Optional[str] = None

    @field_validator('isin')
    @classmethod
    def validate_isin(cls, v: Optional[str]) -> Optional[str]:
        return _validate_isin(v)


class AssetOut(BaseModel):
    id: int
    name: str
    ticker: str
    type: str
    currency: str
    market_id: Optional[int]
    image_url: Optional[str]
    manual_price: bool
    isin: Optional[str]
    created_at: datetime
    in_portfolio: bool = False
