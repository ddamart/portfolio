"""Tests for /api/assets endpoints."""
import json
import pytest
from unittest.mock import patch, MagicMock
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

    def test_any_isin_format_accepted(self, client):
        # ISIN validation is intentionally permissive — off-market / manual assets
        # use custom identifiers that don't follow the strict 12-char ISIN format.
        r = client.post("/api/assets", json={
            "name": "Test", "ticker": "TST", "type": "stock",
            "currency": "EUR", "manual_price": True,
            "isin": "INVALID",
        })
        assert r.status_code == 201

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

    def test_update_isin_any_format_accepted(self, client):
        # Same permissive validation as creation — any non-empty string is stored.
        asset = create_asset(client)
        r = client.put(f"/api/assets/{asset['id']}", json={"isin": "TOOSHORT"})
        assert r.status_code == 200

    def test_update_name_with_transactions(self, client):
        """Renaming an asset that has linked transactions must not throw a FK error."""
        asset = create_asset(client)
        create_fx_rate(client, "USD", 0.92)
        create_buy(client, asset["id"])
        r = client.put(f"/api/assets/{asset['id']}", json={"name": "Apple Inc (Renamed)"})
        assert r.status_code == 200
        assert r.json()["name"] == "Apple Inc (Renamed)"

    def test_update_isin_with_transactions(self, client):
        """Setting ISIN preserves all transaction data including commission_currency.

        commission_currency was added via ALTER TABLE so its physical position in
        SELECT * differs from the INSERT column order — a named SELECT must be used
        or the restore silently corrupts data / raises a type error.
        """
        asset = create_asset(client, ticker="RDDT", name="Reddit")
        create_fx_rate(client, "USD", 0.92)
        create_buy(client, asset["id"], shares=5)
        r = client.put(f"/api/assets/{asset['id']}", json={"isin": "US75734B1008"})
        assert r.status_code == 200
        assert r.json()["isin"] == "US75734B1008"
        txs = client.get("/api/transactions").json()
        assert len(txs) == 1
        tx = txs[0]
        assert tx["shares"] == 5
        assert tx["commission_currency"] == "USD"  # was corrupt when SELECT * was used

    def test_update_all_fields_with_transactions(self, client):
        """Frontend always sends all fields at once — must preserve transactions for any change."""
        asset = create_asset(client, ticker="RDDT", name="Reddit")
        create_fx_rate(client, "USD", 0.92)
        create_buy(client, asset["id"])
        markets = client.get("/api/assets/markets").json()
        valid_id = markets[0]["id"]
        r = client.put(f"/api/assets/{asset['id']}", json={
            "name": "Reddit Inc", "ticker": "RDDT", "currency": "USD",
            "isin": "US75734B1008", "market_id": valid_id,
            "manual_price": False, "image_url": None,
        })
        assert r.status_code == 200
        assert r.json()["isin"] == "US75734B1008"
        txs = client.get("/api/transactions").json()
        assert len(txs) == 1
        assert txs[0]["commission_currency"] == "USD"

    def test_update_invalid_market_id_returns_422(self, client):
        """Sending a market_id that doesn't exist must return 422, not 500."""
        asset = create_asset(client)
        r = client.put(f"/api/assets/{asset['id']}", json={"market_id": 9999})
        assert r.status_code == 422
        assert "market_id" in r.json()["detail"]

    def test_update_valid_market_id(self, client):
        """Changing market_id to an existing market works."""
        asset = create_asset(client)
        markets = client.get("/api/assets/markets").json()
        valid_id = markets[0]["id"]
        r = client.put(f"/api/assets/{asset['id']}", json={"market_id": valid_id})
        assert r.status_code == 200
        assert r.json()["market_id"] == valid_id

    def test_update_empty_body_returns_400(self, client):
        asset = create_asset(client)
        r = client.put(f"/api/assets/{asset['id']}", json={})
        assert r.status_code == 400

    def test_update_ticker(self, client):
        """Changing ticker updates the stored value (used for price lookup)."""
        asset = create_asset(client, ticker="SOH1")
        r = client.put(f"/api/assets/{asset['id']}", json={"ticker": "SOI.PA"})
        assert r.status_code == 200
        assert r.json()["ticker"] == "SOI.PA"

    def test_update_ticker_with_transactions_preserved(self, client):
        """Renaming ticker while transactions exist must keep all transactions."""
        asset = create_asset(client, ticker="SOH1")
        create_fx_rate(client, "USD", 0.92)
        create_buy(client, asset["id"])
        r = client.put(f"/api/assets/{asset['id']}", json={"ticker": "SOI.PA", "name": "Soitec"})
        assert r.status_code == 200
        # Transactions still reference the asset
        txs = client.get("/api/transactions").json()
        assert len(txs) == 1
        assert txs[0]["asset_ticker"] == "SOI.PA"

    def test_update_ticker_duplicate_rejected(self, client):
        """Can't rename to a ticker already used by another asset."""
        create_asset(client, ticker="AAPL", name="Apple")
        asset2 = create_asset(client, ticker="MSFT", name="Microsoft")
        r = client.put(f"/api/assets/{asset2['id']}", json={"ticker": "AAPL"})
        assert r.status_code == 409


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


