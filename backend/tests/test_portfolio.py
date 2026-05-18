"""Tests for /api/portfolio endpoints."""
from .conftest import create_asset, create_buy, create_fx_rate
import app.database as db_module


def seed_price(asset_id, date, price, currency="EUR", price_eur=None):
    conn = db_module.get_db()
    price_eur = price_eur if price_eur is not None else price
    conn.execute(
        "INSERT INTO prices VALUES (?, ?, ?, ?, ?) ON CONFLICT DO UPDATE SET price=excluded.price, price_eur=excluded.price_eur",
        [asset_id, date, price, currency, price_eur],
    )


class TestPortfolioSummary:
    def test_summary_empty(self, client):
        r = client.get("/api/portfolio/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total_value_eur"] == 0.0
        assert data["total_invested_eur"] == 0.0
        assert data["total_pnl_eur"] == 0.0

    def test_summary_after_buy(self, client):
        asset = create_asset(client, currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR")
        seed_price(asset["id"], "2024-01-02", 110.0)
        r = client.get("/api/portfolio/summary")
        data = r.json()
        assert data["total_value_eur"] == pytest.approx(1100.0, abs=1.0)
        assert data["total_invested_eur"] == pytest.approx(1000.0, abs=1.0)
        assert data["total_pnl_eur"] == pytest.approx(100.0, abs=1.0)

    def test_summary_excludes_sold_assets(self, client):
        asset = create_asset(client, currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR")
        # Sell all
        client.post("/api/transactions", json={
            "asset_id": asset["id"], "type": "sell", "broker": "degiro",
            "shares": 10, "price": 110.0, "currency": "EUR",
            "commission": 0, "date": "2024-06-01",
        })
        seed_price(asset["id"], "2024-06-01", 110.0)
        r = client.get("/api/portfolio/summary")
        data = r.json()
        # After selling all, value should be 0
        assert data["total_value_eur"] == pytest.approx(0.0, abs=1.0)


class TestPortfolioHoldings:
    def test_holdings_empty(self, client):
        r = client.get("/api/portfolio/holdings")
        assert r.status_code == 200
        assert r.json() == []

    def test_holding_row_shape(self, client):
        asset = create_asset(client, ticker="VOO", currency="EUR")
        create_buy(client, asset["id"], shares=5, price=400.0, currency="EUR")
        seed_price(asset["id"], "2024-01-02", 410.0)
        rows = client.get("/api/portfolio/holdings").json()
        assert len(rows) == 1
        row = rows[0]
        for key in ("asset_id", "name", "ticker", "type", "currency", "total_shares",
                    "avg_buy_price_eur", "avg_buy_price", "current_price_eur",
                    "value_eur", "pnl_eur", "gain_pct", "allocation_pct"):
            assert key in row, f"Missing field: {key}"

    def test_total_shares_correct_after_buy(self, client):
        asset = create_asset(client, currency="EUR")
        create_buy(client, asset["id"], shares=7, price=100.0, currency="EUR")
        create_buy(client, asset["id"], shares=3, price=110.0, currency="EUR")
        seed_price(asset["id"], "2024-01-02", 105.0)
        rows = client.get("/api/portfolio/holdings").json()
        assert abs(rows[0]["total_shares"] - 10.0) < 1e-6

    def test_total_shares_after_partial_sell(self, client):
        asset = create_asset(client, currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR")
        client.post("/api/transactions", json={
            "asset_id": asset["id"], "type": "sell", "broker": "degiro",
            "shares": 3, "price": 110.0, "currency": "EUR",
            "commission": 0, "date": "2024-06-01",
        })
        seed_price(asset["id"], "2024-06-01", 110.0)
        rows = client.get("/api/portfolio/holdings").json()
        assert abs(rows[0]["total_shares"] - 7.0) < 1e-6

    def test_sold_out_asset_not_in_holdings(self, client):
        asset = create_asset(client, currency="EUR")
        create_buy(client, asset["id"], shares=5, price=100.0, currency="EUR")
        client.post("/api/transactions", json={
            "asset_id": asset["id"], "type": "sell", "broker": "degiro",
            "shares": 5, "price": 110.0, "currency": "EUR",
            "commission": 0, "date": "2024-06-01",
        })
        seed_price(asset["id"], "2024-06-01", 110.0)
        rows = client.get("/api/portfolio/holdings").json()
        assert rows == []

    def test_avg_buy_price_eur_weighted(self, client):
        """Avg buy price = weighted by shares, not simple average."""
        asset = create_asset(client, currency="EUR")
        # 10 shares @ 100 → cost 1000
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR")
        # 0 shares @ 200 → can't have 0, use 1 share @ 200 → cost 200 → avg = 1200/11
        create_buy(client, asset["id"], shares=1, price=200.0, currency="EUR")
        seed_price(asset["id"], "2024-01-02", 105.0)
        rows = client.get("/api/portfolio/holdings").json()
        expected_avg = (10 * 100 + 1 * 200) / 11
        assert abs(rows[0]["avg_buy_price_eur"] - expected_avg) < 0.01

    def test_avg_buy_price_native_currency(self, client):
        """avg_buy_price is in native currency (USD), avg_buy_price_eur is converted."""
        asset = create_asset(client, currency="USD")
        create_fx_rate(client, "USD", 0.90, date="2024-01-02")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="USD",
                   date="2024-01-02", broker="degiro")
        seed_price(asset["id"], "2024-01-02", 100.0, currency="USD", price_eur=90.0)
        rows = client.get("/api/portfolio/holdings").json()
        row = rows[0]
        assert abs(row["avg_buy_price"] - 100.0) < 0.01       # native USD
        assert abs(row["avg_buy_price_eur"] - 90.0) < 0.01    # EUR-converted

    def test_pnl_positive_when_price_up(self, client):
        asset = create_asset(client, currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR")
        seed_price(asset["id"], "2024-06-01", 150.0)
        rows = client.get("/api/portfolio/holdings").json()
        assert rows[0]["pnl_eur"] > 0

    def test_pnl_negative_when_price_down(self, client):
        asset = create_asset(client, currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR")
        seed_price(asset["id"], "2024-06-01", 80.0)
        rows = client.get("/api/portfolio/holdings").json()
        assert rows[0]["pnl_eur"] < 0

    def test_holdings_without_prices_still_shows(self, client):
        """Holdings with no price data return row with nulls, not 404."""
        asset = create_asset(client, currency="EUR")
        create_buy(client, asset["id"], shares=5, price=100.0, currency="EUR")
        rows = client.get("/api/portfolio/holdings").json()
        assert len(rows) == 1
        assert rows[0]["current_price_eur"] is None

    def test_allocation_pct_sums_to_100(self, client):
        a1 = create_asset(client, ticker="AAPL", currency="EUR")
        a2 = create_asset(client, ticker="MSFT", currency="EUR")
        create_buy(client, a1["id"], shares=5, price=100.0, currency="EUR")
        create_buy(client, a2["id"], shares=5, price=200.0, currency="EUR")
        seed_price(a1["id"], "2024-01-02", 100.0)
        seed_price(a2["id"], "2024-01-02", 200.0)
        rows = client.get("/api/portfolio/holdings").json()
        total_pct = sum(r["allocation_pct"] for r in rows if r["allocation_pct"])
        assert abs(total_pct - 100.0) < 0.1


class TestPortfolioChart:
    def test_chart_empty(self, client):
        r = client.get("/api/portfolio/chart?period=all")
        assert r.status_code == 200
        assert r.json() == []

    def test_chart_returns_date_value_pairs(self, client):
        asset = create_asset(client, currency="EUR")
        create_buy(client, asset["id"], shares=5, price=100.0, currency="EUR",
                   date="2024-01-02")
        seed_price(asset["id"], "2024-01-02", 100.0)
        seed_price(asset["id"], "2024-01-03", 105.0)
        seed_price(asset["id"], "2024-01-04", 110.0)
        r = client.get("/api/portfolio/chart?period=all")
        data = r.json()
        assert len(data) >= 1
        assert "date" in data[0]
        assert "value_eur" in data[0]

    def test_chart_values_are_numeric(self, client):
        asset = create_asset(client, currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-01-02")
        seed_price(asset["id"], "2024-01-02", 100.0)
        data = client.get("/api/portfolio/chart?period=all").json()
        for point in data:
            assert isinstance(point["value_eur"], (int, float))

    def test_chart_filtered_by_date_range(self, client):
        asset = create_asset(client, currency="EUR")
        create_buy(client, asset["id"], shares=5, price=100.0, currency="EUR",
                   date="2024-01-02")
        for d in ["2024-01-02", "2024-03-01", "2024-06-01", "2024-12-01"]:
            seed_price(asset["id"], d, 100.0)
        r = client.get("/api/portfolio/chart?date_from=2024-03-01&date_to=2024-07-01")
        data = r.json()
        for point in data:
            assert point["date"] >= "2024-03-01"
            assert point["date"] <= "2024-07-01"


import pytest
