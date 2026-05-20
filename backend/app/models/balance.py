from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class BalanceEntryCreate(BaseModel):
    date: date
    type: str   # deposit | withdrawal | snapshot
    amount_eur: float
    notes: Optional[str] = None


class BalanceEntryOut(BaseModel):
    id: int
    asset_id: int
    date: date
    type: str
    amount_eur: float
    notes: Optional[str]
    created_at: datetime
