from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from app.database import get_db
from app.models.transaction import TransactionCreate, TransactionOut, TransactionUpdate

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _row_to_out(r) -> TransactionOut:
    return TransactionOut(
        id=r[0], asset_id=r[1], asset_name=r[2], asset_ticker=r[3], asset_type=r[4],
        type=r[5], broker=r[6], shares=float(r[7]), price=float(r[8]),
        price_eur=float(r[9]), currency=r[10], commission=float(r[11]),
        commission_eur=float(r[12]), date=r[13], notes=r[14],
        created_at=r[15], updated_at=r[16],
    )


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    period: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    broker: Optional[str] = None,
    asset_type: Optional[str] = None,
    asset_id: Optional[int] = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
):
    conn = get_db()

    # Resolve period to date range
    if period and not date_from:
        from app.services.portfolio_calc import _period_to_date_range
        date_from, date_to = _period_to_date_range(period)

    filters = []
    params: list = []

    if date_from:
        filters.append("t.date >= ?")
        params.append(date_from)
    if date_to:
        filters.append("t.date <= ?")
        params.append(date_to)
    if broker:
        filters.append("t.broker = ?")
        params.append(broker)
    if asset_type:
        filters.append("a.type = ?")
        params.append(asset_type)
    if asset_id:
        filters.append("t.asset_id = ?")
        params.append(asset_id)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    valid_sort = {"date", "shares", "price", "price_eur", "broker", "type"}
    sort_col = sort_by if sort_by in valid_sort else "date"
    sort_direction = "DESC" if sort_dir.lower() == "desc" else "ASC"

    query = f"""
    SELECT
        t.id, t.asset_id, a.name, a.ticker, a.type,
        t.type, t.broker, t.shares, t.price, t.price_eur,
        t.currency, t.commission, t.commission_eur,
        t.date, t.notes, t.created_at, t.updated_at
    FROM transactions t
    JOIN assets a ON a.id = t.asset_id
    {where}
    ORDER BY t.{sort_col} {sort_direction}
    """

    rows = conn.execute(query, params).fetchall()
    return [_row_to_out(r) for r in rows]


@router.get("/{tx_id}", response_model=TransactionOut)
def get_transaction(tx_id: int):
    conn = get_db()
    row = conn.execute("""
        SELECT t.id, t.asset_id, a.name, a.ticker, a.type,
               t.type, t.broker, t.shares, t.price, t.price_eur,
               t.currency, t.commission, t.commission_eur,
               t.date, t.notes, t.created_at, t.updated_at
        FROM transactions t JOIN assets a ON a.id = t.asset_id
        WHERE t.id = ?
    """, [tx_id]).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return _row_to_out(row)


def _current_balance(conn, asset_id: int) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN type='buy' THEN shares ELSE -shares END), 0) FROM transactions WHERE asset_id = ?",
        [asset_id],
    ).fetchone()
    return float(row[0])


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionCreate):
    conn = get_db()
    asset = conn.execute("SELECT id FROM assets WHERE id = ?", [body.asset_id]).fetchone()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if body.type == "sell":
        current = _current_balance(conn, body.asset_id)
        if body.shares > current + 1e-9:
            raise HTTPException(
                status_code=422,
                detail=f"Saldo insuficiente: tienes {current:g} participaciones, intentas vender {body.shares:g}",
            )

    conn.execute(
        """
        INSERT INTO transactions VALUES (
            nextval('transactions_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp, current_timestamp
        )
        """,
        [
            body.asset_id, body.type, body.broker, body.shares,
            body.price, body.price_eur, body.currency,
            body.commission, body.commission_eur, body.date, body.notes,
        ],
    )

    row = conn.execute("""
        SELECT t.id, t.asset_id, a.name, a.ticker, a.type,
               t.type, t.broker, t.shares, t.price, t.price_eur,
               t.currency, t.commission, t.commission_eur,
               t.date, t.notes, t.created_at, t.updated_at
        FROM transactions t JOIN assets a ON a.id = t.asset_id
        WHERE t.id = (SELECT MAX(id) FROM transactions)
    """).fetchone()
    return _row_to_out(row)


@router.put("/{tx_id}", response_model=TransactionOut)
def update_transaction(tx_id: int, body: TransactionUpdate):
    conn = get_db()
    existing = conn.execute("SELECT id FROM transactions WHERE id = ?", [tx_id]).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Transaction not found")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates["updated_at"] = "current_timestamp"
    set_parts = []
    params = []
    for k, v in updates.items():
        if k == "updated_at":
            set_parts.append(f"{k} = current_timestamp")
        else:
            set_parts.append(f"{k} = ?")
            params.append(v)

    conn.execute(
        f"UPDATE transactions SET {', '.join(set_parts)} WHERE id = ?",
        params + [tx_id],
    )

    row = conn.execute("""
        SELECT t.id, t.asset_id, a.name, a.ticker, a.type,
               t.type, t.broker, t.shares, t.price, t.price_eur,
               t.currency, t.commission, t.commission_eur,
               t.date, t.notes, t.created_at, t.updated_at
        FROM transactions t JOIN assets a ON a.id = t.asset_id
        WHERE t.id = ?
    """, [tx_id]).fetchone()
    return _row_to_out(row)


@router.delete("/{tx_id}", status_code=204)
def delete_transaction(tx_id: int):
    conn = get_db()
    existing = conn.execute("SELECT id FROM transactions WHERE id = ?", [tx_id]).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Transaction not found")
    conn.execute("DELETE FROM transactions WHERE id = ?", [tx_id])
