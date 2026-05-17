from pydantic import BaseModel, field_validator
from datetime import date, datetime
from typing import Optional


VALID_BROKERS = {"openbank", "trade_republic", "revolut", "degiro"}
VALID_TYPES = {"buy", "sell"}


class TransactionCreate(BaseModel):
    asset_id: int
    type: str
    broker: str
    shares: float
    price: float
    currency: str = "EUR"
    commission: float = 0.0
    date: date
    notes: Optional[str] = None
    # Computed on the backend from FX table; only send if you already know them
    price_eur: Optional[float] = None
    commission_eur: Optional[float] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_TYPES:
            raise ValueError(f"type must be one of {VALID_TYPES}")
        return v

    @field_validator("broker")
    @classmethod
    def validate_broker(cls, v: str) -> str:
        if v not in VALID_BROKERS:
            raise ValueError(f"broker must be one of {VALID_BROKERS}")
        return v


class TransactionUpdate(BaseModel):
    type: Optional[str] = None
    broker: Optional[str] = None
    shares: Optional[float] = None
    price: Optional[float] = None
    price_eur: Optional[float] = None
    currency: Optional[str] = None
    commission: Optional[float] = None
    commission_eur: Optional[float] = None
    date: Optional[date] = None
    notes: Optional[str] = None


class TransactionOut(BaseModel):
    id: int
    asset_id: int
    asset_name: str
    asset_ticker: str
    asset_type: str
    type: str
    broker: str
    shares: float
    price: float
    price_eur: float
    currency: str
    commission: float
    commission_eur: float
    date: date
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
