import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.database import get_db
from app.models.asset import AssetCreate, AssetOut, AssetUpdate
from app.services.price_fetcher import fetch_asset_metadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assets", tags=["assets"])

_ASSET_COLS = "id, name, ticker, type, currency, market_id, image_url, manual_price, isin, created_at"

def _row_to_out(r, in_portfolio: bool = False) -> AssetOut:
    return AssetOut(
        id=r[0], name=r[1], ticker=r[2], type=r[3], currency=r[4],
        market_id=r[5], image_url=r[6], manual_price=bool(r[7]),
        isin=r[8], created_at=r[9], in_portfolio=in_portfolio,
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
    ".ST": "XSTO",
}

# ISIN country prefix → default MIC
_ISIN_COUNTRY_TO_MIC: dict[str, str] = {
    "DE": "XETR",
    "NL": "XAMS",
    "ES": "XMAD",   # overridden to CNMV for funds below
    "GB": "XLON",
    "US": "XNAS",
    "SE": "XSTO",
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


@router.get("/metadata")
def asset_metadata(ticker: str):
    """Preview name/currency/image for a ticker without creating the asset."""
    return fetch_asset_metadata(ticker)


@router.get("/lookup")
def lookup_asset(q: str):
    """Resolve an ISIN or ticker to enriched asset metadata for the creation preview."""
    from app.services.price_fetcher import lookup_asset as _lookup
    result = _lookup(q)
    conn = get_db()
    result["market_id"] = _detect_market_id(conn, result["ticker"], result.get("isin"), result["type"])
    return result


@router.get("/{asset_id}/history")
def asset_price_history(asset_id: int, period: str = "1y"):
    """Return price history for a single asset filtered by period."""
    conn = get_db()
    if not conn.execute("SELECT id FROM assets WHERE id = ?", [asset_id]).fetchone():
        raise HTTPException(status_code=404, detail="Asset not found")

    from app.services.portfolio_calc import _period_to_date_range
    date_from, _ = _period_to_date_range(period)

    if date_from:
        rows = conn.execute(
            "SELECT date, price, price_eur, currency FROM prices WHERE asset_id = ? AND date >= ? ORDER BY date ASC",
            [asset_id, date_from],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT date, price, price_eur, currency FROM prices WHERE asset_id = ? ORDER BY date ASC",
            [asset_id],
        ).fetchall()

    return [{"date": str(r[0]), "price": float(r[1]), "price_eur": float(r[2]), "currency": r[3]} for r in rows]


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int):
    conn = get_db()
    if not conn.execute("SELECT id FROM assets WHERE id = ?", [asset_id]).fetchone():
        raise HTTPException(status_code=404, detail="Asset not found")
    has_tx = conn.execute("SELECT COUNT(*) FROM transactions WHERE asset_id = ?", [asset_id]).fetchone()[0]
    if has_tx:
        raise HTTPException(status_code=409, detail=f"Cannot delete: asset has {has_tx} transaction(s)")
    conn.execute("DELETE FROM prices WHERE asset_id = ?", [asset_id])
    conn.execute("DELETE FROM assets WHERE id = ?", [asset_id])


@router.get("", response_model=list[AssetOut])
def list_assets():
    conn = get_db()
    rows = conn.execute(
        f"""
        SELECT {_ASSET_COLS},
               COALESCE(h.net_shares, 0) > 0 AS in_portfolio
        FROM assets a
        LEFT JOIN (
            SELECT asset_id,
                   SUM(CASE WHEN type = 'buy' THEN shares ELSE -shares END) AS net_shares
            FROM transactions
            GROUP BY asset_id
        ) h ON h.asset_id = a.id
        ORDER BY a.name
        """
    ).fetchall()
    return [_row_to_out(r, in_portfolio=bool(r[10])) for r in rows]


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
        # Treat name == ticker as "not provided" — the frontend falls back to ticker
        # when yfinance fails, so we must prefer the freshly-fetched full name here.
        if not name or name.upper() == body.ticker.upper():
            name = meta["name"]
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
            n = price_fetcher.refresh_single_asset(conn, row[0])
            if n == 0:
                logger.warning("No prices loaded for %s — ticker may be unrecognised or market closed", body.ticker)
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", body.ticker, e)

    return _row_to_out(row)


