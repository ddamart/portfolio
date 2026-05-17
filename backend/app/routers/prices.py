from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.database import get_db
from app.models.portfolio import PriceStatus, PriceStatusAsset
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

    conn = get_db()
    background_tasks.add_task(price_fetcher.refresh_all_prices, conn)
    return {"ok": True, "message": "Price refresh started"}


@router.post("/refresh/{asset_id}")
def refresh_single(asset_id: int, background_tasks: BackgroundTasks):
    conn = get_db()
    row = conn.execute("SELECT id FROM assets WHERE id = ?", [asset_id]).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")

    background_tasks.add_task(price_fetcher.refresh_single_asset, conn, asset_id)
    return {"ok": True, "message": f"Price refresh started for asset {asset_id}"}
