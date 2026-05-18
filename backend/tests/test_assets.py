"""Tests for /api/assets endpoints."""
import pytest
from .conftest import create_asset, create_buy, create_fx_rate
import app.database as db_module


class TestListAssets:
    def test_empty(self, client):
        r = client.get("/api/assets")
        assert r.status_code == 200
        assert r.json() == []

    def test_in_portfolio_false_when_no_transactions(self, client):
        create_asset(client)
        assets = client.get("/api/assets").json()
        assert len(assets) == 1
        assert assets[0]["in_portfolio"] is False

    def test_in_portfolio_true_after_buy(self, client):
        asset = create_asset(client)
        create_fx_rate(client, "USD", 0.92)
        create_buy(client, asset["id"])
        assets = client.get("/api/assets").json()
        assert assets[0]["in_portfolio"] is True

    def test_in_portfolio_false_after_selling_all(self, client):
        asset = create_asset(client)
        create_fx_rate(client, "USD", 0.92)
        create_buy(client, asset["id"], shares=10)
        # sell all
        r = client.post("/api/transactions", json={
            "asset_id": asset["id"], "type": "sell", "broker": "degiro",
            "shares": 10, "price": 110.0, "currency": "USD",
            "commission": 0, "date": "2024-06-01",
        })
        assert r.status_code == 201
        assets = client.get("/api/assets").json()
        assert assets[0]["in_portfolio"] is False

    def test_response_shape(self, client):
        create_asset(client, ticker="VOO", name="Vanguard S&P 500", type_="etf", currency="USD")
        a = client.get("/api/assets").json()[0]
        required = {"id", "name", "ticker", "type", "currency", "market_id",
                    "image_url", "manual_price", "isin", "created_at", "in_portfolio"}
        assert required.issubset(a.keys())

    def test_sorted_by_name(self, client):
        create_asset(client, ticker="ZZZ", name="Zebra Corp")
        create_asset(client, ticker="AAA", name="Alpha Corp")
        names = [a["name"] for a in client.get("/api/assets").json()]
        assert names == sorted(names)


class TestCreateAsset:
    def test_create_returns_201(self, client):
        r = client.post("/api/assets", json={
            "name": "Apple", "ticker": "AAPL", "type": "stock",
            "currency": "USD", "manual_price": True,
        })
        assert r.status_code == 201
        data = r.json()
        assert data["ticker"] == "AAPL"
        assert data["in_portfolio"] is False

    def test_duplicate_ticker_rejected(self, client):
        create_asset(client)
        r = client.post("/api/assets", json={
            "name": "Apple 2", "ticker": "AAPL", "type": "stock",
            "currency": "USD", "manual_price": True,
        })
        assert r.status_code == 409

    def test_invalid_isin_rejected(self, client):
        r = client.post("/api/assets", json={
            "name": "Test", "ticker": "TST", "type": "stock",
            "currency": "EUR", "manual_price": True,
            "isin": "INVALID",
        })
        assert r.status_code == 422

    def test_valid_isin_accepted(self, client):
        r = client.post("/api/assets", json={
            "name": "Santander", "ticker": "SAN.MC", "type": "stock",
            "currency": "EUR", "manual_price": True,
            "isin": "ES0113900J37",
        })
        assert r.status_code == 201
        assert r.json()["isin"] == "ES0113900J37"


class TestUpdateAsset:
    def test_update_name(self, client):
        asset = create_asset(client)
        r = client.put(f"/api/assets/{asset['id']}", json={"name": "Apple Inc (Updated)"})
        assert r.status_code == 200
        assert r.json()["name"] == "Apple Inc (Updated)"

    def test_update_nonexistent(self, client):
        r = client.put("/api/assets/9999", json={"name": "Ghost"})
        assert r.status_code == 404

    def test_update_isin_validated(self, client):
        asset = create_asset(client)
        r = client.put(f"/api/assets/{asset['id']}", json={"isin": "TOOSHORT"})
        assert r.status_code == 422


class TestDeleteAsset:
    def test_delete_asset_no_transactions(self, client):
        asset = create_asset(client)
        r = client.delete(f"/api/assets/{asset['id']}")
        assert r.status_code == 204
        assert client.get("/api/assets").json() == []

    def test_delete_nonexistent(self, client):
        r = client.delete("/api/assets/9999")
        assert r.status_code == 404


class TestSearchAssets:
    def test_search_by_ticker(self, client):
        create_asset(client, ticker="AAPL", name="Apple")
        create_asset(client, ticker="MSFT", name="Microsoft")
        results = client.get("/api/assets/search?q=AAPL").json()
        assert len(results) == 1
        assert results[0]["ticker"] == "AAPL"

    def test_search_by_name(self, client):
        create_asset(client, ticker="AAPL", name="Apple Inc")
        results = client.get("/api/assets/search?q=apple").json()
        assert len(results) == 1

    def test_search_empty_query_returns_all(self, client):
        create_asset(client, ticker="AAPL", name="Apple")
        create_asset(client, ticker="MSFT", name="Microsoft")
        results = client.get("/api/assets/search?q=").json()
        assert len(results) == 2


class TestPriceImport:
    def test_import_eur_prices(self, client):
        asset = client.post("/api/assets", json={
            "name": "Fondo Openbank", "ticker": "ES0170960015", "type": "fund",
            "currency": "EUR", "manual_price": True,
        }).json()

        rows = [
            {"date": "2025-01-02", "price": 10.50},
            {"date": "2025-01-03", "price": 10.75},
            {"date": "2025-01-06", "price": 10.60},
        ]
        r = client.post(f"/api/assets/{asset['id']}/prices/import", json=rows)
        assert r.status_code == 200
        data = r.json()
        assert data["inserted"] == 3
        assert data["errors"] == []

    def test_import_stores_price_eur_equal_price_for_eur(self, client):
        asset = client.post("/api/assets", json={
            "name": "Fondo EUR", "ticker": "FUNDESP", "type": "fund",
            "currency": "EUR", "manual_price": True,
        }).json()
        client.post(f"/api/assets/{asset['id']}/prices/import", json=[
            {"date": "2025-01-02", "price": 123.45},
        ])
        conn = db_module.get_db()
        row = conn.execute("SELECT price, price_eur FROM prices WHERE asset_id = ?", [asset["id"]]).fetchone()
        assert abs(float(row[0]) - 123.45) < 0.001
        assert abs(float(row[1]) - 123.45) < 0.001  # EUR → EUR, rate = 1.0

    def test_import_upserts_existing(self, client):
        asset = client.post("/api/assets", json={
            "name": "Fondo", "ticker": "FUNDUP", "type": "fund",
            "currency": "EUR", "manual_price": True,
        }).json()
        client.post(f"/api/assets/{asset['id']}/prices/import", json=[{"date": "2025-01-02", "price": 10.0}])
        client.post(f"/api/assets/{asset['id']}/prices/import", json=[{"date": "2025-01-02", "price": 11.0}])
        conn = db_module.get_db()
        row = conn.execute("SELECT price FROM prices WHERE asset_id = ?", [asset["id"]]).fetchone()
        assert abs(float(row[0]) - 11.0) < 0.001  # overwritten

    def test_import_nonexistent_asset(self, client):
        r = client.post("/api/assets/9999/prices/import", json=[{"date": "2025-01-02", "price": 10.0}])
        assert r.status_code == 404
