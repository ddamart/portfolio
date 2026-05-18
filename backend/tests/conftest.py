"""Shared fixtures for all tests."""
import pytest
import duckdb
from unittest.mock import patch
from fastapi.testclient import TestClient

import app.database as db_module
from app.database import _apply_schema, _seed_markets
from app.main import app


@pytest.fixture
def client(tmp_path):
    """
    Each test gets a fresh DuckDB file in a temp directory.
    With threading.local, every thread (test thread + FastAPI worker threads)
    opens its own connection to the same file — correct DuckDB multi-thread pattern.
    """
    db_file = str(tmp_path / "test.duckdb")

    # Bootstrap schema on the temp file
    bootstrap = duckdb.connect(db_file)
    _apply_schema(bootstrap)
    _seed_markets(bootstrap)
    bootstrap.close()

    # Tell get_db() where the file is; close any stale thread-local conn
    if getattr(db_module._local, "conn", None):
        db_module._local.conn.close()
        db_module._local.conn = None
    db_module._db_path = db_file

    with patch("app.main.init_db"), patch("app.main.close_db"):
        with TestClient(app) as c:
            yield c

    # Close this thread's connection if opened during the test
    if getattr(db_module._local, "conn", None):
        db_module._local.conn.close()
        db_module._local.conn = None
    db_module._db_path = ""


# ---------------------------------------------------------------------------
# Helpers reused across test modules
# ---------------------------------------------------------------------------

def create_asset(client, ticker="AAPL", name="Apple Inc", type_="stock", currency="USD"):
    r = client.post("/api/assets", json={
        "name": name, "ticker": ticker, "type": type_,
        "currency": currency, "manual_price": True,
    })
    assert r.status_code == 201, r.text
    return r.json()


def create_fx_rate(client, from_ccy, rate, date="2024-01-02"):
    """Insert an FX rate directly via DB (no public endpoint)."""
    conn = db_module.get_db()
    conn.execute(
        "INSERT INTO fx_rates VALUES (?, ?, 'EUR', ?) ON CONFLICT DO UPDATE SET rate = excluded.rate",
        [date, from_ccy, rate],
    )


def create_buy(client, asset_id, shares=10, price=100.0, currency="USD",
               date="2024-01-02", broker="degiro"):
    r = client.post("/api/transactions", json={
        "asset_id": asset_id, "type": "buy", "broker": broker,
        "shares": shares, "price": price, "currency": currency,
        "commission": 0, "date": date,
    })
    assert r.status_code == 201, r.text
    return r.json()


def create_sell(client, asset_id, shares=5, price=120.0, currency="USD",
                date="2024-06-01", broker="degiro"):
    r = client.post("/api/transactions", json={
        "asset_id": asset_id, "type": "sell", "broker": broker,
        "shares": shares, "price": price, "currency": currency,
        "commission": 0, "date": date,
    })
    return r
