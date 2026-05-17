from datetime import date
from typing import Optional

from fastapi import APIRouter
from app.database import get_db
from app.models.portfolio import ChartPoint, HoldingRow, PortfolioSummary
from app.services.portfolio_calc import get_chart_data, get_holdings, get_summary

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary():
    return get_summary(get_db())


@router.get("/holdings", response_model=list[HoldingRow])
def portfolio_holdings(
    period: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    broker: Optional[str] = None,
    asset_type: Optional[str] = None,
):
    return get_holdings(get_db(), period=period, date_from=date_from, date_to=date_to, broker=broker, asset_type=asset_type)


@router.get("/chart", response_model=list[ChartPoint])
def portfolio_chart(
    period: Optional[str] = "ytd",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
):
    return get_chart_data(get_db(), period=period, date_from=date_from, date_to=date_to)
