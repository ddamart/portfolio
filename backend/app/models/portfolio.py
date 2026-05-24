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
    # All-time realized P&L (never period-scoped, used for Rendimiento Total card)
    realized_pnl_all_time_eur: float = 0.0
    realized_pnl_all_time_pct: float = 0.0
    # Total commissions paid ever (buy + sell), for Rendimiento Total neto
    total_commissions_eur: float = 0.0
    # All-time Modified Dietz (inception → effective_date_to) — kept for backward compat
    total_return_eur: Optional[float] = None
    total_return_pct: Optional[float] = None
    # G/P no realizada: SUM(cambio_eur) for all holdings — period-scoped price movement
    unrealized_cambio_eur: Optional[float] = None
    unrealized_cambio_pct: Optional[float] = None   # / total_invested_eur × 100
    # Rendimiento total: all-time unrealized + all-time realized (ignores date_from, respects date_to)
    rendimiento_total_eur: Optional[float] = None
    rendimiento_total_pct: Optional[float] = None   # / total_invested_ever_eur × 100
    # Cambio: unrealized_cambio + realized_pnl (period) = total wealth change in the period
    cambio_total_eur: Optional[float] = None
    cambio_total_pct: Optional[float] = None        # / period_start_value_eur × 100


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
    pnl_eur: Optional[float]       # Unrealized G/P (all-time): value − invested
    pnl_ccy: Optional[float]
    gain_pct: Optional[float]      # pnl_eur / invested × 100
    daily_change_pct: Optional[float]
    allocation_pct: float          # invested / total_pool_invested × 100 (separate pools: tx vs balance)
    # Period-specific performance (None when no period active)
    period_start_value_eur: Optional[float] = None  # price at date_from × current shares (V_ini proxy)
    period_gain_eur: Optional[float] = None         # period gain for balance assets (Modified Dietz num.)
    period_gain_pct: Optional[float] = None         # period return % for balance assets
    # Cambio: price-movement contribution of current position over the period
    cambio_eur: Optional[float] = None    # total_shares × (price_date_to − price_date_from)
    cambio_pct: Optional[float] = None   # cambio_eur / (shares × avg_buy_price_eur) × 100
    # Balance asset fields (only populated when asset type='balance')
    balance_value_eur: Optional[float] = None
    balance_contributions_eur: Optional[float] = None  # all-time net contributions ≤ date_to
    balance_inicio_eur: Optional[float] = None          # snapshot at period start (first ≥ date_from)
    balance_last_snapshot_date: Optional[str] = None
    period_net_flows_eur: Optional[float] = None  # deposits − withdrawals within the period window


class RealizedSale(BaseModel):
    date: date
    asset_name: str
    ticker: str
    asset_type: str
    broker: Optional[str]
    shares: float
    price_eur: float
    cost_basis_eur: float
    realized_pnl_eur: float
    realized_pnl_pct: float


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