class TestOpenFigiExchangePreference:
    """_openfigi_resolve should prefer the home-country exchange over cross-listings."""

    def _make_figi_response(self, candidates: list[dict]) -> MagicMock:
        payload = json.dumps([{"data": candidates}]).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_french_isin_prefers_paris_over_xetra(self):
        """FR ISIN should resolve to .PA ticker, not .DE cross-listing."""
        from app.services.price_fetcher import _openfigi_resolve
        candidates = [
            {"exchCode": "GY", "ticker": "SOH1", "securityType2": "Common Stock"},  # Xetra
            {"exchCode": "FP", "ticker": "SOI",  "securityType2": "Common Stock"},  # Paris
        ]
        with patch("urllib.request.urlopen", return_value=self._make_figi_response(candidates)):
            ticker, asset_type = _openfigi_resolve("FR0013227113")
        assert ticker == "SOI.PA"
        assert asset_type == "stock"

    def test_german_isin_prefers_xetra(self):
        from app.services.price_fetcher import _openfigi_resolve
        candidates = [
            {"exchCode": "UN", "ticker": "SAP",  "securityType2": "Common Stock"},  # NYSE ADR
            {"exchCode": "GY", "ticker": "SAP",  "securityType2": "Common Stock"},  # Xetra
        ]
        with patch("urllib.request.urlopen", return_value=self._make_figi_response(candidates)):
            ticker, _ = _openfigi_resolve("DE0007164600")
        assert ticker == "SAP.DE"

    def test_fallback_to_first_candidate_when_no_home_match(self):
        """Unknown ISIN country falls back to the first candidate."""
        from app.services.price_fetcher import _openfigi_resolve
        candidates = [
            {"exchCode": "GY", "ticker": "XYZ", "securityType2": "Common Stock"},
        ]
        with patch("urllib.request.urlopen", return_value=self._make_figi_response(candidates)):
            ticker, _ = _openfigi_resolve("AU0000000000")  # AU not in preference map
        assert ticker == "XYZ.DE"

    def test_canadian_tsxv_stock_prefers_tsxv_over_otc(self):
        """CA ISIN on TSX Venture (CV) should resolve to .V, not a US OTC cross-listing."""
        from app.services.price_fetcher import _openfigi_resolve
        candidates = [
            {"exchCode": "UV", "ticker": "KRKN",  "securityType2": "Common Stock"},  # US OTC
            {"exchCode": "CV", "ticker": "PNG",   "securityType2": "Common Stock"},  # TSXV
        ]
        with patch("urllib.request.urlopen", return_value=self._make_figi_response(candidates)):
            ticker, _ = _openfigi_resolve("CA49013A2002")
        assert ticker == "PNG.V"

    def test_canadian_tsx_stock_prefers_tsx_over_tsxv(self):
        """CA ISIN with both TSX (CT) and TSXV (CV) listings prefers TSX main board."""
        from app.services.price_fetcher import _openfigi_resolve
        candidates = [
            {"exchCode": "CV", "ticker": "HPS",   "securityType2": "Common Stock"},  # TSXV
            {"exchCode": "CT", "ticker": "HPS",   "securityType2": "Common Stock"},  # TSX main
        ]
        with patch("urllib.request.urlopen", return_value=self._make_figi_response(candidates)):
            ticker, _ = _openfigi_resolve("CA4071671094")
        assert ticker == "HPS.TO"

    def test_returns_none_on_empty_response(self):
        from app.services.price_fetcher import _openfigi_resolve
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([{}]).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            ticker, asset_type = _openfigi_resolve("FR0013227113")
        assert ticker is None
        assert asset_type is None


class TestBalanceAssetDeleteAndClear:
    def _create_balance_asset(self, client, ticker="CARTBAL"):
        r = client.post("/api/assets", json={
            "name": "Cartera Test", "ticker": ticker,
            "type": "balance", "currency": "EUR", "manual_price": True,
        })
        assert r.status_code == 201, r.text
        return r.json()

    def _add_entry(self, client, asset_id, etype, amount, date="2024-01-15"):
        r = client.post(f"/api/balance/{asset_id}", json={
            "date": date, "type": etype, "amount_eur": amount,
        })
        assert r.status_code == 201, r.text
        return r.json()

    def test_clear_balance_entries_deletes_all_entries(self, client):
        asset = self._create_balance_asset(client)
        self._add_entry(client, asset["id"], "snapshot", 10000)
        self._add_entry(client, asset["id"], "deposit", 5000)
        self._add_entry(client, asset["id"], "withdrawal", 1000)

        r = client.delete(f"/api/assets/{asset['id']}/prices")
        assert r.status_code == 204

        entries = client.get(f"/api/balance/{asset['id']}").json()
        assert entries == []

    def test_clear_balance_leaves_asset_intact(self, client):
        asset = self._create_balance_asset(client)
        self._add_entry(client, asset["id"], "snapshot", 5000)

        client.delete(f"/api/assets/{asset['id']}/prices")

        assets = client.get("/api/assets").json()
        assert any(a["id"] == asset["id"] for a in assets)

    def test_delete_balance_asset_with_entries_succeeds(self, client):
        asset = self._create_balance_asset(client)
        self._add_entry(client, asset["id"], "snapshot", 10000)
        self._add_entry(client, asset["id"], "deposit", 5000)

        r = client.delete(f"/api/assets/{asset['id']}")
        assert r.status_code == 204

        assets = client.get("/api/assets").json()
        assert not any(a["id"] == asset["id"] for a in assets)

    def test_delete_balance_asset_removes_entries_too(self, client):
        asset = self._create_balance_asset(client)
        self._add_entry(client, asset["id"], "deposit", 3000)

        client.delete(f"/api/assets/{asset['id']}")

        r = client.get(f"/api/balance/{asset['id']}")
        assert r.status_code == 404
