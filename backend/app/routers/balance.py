from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.models.balance import BalanceEntryCreate, BalanceEntryOut

router = APIRouter(prefix="/api/balance", tags=["balance"])


@router.get("/{asset_id}", response_model=list[BalanceEntryOut])
def list_entries(asset_id: int):
    """List all balance entries for an asset, ordered by date descending."""
    conn = get_db()
    asset = conn.execute("SELECT id FROM assets WHERE id = ? AND type = 'balance'", [asset_id]).fetchone()
    if not asset:
        raise HTTPException(status_code=404, detail="Balance asset not found")
    rows = conn.execute(
        """
        SELECT id, asset_id, date, type, amount_eur, notes, created_at
        FROM balance_entries
        WHERE asset_id = ?
        ORDER BY date DESC, id DESC
        """,
        [asset_id],
    ).fetchall()
    return [
        BalanceEntryOut(
            id=row[0],
            asset_id=row[1],
            date=row[2],
            type=row[3],
            amount_eur=float(row[4]),
            notes=row[5],
            created_at=row[6],
        )
        for row in rows
    ]


@router.post("/{asset_id}", response_model=BalanceEntryOut, status_code=201)
def create_entry(asset_id: int, body: BalanceEntryCreate):
    """Insert a new balance entry (deposit, withdrawal, or snapshot)."""
    conn = get_db()
    asset = conn.execute("SELECT id FROM assets WHERE id = ? AND type = 'balance'", [asset_id]).fetchone()
    if not asset:
        raise HTTPException(status_code=404, detail="Balance asset not found")
    if body.type not in ("deposit", "withdrawal", "snapshot"):
        raise HTTPException(status_code=422, detail="type must be deposit, withdrawal, or snapshot")
    row = conn.execute(
        """
        INSERT INTO balance_entries (id, asset_id, date, type, amount_eur, notes)
        VALUES (nextval('balance_entries_id_seq'), ?, ?, ?, ?, ?)
        RETURNING id, asset_id, date, type, amount_eur, notes, created_at
        """,
        [asset_id, body.date, body.type, body.amount_eur, body.notes],
    ).fetchone()
    return BalanceEntryOut(
        id=row[0],
        asset_id=row[1],
        date=row[2],
        type=row[3],
        amount_eur=float(row[4]),
        notes=row[5],
        created_at=row[6],
    )


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: int):
    """Delete a balance entry by its id."""
    conn = get_db()
    existing = conn.execute("SELECT id FROM balance_entries WHERE id = ?", [entry_id]).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Balance entry not found")
    conn.execute("DELETE FROM balance_entries WHERE id = ?", [entry_id])
