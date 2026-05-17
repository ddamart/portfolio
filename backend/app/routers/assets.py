from fastapi import APIRouter, HTTPException
from app.database import get_db
from app.models.asset import AssetCreate, AssetOut, AssetUpdate
from app.services.price_fetcher import fetch_asset_metadata

router = APIRouter(prefix="/api/assets", tags=["assets"])

# Map ticker suffix to market MIC
_SUFFIX_TO_MIC = {
    ".DE": "XETR",
    ".AS": "XAMS",
    ".MC": "XMAD",
    ".L": "XLON",
}


def _detect_market_id(conn, ticker: str) -> int | None:
    for suffix, mic in _SUFFIX_TO_MIC.items():
        if ticker.upper().endswith(suffix.upper()):
            row = conn.execute("SELECT id FROM markets WHERE mic = ?", [mic]).fetchone()
            return row[0] if row else None
    # ISIN pattern (2 letters + 10 alphanumeric)
    import re
    if re.match(r"^[A-Z]{2}[A-Z0-9]{10}$", ticker.upper()):
        row = conn.execute("SELECT id FROM markets WHERE mic = 'CNMV'").fetchone()
        return row[0] if row else None
    # Default: NASDAQ for bare US tickers
    row = conn.execute("SELECT id FROM markets WHERE mic = 'XNAS'").fetchone()
    return row[0] if row else None


@router.get("", response_model=list[AssetOut])
def list_assets():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, ticker, type, currency, market_id, image_url, manual_price, created_at FROM assets ORDER BY name"
    ).fetchall()
    return [
        AssetOut(
            id=r[0], name=r[1], ticker=r[2], type=r[3], currency=r[4],
            market_id=r[5], image_url=r[6], manual_price=bool(r[7]), created_at=r[8],
        )
        for r in rows
    ]


@router.get("/search", response_model=list[AssetOut])
def search_assets(q: str = ""):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, ticker, type, currency, market_id, image_url, manual_price, created_at FROM assets WHERE LOWER(name) LIKE ? OR LOWER(ticker) LIKE ? ORDER BY name LIMIT 10",
        [f"%{q.lower()}%", f"%{q.lower()}%"],
    ).fetchall()
    return [
        AssetOut(
            id=r[0], name=r[1], ticker=r[2], type=r[3], currency=r[4],
            market_id=r[5], image_url=r[6], manual_price=bool(r[7]), created_at=r[8],
        )
        for r in rows
    ]


@router.post("", response_model=AssetOut, status_code=201)
def create_asset(body: AssetCreate):
    conn = get_db()

    existing = conn.execute("SELECT id FROM assets WHERE ticker = ?", [body.ticker]).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail=f"Asset with ticker '{body.ticker}' already exists")

    # Auto-fill metadata from yfinance if not a fund
    name = body.name
    currency = body.currency
    image_url = body.image_url
    if not body.manual_price and body.type != "fund":
        meta = fetch_asset_metadata(body.ticker)
        name = name or meta["name"]
        currency = currency or meta["currency"]
        image_url = image_url or meta["image_url"]

    market_id = body.market_id or _detect_market_id(conn, body.ticker)

    conn.execute(
        """
        INSERT INTO assets VALUES (nextval('assets_id_seq'), ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        """,
        [name, body.ticker, body.type, currency, market_id, image_url, body.manual_price],
    )

    row = conn.execute(
        "SELECT id, name, ticker, type, currency, market_id, image_url, manual_price, created_at FROM assets WHERE ticker = ?",
        [body.ticker],
    ).fetchone()

    # Kick off historical price fetch in background after creation
    if not body.manual_price:
        try:
            from app.services import price_fetcher
            price_fetcher.refresh_single_asset(conn, row[0])
        except Exception:
            pass  # non-fatal; user can refresh manually

    return AssetOut(
        id=row[0], name=row[1], ticker=row[2], type=row[3], currency=row[4],
        market_id=row[5], image_url=row[6], manual_price=bool(row[7]), created_at=row[8],
    )


@router.put("/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: int, body: AssetUpdate):
    conn = get_db()
    row = conn.execute("SELECT id FROM assets WHERE id = ?", [asset_id]).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE assets SET {set_clause} WHERE id = ?",
        list(updates.values()) + [asset_id],
    )

    row = conn.execute(
        "SELECT id, name, ticker, type, currency, market_id, image_url, manual_price, created_at FROM assets WHERE id = ?",
        [asset_id],
    ).fetchone()
    return AssetOut(
        id=row[0], name=row[1], ticker=row[2], type=row[3], currency=row[4],
        market_id=row[5], image_url=row[6], manual_price=bool(row[7]), created_at=row[8],
    )


@router.put("/{asset_id}/price")
def set_manual_price(asset_id: int, price: float, price_date: str, currency: str = "EUR"):
    """Manual price entry for assets with manual_price=true."""
    from datetime import date as date_type
    from dateutil.parser import parse as parse_date
    conn = get_db()

    row = conn.execute("SELECT id, currency, manual_price FROM assets WHERE id = ?", [asset_id]).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")

    parsed_date = parse_date(price_date).date()

    # Convert to EUR
    from app.services.currency import get_rate_to_eur
    try:
        price_eur = price * get_rate_to_eur(conn, currency, parsed_date)
    except ValueError:
        price_eur = price  # fallback if no FX rate

    conn.execute(
        """
        INSERT INTO prices VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (asset_id, date) DO UPDATE SET
            price = excluded.price, currency = excluded.currency, price_eur = excluded.price_eur
        """,
        [asset_id, parsed_date, price, currency.upper(), price_eur],
    )
    return {"ok": True, "date": str(parsed_date), "price": price, "price_eur": price_eur}