@router.put("/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: int, body: AssetUpdate):
    conn = get_db()
    if not conn.execute("SELECT id FROM assets WHERE id = ?", [asset_id]).fetchone():
        raise HTTPException(status_code=404, detail="Asset not found")

    # exclude_unset so only fields explicitly included in the request body are updated;
    # this also allows callers to null out a field (e.g. clear market_id) by sending null.
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Validate foreign key before hitting DuckDB — its FK error message is misleading
    # (it reports the child-table constraint instead of the violated parent reference).
    if "market_id" in updates and updates["market_id"] is not None:
        if not conn.execute("SELECT id FROM markets WHERE id = ?", [updates["market_id"]]).fetchone():
            raise HTTPException(status_code=422, detail=f"market_id {updates['market_id']} does not exist")

    new_ticker = None
    if "ticker" in updates and updates["ticker"] is not None:
        updates["ticker"] = updates["ticker"].upper()
        new_ticker = updates.pop("ticker")  # handle separately — see below
        conflict = conn.execute(
            "SELECT id FROM assets WHERE ticker = ? AND id != ?", [new_ticker, asset_id]
        ).fetchone()
        if conflict:
            raise HTTPException(status_code=409, detail=f"Ticker '{new_ticker}' already used by another asset")

    # Update all non-ticker fields first
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE assets SET {set_clause} WHERE id = ?",
            list(updates.values()) + [asset_id],
        )

    # Ticker is a UNIQUE column — DuckDB implements its UPDATE as DELETE+INSERT,
    # which trips the FK constraint from transactions/prices → assets.id.
    # Workaround: snapshot child rows, remove them, update ticker, restore.
    if new_ticker is not None:
        tx_rows    = conn.execute("SELECT * FROM transactions WHERE asset_id = ?", [asset_id]).fetchall()
        price_rows = conn.execute("SELECT * FROM prices       WHERE asset_id = ?", [asset_id]).fetchall()

        conn.execute("DELETE FROM transactions WHERE asset_id = ?", [asset_id])
        conn.execute("DELETE FROM prices       WHERE asset_id = ?", [asset_id])
        conn.execute("UPDATE assets SET ticker = ? WHERE id = ?", [new_ticker, asset_id])

        for row in tx_rows:
            conn.execute(
                "INSERT INTO transactions (id, asset_id, type, broker, shares, price, price_eur, "
                "currency, commission, commission_currency, commission_eur, date, notes, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                list(row),
            )
        for row in price_rows:
            conn.execute(
                "INSERT INTO prices (asset_id, date, price, currency, price_eur) VALUES (?,?,?,?,?)",
                list(row),
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


class _PriceImportItem(BaseModel):
    date: str
    price: float


@router.post("/{asset_id}/prices/import")
def import_prices(asset_id: int, body: list[_PriceImportItem]):
    """Batch upsert prices for a manual-price asset (CSV-style import)."""
    from dateutil.parser import parse as _parse_date
    conn = get_db()
    row = conn.execute("SELECT id, currency FROM assets WHERE id = ?", [asset_id]).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")
    currency = row[1]

    from app.services.currency import get_rate_to_eur
    inserted, errors = 0, []
    for item in body:
        try:
            d = _parse_date(item.date).date()
            try:
                price_eur = item.price * get_rate_to_eur(conn, currency, d)
            except ValueError:
                price_eur = item.price
            conn.execute(
                """INSERT INTO prices VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (asset_id, date) DO UPDATE SET
                       price = excluded.price, currency = excluded.currency, price_eur = excluded.price_eur""",
                [asset_id, d, item.price, currency, price_eur],
            )
            inserted += 1
        except Exception as exc:
            errors.append({"date": item.date, "error": str(exc)})
    return {"inserted": inserted, "errors": errors}
