from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.config import settings
from app.database import get_db
from app.models.portfolio import PriceStatus
from app.services import price_fetcher
from app.services.price_status import compute_price_status

router = APIRouter(prefix="/api/prices", tags=["prices"])


@router.get("/status", response_model=PriceStatus)
def price_status():
    return compute_price_status(get_db())


@router.post("/refresh")
def refresh_prices(background_tasks: BackgroundTasks):
    """Trigger a full price refresh in the background. Returns immediately."""
    if price_fetcher.is_refreshing():
        return {"ok": False, "message": "Refresh already in progress"}
    # Pass the db path so the background thread opens its own connection —
    # sharing the main conn across threads is not safe.
    background_tasks.add_task(price_fetcher.refresh_all_prices_bg, settings.database_path)
    return {"ok": True, "message": "Price refresh started"}


@router.get("/fx-rate")
def fx_rate(currency: str, date: str):
    """Return the EUR rate for a currency on a given date (for form hints).
    Falls back to fetching from yfinance when the date is not in the local cache."""
    from app.services.currency import get_rate_to_eur
    from app.services.price_fetcher import fetch_fx_rate_on_demand
    from dateutil.parser import parse as parse_date
    conn = get_db()
    if currency.upper() == "EUR":
        return {"rate": 1.0, "found": True}
    target_date = parse_date(date).date()
    try:
        rate = get_rate_to_eur(conn, currency.upper(), target_date)
        return {"rate": rate, "found": True}
    except ValueError:
        rate = fetch_fx_rate_on_demand(conn, currency.upper(), target_date)
        if rate is not None:
            return {"rate": rate, "found": True}
        return {"rate": None, "found": False}


@router.post("/refresh/{asset_id}")
def refresh_single(asset_id: int, background_tasks: BackgroundTasks):
    conn = get_db()
    if not conn.execute("SELECT id FROM assets WHERE id = ?", [asset_id]).fetchone():
        raise HTTPException(status_code=404, detail="Asset not found")
    background_tasks.add_task(price_fetcher.refresh_single_asset_bg, settings.database_path, asset_id)
    return {"ok": True, "message": f"Price refresh started for asset {asset_id}"}
