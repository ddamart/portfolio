"""Tests for /api/portfolio endpoints."""
import pytest
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


class TestModifiedDietz:
    """
    Verify the Modified Dietz formula via the /api/portfolio/summary?period= endpoint.

    Key invariant: period_return_eur should reflect only market gains, not capital
    injections, so it equals zero when prices don't move regardless of how much
    new money is added.
    """

    def test_no_capital_movement_pure_price_gain(self, client):
        """100 % price gain, no new buys → period_return_eur == unrealised P&L."""
        asset = create_asset(client, ticker="X", currency="EUR")
        # Buy on 2025-12-31 (before YTD 2026 period)
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2025-12-31", broker="degiro")
        seed_price(asset["id"], "2025-12-31", 100.0)   # V_ini reference price
        # Price rises to 120 by period end (in 2026)
        seed_price(asset["id"], "2026-05-01", 120.0)

        r = client.get("/api/portfolio/summary?period=ytd")
        data = r.json()
        # No transactions in YTD → CF = 0, so Modified Dietz gain == simple price gain
        assert data["period_return_eur"] == pytest.approx(200.0, abs=1.0)
        assert data["period_return_pct"] == pytest.approx(20.0, abs=0.5)

    def test_new_investment_does_not_inflate_gain(self, client):
        """
        Adding €10 000 of new capital mid-period must NOT count as performance gain.
        With flat prices (no market movement), period_return_eur should be ~0.
        """
        asset = create_asset(client, ticker="FLAT", currency="EUR")
        # Existing holding before the YTD 2026 period
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2025-12-31", broker="degiro")
        seed_price(asset["id"], "2025-12-31", 100.0)

        # Large new purchase mid-period at the same price (no price change)
        create_buy(client, asset["id"], shares=100, price=100.0, currency="EUR",
                   date="2026-03-01", broker="degiro")
        seed_price(asset["id"], "2026-03-01", 100.0)
        seed_price(asset["id"], "2026-05-01", 100.0)  # price still flat

        r = client.get("/api/portfolio/summary?period=ytd")
        data = r.json()
        # Market didn't move → real return is zero; new capital must not inflate it
        assert abs(data["period_return_eur"]) < 5.0, (
            f"New investment inflated period_return_eur to {data['period_return_eur']}"
        )
        assert abs(data["period_return_pct"]) < 0.5

    def test_period_return_equals_zero_when_flat(self, client):
        """No transactions in period, price unchanged → 0 % return."""
        asset = create_asset(client, ticker="Z", currency="EUR")
        create_buy(client, asset["id"], shares=5, price=200.0, currency="EUR",
                   date="2025-12-31", broker="degiro")
        seed_price(asset["id"], "2025-12-31", 200.0)
        seed_price(asset["id"], "2026-05-01", 200.0)

        r = client.get("/api/portfolio/summary?period=ytd")
        data = r.json()
        assert abs(data["period_return_eur"]) < 1.0
        assert abs(data["period_return_pct"]) < 0.1


class TestPeriodHoldingPct:
    """period_gain_pct must be simple ROI: gain_eur / period_invested, not Modified Dietz."""

    def test_period_gain_pct_simple_roi(self, client):
        """gain_pct = gain_eur / period_invested (not time-weighted)."""
        asset = create_asset(client, ticker="SIMPLEROI", currency="EUR")
        # Existing holding before the YTD 2026 period
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2025-12-31", broker="degiro")
        seed_price(asset["id"], "2025-12-31", 100.0)   # V_ini = 1 000
        # Large buy very late in the period (Modified Dietz would inflate %)
        create_buy(client, asset["id"], shares=90, price=100.0, currency="EUR",
                   date="2026-05-10", broker="degiro")
        seed_price(asset["id"], "2026-05-10", 100.0)
        seed_price(asset["id"], "2026-05-19", 110.0)   # 10 % price gain

        rows = client.get("/api/portfolio/holdings?period=ytd").json()
        row = next(r for r in rows if r["ticker"] == "SIMPLEROI")

        # period_invested = 1 000 + 9 000 = 10 000
        # gain_eur = 100 × 110 − 10 000 = 1 000
        # simple ROI = 1 000 / 10 000 = 10 %
        assert row["period_gain_eur"] == pytest.approx(1000.0, abs=5.0)
        assert row["period_gain_pct"] == pytest.approx(10.0, abs=0.5)

    def test_period_fields_absent_for_all(self, client):
        """When period='all' or not provided, period_return fields must be None."""
        asset = create_asset(client, ticker="A", currency="EUR")
        create_buy(client, asset["id"], shares=1, price=100.0, currency="EUR",
                   date="2025-01-02", broker="degiro")
        seed_price(asset["id"], "2025-01-02", 100.0)

        for url in ["/api/portfolio/summary", "/api/portfolio/summary?period=all"]:
            data = client.get(url).json()
            assert data["period_return_eur"] is None, f"Expected None for {url}"
            assert data["period_return_pct"] is None
            assert data["period_start_value_eur"] is None


class TestCustomDateRange:
    """Custom date_from/date_to must use historical prices, not today's."""

    def test_holdings_use_historical_price_at_date_to(self, client):
        """Holdings query must use prices as of date_to, not today's prices."""
        asset = create_asset(client, ticker="HIST", currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2025-01-02", broker="degiro")
        seed_price(asset["id"], "2025-01-02", 100.0)
        seed_price(asset["id"], "2025-03-01", 110.0)   # price at date_to
        seed_price(asset["id"], "2025-06-01", 200.0)   # today's price (much higher)

        rows = client.get("/api/portfolio/holdings?date_from=2025-01-02&date_to=2025-03-01").json()
        assert len(rows) == 1
        # current_price_eur must be the March 1 price (110), not June price (200)
        assert abs(rows[0]["current_price_eur"] - 110.0) < 0.5

    def test_summary_modified_dietz_uses_historical_v_fin(self, client):
        """
        With a past date_to, period_return must reflect the portfolio value at
        date_to, not today's value. With flat prices before date_to and a large
        gain afterwards, the period return for the custom range must be ~0.
        """
        asset = create_asset(client, ticker="HIST2", currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-12-31", broker="degiro")
        seed_price(asset["id"], "2024-12-31", 100.0)   # V_ini
        seed_price(asset["id"], "2025-03-01", 100.0)   # flat at date_to → return ~0
        seed_price(asset["id"], "2025-06-01", 500.0)   # today: would inflate if used as V_fin

        r = client.get("/api/portfolio/summary?date_from=2025-01-01&date_to=2025-03-01")
        data = r.json()
        # Prices flat within the period → return must be ~0, not +4000 €
        assert abs(data["period_return_eur"]) < 10.0, (
            f"V_fin leak: period_return_eur={data['period_return_eur']} (should be ~0)"
        )
        assert abs(data["period_return_pct"]) < 1.0

    def test_period_gain_uses_historical_price_at_date_to(self, client):
        """period_gain_eur on holdings must reflect price at date_to, not today."""
        asset = create_asset(client, ticker="HIST3", currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-12-31", broker="degiro")
        seed_price(asset["id"], "2024-12-31", 100.0)
        seed_price(asset["id"], "2025-03-01", 120.0)   # +20 % at date_to
        seed_price(asset["id"], "2025-06-01", 500.0)   # today

        rows = client.get("/api/portfolio/holdings?date_from=2025-01-01&date_to=2025-03-01").json()
        row = next(r for r in rows if r["ticker"] == "HIST3")
        # period_gain_eur = 10 × 120 − 10 × 100 = 200  (using March price, not June)
        assert row["period_gain_eur"] == pytest.approx(200.0, abs=5.0)
