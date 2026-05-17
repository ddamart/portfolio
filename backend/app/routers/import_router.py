from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.services.llm_parser import VALID_BROKERS, ParsedTransaction, parse_transactions

router = APIRouter(prefix="/api/import", tags=["import"])


class ParseRequest(BaseModel):
    raw_text: str
    broker_hint: Optional[str] = None


class ParseResponse(BaseModel):
    transactions: list[ParsedTransaction]


class ConfirmRequest(BaseModel):
    transactions: list[ParsedTransaction]


class ConfirmResponse(BaseModel):
    imported: int
    errors: list[str]


@router.post("/parse", response_model=ParseResponse)
def parse_import(body: ParseRequest):
    """Send raw pasted text to the LLM and get back structured transactions."""
    if not body.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty")

    try:
        txns = parse_transactions(body.raw_text, body.broker_hint)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM call failed: {exc}")

    # Enrich with asset_id + EUR values for preview display
    conn = get_db()
    for txn in txns:
        _enrich_for_preview(conn, txn)

    return ParseResponse(transactions=txns)


@router.post("/confirm", response_model=ConfirmResponse)
def confirm_import(body: ConfirmRequest, background_tasks: BackgroundTasks):
    """Commit the user-reviewed transactions to the database."""
    conn = get_db()
    imported = 0
    errors: list[str] = []

    for txn in body.transactions:
        label = f"{txn.ticker} {txn.date}"
        try:
            _ensure_asset(conn, txn)
            _insert_transaction(conn, txn)
            imported += 1
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    if imported > 0:
        background_tasks.add_task(_bg_refresh)

    return ConfirmResponse(imported=imported, errors=errors)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enrich_for_preview(conn, txn: ParsedTransaction) -> None:
    """Look up existing asset and pre-compute EUR price for display."""
    from app.services.currency import get_rate_to_eur
    from dateutil.parser import parse as parse_date

    row = conn.execute(
        "SELECT id FROM assets WHERE LOWER(ticker) = LOWER(?)", [txn.ticker]
    ).fetchone()
    if row:
        txn.asset_id = row[0]

    try:
        d = parse_date(txn.date).date()
        rate = get_rate_to_eur(conn, txn.currency, d)
        txn.price_eur = round(txn.price * rate, 6)
        txn.commission_eur = round(txn.commission * rate, 6)
    except ValueError:
        if txn.currency.upper() == "EUR":
            txn.price_eur = txn.price
            txn.commission_eur = txn.commission


def _ensure_asset(conn, txn: ParsedTransaction) -> None:
    """Find or create an asset by ticker; sets txn.asset_id."""
    from app.routers.assets import _detect_market_id
    from app.services.price_fetcher import fetch_asset_metadata

    row = conn.execute(
        "SELECT id FROM assets WHERE LOWER(ticker) = LOWER(?)", [txn.ticker]
    ).fetchone()
    if row:
        txn.asset_id = row[0]
        return

    name = txn.asset_name or txn.ticker
    currency = txn.currency or "EUR"
    image_url = None
    manual_price = False

    if txn.asset_type != "fund":
        try:
            meta = fetch_asset_metadata(txn.ticker)
            name = txn.asset_name or meta["name"]
            currency = meta.get("currency") or currency
            image_url = meta.get("image_url")
        except Exception:
            pass
    else:
        manual_price = True

    market_id = _detect_market_id(conn, txn.ticker)
    conn.execute(
        "INSERT INTO assets VALUES (nextval('assets_id_seq'), ?, ?, ?, ?, ?, ?, ?, current_timestamp)",
        [name, txn.ticker.upper(), txn.asset_type, currency, market_id, image_url, manual_price],
    )
    row = conn.execute(
        "SELECT id FROM assets WHERE ticker = ?", [txn.ticker.upper()]
    ).fetchone()
    txn.asset_id = row[0]


def _insert_transaction(conn, txn: ParsedTransaction) -> None:
    from app.services.currency import get_rate_to_eur
    from dateutil.parser import parse as parse_date

    if not txn.asset_id:
        raise ValueError("asset not resolved")

    broker = txn.broker.lower()
    if broker not in VALID_BROKERS:
        raise ValueError(
            f"Invalid broker '{txn.broker}'. Must be one of: {', '.join(sorted(VALID_BROKERS))}"
        )

    d = parse_date(txn.date).date()
    try:
        rate = get_rate_to_eur(conn, txn.currency, d)
        price_eur = txn.price * rate
        commission_eur = txn.commission * rate
    except ValueError:
        if txn.currency.upper() == "EUR":
            price_eur = txn.price
            commission_eur = txn.commission
        else:
            raise ValueError(
                f"No FX rate for {txn.currency} on {txn.date}. Run a price refresh first."
            )

    conn.execute(
        """
        INSERT INTO transactions VALUES (
            nextval('transactions_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp, current_timestamp
        )
        """,
        [
            txn.asset_id, txn.transaction_type, broker,
            txn.shares, txn.price, price_eur, txn.currency.upper(),
            txn.commission, commission_eur, d, txn.notes,
        ],
    )


def _bg_refresh() -> None:
    try:
        from app.database import get_db as _get_db
        from app.services.price_fetcher import refresh_all_prices
        refresh_all_prices(_get_db())
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Background refresh after import failed: %s", exc)
