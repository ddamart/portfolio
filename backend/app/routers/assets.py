import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from app.database import get_db
from app.models.asset import AssetCreate, AssetOut, AssetUpdate
from app.services.price_fetcher import fetch_asset_metadata

router = APIRouter(prefix="/api/assets", tags=["assets"])

_ASSET_COLS = "id, name, ticker, type, currency, market_id, image_url, manual_price, isin, created_at"

def _row_to_out(r) -> AssetOut:
    return AssetOut(
        id=r[0], name=r[1], ticker=r[2], type=r[3], currency=r[4],
        market_id=r[5], image_url=r[6], manual_price=bool(r[7]),
        isin=r[8], created_at=r[9],
    )


@router.get("/markets")
def list_markets():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, mic, name, country FROM markets ORDER BY id"
    ).fetchall()
    return [{"id": r[0], "mic": r[1], "name": r[2], "country": r[3]} for r in rows]


# Ticker suffix → market MIC
_SUFFIX_TO_MIC = {
    ".DE": "XETR",
    ".AS": "XAMS",
    ".MC": "XMAD",
    ".L":  "XLON",
}

# ISIN country prefix → default MIC
_ISIN_COUNTRY_TO_MIC: dict[str, str] = {
    "DE": "XETR",
    "NL": "XAMS",
    "ES": "XMAD",   # overridden to CNMV for funds below
    "GB": "XLON",
    "US": "XNAS",
}


def _detect_market_id(
    conn,
    ticker: str,
    isin: Optional[str] = None,
    asset_type: str = "stock",
) -> Optional[int]:
    def _mic_to_id(mic: str) -> Optional[int]:
        row = conn.execute("SELECT id FROM markets WHERE mic = ?", [mic]).fetchone()
        return row[0] if row else None

    # 1. Ticker suffix (most precise for exchange-listed instruments)
    for suffix, mic in _SUFFIX_TO_MIC.items():
        if ticker.upper().endswith(suffix.upper()):
            return _mic_to_id(mic)

    # 2. ISIN country code (reliable for domicile; adjust for fund vs equity)
    isin_country = None
    if isin and len(isin) >= 2:
        isin_country = isin[:2].upper()
    elif re.match(r'^[A-Z]{2}[A-Z0-9]{10}$', ticker.upper()):
        # ticker itself looks like an ISIN
        isin_country = ticker[:2].upper()

    if isin_country:
        if isin_country == "ES":
            mic = "CNMV" if asset_type == "fund" else "XMAD"
            return _mic_to_id(mic)
        mic = _ISIN_COUNTRY_TO_MIC.get(isin_country)
        if mic:
            return _mic_to_id(mic)

    # 3. Default: NASDAQ for bare US-style tickers
    return _mic_to_id("XNAS")


@router.get("", response_model=list[AssetOut])
def list_assets():
    conn = get_db()
    rows = conn.execute(f"SELECT {_ASSET_COLS} FROM assets ORDER BY name").fetchall()
    return [_row_to_out(r) for r in rows]


@router.get("/search", response_model=list[AssetOut])
def search_assets(q: str = ""):
    conn = get_db()
    like = f"%{q.lower()}%"
    rows = conn.execute(
        f"""SELECT {_ASSET_COLS} FROM assets
            WHERE LOWER(name) LIKE ? OR LOWER(ticker) LIKE ? OR LOWER(isin) LIKE ?
            ORDER BY name LIMIT 10""",
        [like, like, like],
    ).fetchall()
    return [_row_to_out(r) for r in rows]


@router.post("", response_model=AssetOut, status_code=201)
def create_asset(body: AssetCreate):
    conn = get_db()

    if conn.execute("SELECT id FROM assets WHERE ticker = ?", [body.ticker]).fetchone():
        raise HTTPException(status_code=409, detail=f"Asset with ticker '{body.ticker}' already exists")

    if body.isin:
        existing = conn.execute("SELECT ticker FROM assets WHERE isin = ?", [body.isin]).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Asset with ISIN '{body.isin}' already exists (ticker: {existing[0]})",
            )

    name = body.name
    currency = body.currency
    image_url = body.image_url
    if not body.manual_price and body.type != "fund":
        meta = fetch_asset_metadata(body.ticker)
        name = name or meta["name"]
        currency = currency or meta["currency"]
        image_url = image_url or meta["image_url"]

    market_id = body.market_id or _detect_market_id(conn, body.ticker, body.isin, body.type)

    conn.execute(
        """INSERT INTO assets (id, name, ticker, type, currency, market_id, image_url, manual_price, isin, created_at)
           VALUES (nextval('assets_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)""",
        [name, body.ticker, body.type, currency, market_id, image_url, body.manual_price, body.isin],
    )

    row = conn.execute(f"SELECT {_ASSET_COLS} FROM assets WHERE ticker = ?", [body.ticker]).fetchone()

    if not body.manual_price:
        try:
            from app.services import price_fetcher
            price_fetcher.refresh_single_asset(conn, row[0])
        except Exception:
            pass

    return _row_to_out(row)


@router.put("/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: int, body: AssetUpdate):
    conn = get_db()
    if not conn.execute("SELECT id FROM assets WHERE id = ?", [asset_id]).fetchone():
        raise HTTPException(status_code=404, detail="Asset not found")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE assets SET {set_clause} WHERE id = ?",
        list(updates.values()) + [asset_id],
    )

    row = conn.execute(f"SELECT {_ASSET_COLS} FROM assets WHERE id = ?", [asset_id]).fetchone()
    return _row_to_out(row)


@router.put("/{asset_id}/price")
def set_manual_price(asset_id: int, price: float, price_date: str, currency: str = "EUR"):
    """Manual price entry for assets with manual_price=true."""
    from dateutil.parser import parse as parse_date
    conn = get_db()

    row = conn.execute("SELECT id, currency, manual_price FROM assets WHERE id = ?", [asset_id]).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")

    parsed_date = parse_date(price_date).date()

    from app.services.currency import get_rate_to_eur
    try:
        price_eur = price * get_rate_to_eur(conn, currency, parsed_date)
    except ValueError:
        price_eur = price

    conn.execute(
        """
        INSERT INTO prices VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (asset_id, date) DO UPDATE SET
            price = excluded.price, currency = excluded.currency, price_eur = excluded.price_eur
        """,
        [asset_id, parsed_date, price, currency.upper(), price_eur],
    )
    return {"ok": True, "date": str(parsed_date), "price": price, "price_eur": price_eur}
