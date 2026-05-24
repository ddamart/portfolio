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

    def test_cambio_uses_price_difference_times_quantity(self, client):
        """cambio_eur = total_shares × (price_date_to − price_date_from)."""
        asset = create_asset(client, ticker="SIMPLEROI", currency="EUR")
        # Existing holding before the YTD 2026 period
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2025-12-31", broker="degiro")
        seed_price(asset["id"], "2025-12-31", 100.0)   # price_ini = 100
        # Large buy very late in the period
        create_buy(client, asset["id"], shares=90, price=100.0, currency="EUR",
                   date="2026-05-10", broker="degiro")
        seed_price(asset["id"], "2026-05-10", 100.0)
        seed_price(asset["id"], "2026-05-19", 110.0)   # price_fin = 110

        rows = client.get("/api/portfolio/holdings?period=ytd").json()
        row = next(r for r in rows if r["ticker"] == "SIMPLEROI")

        # cambio_eur = 100 × (110 − 100) = 1 000
        # cambio_pct = 1 000 / (100 × 100) × 100 = 10 %
        assert row["cambio_eur"] == pytest.approx(1000.0, abs=5.0)
        assert row["cambio_pct"] == pytest.approx(10.0, abs=0.5)

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


class TestChartPriceFillForward:
    """
    Regression: when the chart window starts on date D, assets whose last price
    is on D-1 (or earlier) were excluded from value_eur but still counted in
    invested_eur, producing a large false negative G/P on the first chart point.

    The fix uses ASOF JOIN so prices outside the window are filled forward.
    """

    def test_asset_with_prior_price_included_on_window_start(self, client):
        """
        Asset A: bought before window, last price before window start.
        Asset B: bought on window start, price on window start (anchors date_spine).
        Without ASOF fix: A excluded from value on D, G/P = value_B - (cost_A + cost_B) < 0.
        With fix: A uses its last price via fill-forward → G/P is correct.
        """
        # Asset A: 10 shares @ 200 EUR bought on 2024-01-01, price only on 2024-01-01
        a = create_asset(client, ticker="OLDASSET", currency="EUR")
        create_buy(client, a["id"], shares=10, price=200.0, currency="EUR",
                   date="2024-01-01", broker="degiro")
        seed_price(a["id"], "2024-01-01", 200.0)  # last price BEFORE window

        # Asset B: 5 shares @ 50 EUR bought on 2024-01-02, prices from 2024-01-02 onward
        b = create_asset(client, ticker="NEWASSET", currency="EUR")
        create_buy(client, b["id"], shares=5, price=50.0, currency="EUR",
                   date="2024-01-02", broker="degiro")
        seed_price(b["id"], "2024-01-02", 50.0)
        seed_price(b["id"], "2024-01-03", 55.0)

        # cost_A = 10 × 200 = 2 000, cost_B = 5 × 50 = 250, total = 2 250
        # value on 2024-01-02 (with fill-forward): A = 10×200 = 2000, B = 5×50 = 250 → 2 250
        # G/P = 2 250 - 2 250 = 0
        r = client.get("/api/portfolio/chart?date_from=2024-01-02&date_to=2024-01-03")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        first = next(d for d in data if d["date"] == "2024-01-02")
        # Without fix: first["value_eur"] would be ~250 (only B), making G/P = 250-2250 = -2000
        assert first["value_eur"] == pytest.approx(2250.0, abs=5.0), (
            f"Asset A price not filled forward: value={first['value_eur']} (expected ~2250)"
        )
        invested = first.get("invested_eur")
        if invested is not None:
            gp = first["value_eur"] - invested
            assert gp == pytest.approx(0.0, abs=5.0), (
                f"False G/P on first chart point: {gp} (expected ~0)"
            )

    def test_first_window_day_matches_wider_window(self, client):
        """
        Chart value on D must be identical whether the window starts on D or D-1.
        This is the exact symptom the user reported.
        """
        a = create_asset(client, ticker="ASSET_PREV", currency="EUR")
        create_buy(client, a["id"], shares=8, price=100.0, currency="EUR",
                   date="2024-01-01", broker="degiro")
        seed_price(a["id"], "2024-01-01", 100.0)  # last price before window

        b = create_asset(client, ticker="ASSET_DAY", currency="EUR")
        create_buy(client, b["id"], shares=3, price=50.0, currency="EUR",
                   date="2024-01-02", broker="degiro")
        seed_price(b["id"], "2024-01-02", 50.0)

        # Window starting ON 2024-01-02
        r1 = client.get("/api/portfolio/chart?date_from=2024-01-02&date_to=2024-01-04")
        data1 = {d["date"]: d for d in r1.json()}

        # Window starting one day BEFORE (2024-01-01)
        r2 = client.get("/api/portfolio/chart?date_from=2024-01-01&date_to=2024-01-04")
        data2 = {d["date"]: d for d in r2.json()}

        assert "2024-01-02" in data1 and "2024-01-02" in data2
        v1 = data1["2024-01-02"]["value_eur"]
        v2 = data2["2024-01-02"]["value_eur"]
        assert v1 == pytest.approx(v2, abs=1.0), (
            f"value_eur on 2024-01-02 differs by window start: {v1} vs {v2}"
        )


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

    def test_cambio_uses_historical_price_at_date_to(self, client):
        """cambio_eur on holdings must reflect price at date_to, not today."""
        asset = create_asset(client, ticker="HIST3", currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-12-31", broker="degiro")
        seed_price(asset["id"], "2024-12-31", 100.0)
        seed_price(asset["id"], "2025-03-01", 120.0)   # +20 % at date_to
        seed_price(asset["id"], "2025-06-01", 500.0)   # today

        rows = client.get("/api/portfolio/holdings?date_from=2025-01-01&date_to=2025-03-01").json()
        row = next(r for r in rows if r["ticker"] == "HIST3")
        # cambio_eur = 10 × (120 − 100) = 200  (using March price, not June)
        assert row["cambio_eur"] == pytest.approx(200.0, abs=5.0)


class TestBalanceSummaryMetrics:
    """Balance account deposits must appear in portfolio-level summary metrics."""

    def _create_balance_asset(self, client, ticker="OBANKBAL"):
        r = client.post("/api/assets", json={
            "name": "Openbank Balance", "ticker": ticker,
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

    def test_balance_deposit_counts_in_total_invested_ever(self, client):
        """total_invested_ever_eur must include balance deposits."""
        bal = self._create_balance_asset(client)
        self._add_entry(client, bal["id"], "deposit", 5000.0, "2024-01-15")
        self._add_entry(client, bal["id"], "snapshot", 5200.0, "2024-06-01")

        data = client.get("/api/portfolio/summary").json()
        assert data["total_invested_ever_eur"] == pytest.approx(5000.0, abs=1.0), (
            f"Expected balance deposit 5000 in total_invested_ever_eur, got {data['total_invested_ever_eur']}"
        )

    def test_balance_deposit_plus_tx_buys_in_total_invested_ever(self, client):
        """total_invested_ever_eur = sum of all buy costs + all balance deposits."""
        # Regular tx asset
        stock = create_asset(client, ticker="STOCK1", currency="EUR")
        create_buy(client, stock["id"], shares=10, price=100.0, currency="EUR")
        seed_price(stock["id"], "2024-01-02", 110.0)

        # Balance asset with deposit
        bal = self._create_balance_asset(client)
        self._add_entry(client, bal["id"], "deposit", 3000.0, "2024-02-01")
        self._add_entry(client, bal["id"], "snapshot", 3100.0, "2024-06-01")

        data = client.get("/api/portfolio/summary").json()
        # 10 * 100 (buy) + 3000 (deposit) = 4000
        assert data["total_invested_ever_eur"] == pytest.approx(4000.0, abs=1.0), (
            f"Expected 4000, got {data['total_invested_ever_eur']}"
        )

    def test_balance_value_in_total_value(self, client):
        """Latest balance snapshot is included in total portfolio value."""
        bal = self._create_balance_asset(client)
        self._add_entry(client, bal["id"], "snapshot", 12000.0, "2024-06-01")

        data = client.get("/api/portfolio/summary").json()
        assert data["total_value_eur"] == pytest.approx(12000.0, abs=1.0)

    def test_multiple_deposits_sum_correctly(self, client):
        """Multiple deposits across dates all count towards total_invested_ever_eur."""
        bal = self._create_balance_asset(client)
        self._add_entry(client, bal["id"], "deposit", 1000.0, "2024-01-01")
        self._add_entry(client, bal["id"], "deposit", 2000.0, "2024-04-01")
        self._add_entry(client, bal["id"], "deposit", 500.0, "2024-07-01")
        self._add_entry(client, bal["id"], "snapshot", 3800.0, "2024-08-01")

        data = client.get("/api/portfolio/summary").json()
        assert data["total_invested_ever_eur"] == pytest.approx(3500.0, abs=1.0)


class TestCambioEur:
    """cambio_eur = total_shares × (price_date_to − price_date_from)."""

    def test_cambio_basic(self, client):
        asset = create_asset(client, ticker="CMBTEST", currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-12-31", broker="degiro")
        seed_price(asset["id"], "2024-12-31", 100.0)
        seed_price(asset["id"], "2025-03-01", 130.0)

        rows = client.get("/api/portfolio/holdings?date_from=2025-01-01&date_to=2025-03-01").json()
        row = next(r for r in rows if r["ticker"] == "CMBTEST")
        # cambio = 10 × (130 − 100) = 300
        assert row["cambio_eur"] == pytest.approx(300.0, abs=1.0)
        # cambio_pct = 300 / 1000 × 100 = 30 %
        assert row["cambio_pct"] == pytest.approx(30.0, abs=0.5)

    def test_cambio_zero_when_price_unchanged(self, client):
        asset = create_asset(client, ticker="FLATPRICE", currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-12-31", broker="degiro")
        seed_price(asset["id"], "2024-12-31", 100.0)
        seed_price(asset["id"], "2025-06-01", 100.0)

        rows = client.get("/api/portfolio/holdings?date_from=2025-01-01&date_to=2025-06-01").json()
        row = next(r for r in rows if r["ticker"] == "FLATPRICE")
        assert row["cambio_eur"] == pytest.approx(0.0, abs=1.0)

    def test_cambio_negative_when_price_falls(self, client):
        asset = create_asset(client, ticker="FALLING", currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-12-31", broker="degiro")
        seed_price(asset["id"], "2024-12-31", 100.0)
        seed_price(asset["id"], "2025-06-01", 80.0)

        rows = client.get("/api/portfolio/holdings?date_from=2025-01-01&date_to=2025-06-01").json()
        row = next(r for r in rows if r["ticker"] == "FALLING")
        # cambio = 10 × (80 − 100) = −200
        assert row["cambio_eur"] == pytest.approx(-200.0, abs=1.0)

    def test_cambio_fallback_when_no_period_start_price(self, client):
        """When asset has no price at date_from, avg_buy_price_eur is used as fallback."""
        asset = create_asset(client, ticker="NEWASSET", currency="EUR")
        # Bought during the period — no historical price at date_from
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2025-03-01", broker="degiro")
        seed_price(asset["id"], "2025-03-01", 100.0)
        seed_price(asset["id"], "2025-06-01", 120.0)

        rows = client.get("/api/portfolio/holdings?date_from=2025-01-01&date_to=2025-06-01").json()
        row = next(r for r in rows if r["ticker"] == "NEWASSET")
        # Fallback: price_ini = avg_buy_price = 100, so cambio = 10 × (120 - 100) = 200
        assert row["cambio_eur"] == pytest.approx(200.0, abs=1.0)

    def test_cambio_none_without_period(self, client):
        """Without a date range, cambio_eur must be None."""
        asset = create_asset(client, ticker="NOPERIOD", currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-01-02", broker="degiro")
        seed_price(asset["id"], "2024-01-02", 110.0)

        rows = client.get("/api/portfolio/holdings").json()
        row = next(r for r in rows if r["ticker"] == "NOPERIOD")
        assert row["cambio_eur"] is None


class TestAllocationByInvested:
    """allocation_pct must use cost basis (invested), not market value."""

    def test_allocation_reflects_invested_not_value(self, client):
        a1 = create_asset(client, ticker="A1", currency="EUR")
        a2 = create_asset(client, ticker="A2", currency="EUR")
        # Both invested €1000, but A1 has grown 2× and A2 is flat
        create_buy(client, a1["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-01-02", broker="degiro")
        create_buy(client, a2["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-01-02", broker="degiro")
        seed_price(a1["id"], "2024-01-02", 200.0)  # A1 grew 2×
        seed_price(a2["id"], "2024-01-02", 100.0)  # A2 flat

        rows = client.get("/api/portfolio/holdings").json()
        allocs = {r["ticker"]: r["allocation_pct"] for r in rows}
        # Both invested €1000 out of €2000 total → 50% each (not 66% / 33% by value)
        assert allocs["A1"] == pytest.approx(50.0, abs=1.0)
        assert allocs["A2"] == pytest.approx(50.0, abs=1.0)
        assert sum(allocs.values()) == pytest.approx(100.0, abs=0.5)


class TestBalanceContributionDateFilter:
    """balance_contributions_eur must be filtered to <= date_to (bug fix)."""

    def _create_balance_asset(self, client, ticker="BFIXTEST"):
        r = client.post("/api/assets", json={
            "name": "Balance Fix Test", "ticker": ticker,
            "type": "balance", "currency": "EUR", "manual_price": True,
        })
        assert r.status_code == 201, r.text
        return r.json()

    def _add_entry(self, client, asset_id, entry_type, amount, date):
        r = client.post(f"/api/balance/{asset_id}", json={
            "date": date, "type": entry_type, "amount_eur": amount,
        })
        assert r.status_code == 201, r.text

    def test_contributions_filtered_by_date_to(self, client):
        bal = self._create_balance_asset(client)
        self._add_entry(client, bal["id"], "deposit", 1000.0, "2024-01-01")
        self._add_entry(client, bal["id"], "deposit", 2000.0, "2025-01-01")  # after date_to
        self._add_entry(client, bal["id"], "snapshot", 1100.0, "2024-06-01")

        rows = client.get("/api/portfolio/holdings?date_to=2024-06-30").json()
        bal_row = next((r for r in rows if r["ticker"] == "BFIXTEST"), None)
        assert bal_row is not None
        # Only first deposit <= 2024-06-30 should count
        assert bal_row["balance_contributions_eur"] == pytest.approx(1000.0, abs=1.0)


class TestBalanceInicio:
    """balance_inicio_eur should use first snapshot >= date_from, fallback last <= date_from."""

    def _create_balance_asset(self, client, ticker="BINICIO"):
        r = client.post("/api/assets", json={
            "name": "Balance Inicio Test", "ticker": ticker,
            "type": "balance", "currency": "EUR", "manual_price": True,
        })
        assert r.status_code == 201, r.text
        return r.json()

    def _add_entry(self, client, asset_id, entry_type, amount, date):
        r = client.post(f"/api/balance/{asset_id}", json={
            "date": date, "type": entry_type, "amount_eur": amount,
        })
        assert r.status_code == 201, r.text

    def test_inicio_uses_first_snapshot_gte_date_from(self, client):
        bal = self._create_balance_asset(client)
        self._add_entry(client, bal["id"], "snapshot", 800.0, "2025-01-05")   # first >= 2025-01-01
        self._add_entry(client, bal["id"], "snapshot", 1200.0, "2025-06-01")  # fin

        rows = client.get("/api/portfolio/holdings?date_from=2025-01-01&date_to=2025-06-01").json()
        bal_row = next((r for r in rows if r["ticker"] == "BINICIO"), None)
        assert bal_row is not None
        assert bal_row["balance_inicio_eur"] == pytest.approx(800.0, abs=1.0)

    def test_inicio_fallback_to_last_lte_date_from(self, client):
        # Different ticker to avoid collision with previous test
        r = client.post("/api/assets", json={
            "name": "Balance Fallback Test", "ticker": "BFALLBACK",
            "type": "balance", "currency": "EUR", "manual_price": True,
        })
        bal = r.json()
        self._add_entry(client, bal["id"], "snapshot", 500.0, "2024-11-01")  # only before period
        # date_to is BEFORE the snapshot at 2025-06-01 so no snapshot >= date_from up to date_to

        # We need date_to=2024-12-31 so no snapshot >= date_from=2024-12-01 within that window
        rows = client.get("/api/portfolio/holdings?date_from=2024-12-01&date_to=2024-12-31").json()
        bal_row = next((r for r in rows if r["ticker"] == "BFALLBACK"), None)
        assert bal_row is not None
        # No snapshot >= 2024-12-01, fallback to last <= 2024-12-01 = 500 (at 2024-11-01)
        assert bal_row["balance_inicio_eur"] == pytest.approx(500.0, abs=1.0)


class TestRendimientoTotal:
    """rendimiento_total_eur = total_pnl_eur + realized_pnl_all_time_eur."""

    def test_rendimiento_total_unrealized_only(self, client):
        asset = create_asset(client, ticker="REND1", currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-01-02", broker="degiro")
        seed_price(asset["id"], "2024-01-02", 150.0)

        data = client.get("/api/portfolio/summary").json()
        # No sells: rendimiento_total = pnl = 10 × (150 − 100) = 500
        assert data["rendimiento_total_eur"] == pytest.approx(500.0, abs=1.0)

    def test_rendimiento_total_includes_realized(self, client):
        asset = create_asset(client, ticker="REND2", currency="EUR")
        create_buy(client, asset["id"], shares=20, price=100.0, currency="EUR",
                   date="2024-01-02", broker="degiro")
        seed_price(asset["id"], "2024-01-02", 100.0)
        # Sell half at 150 → realized gain = 10 × 50 = 500
        client.post("/api/transactions", json={
            "asset_id": asset["id"], "type": "sell", "broker": "degiro",
            "shares": 10, "price": 150.0, "currency": "EUR",
            "commission": 0, "date": "2024-06-01",
        })
        seed_price(asset["id"], "2024-06-01", 150.0)  # unrealized = 10 × (150 − 100) = 500
        seed_price(asset["id"], "2024-12-31", 150.0)

        data = client.get("/api/portfolio/summary").json()
        # rendimiento_total = unrealized(500) + all_time_realized(500) = 1000
        assert data["rendimiento_total_eur"] == pytest.approx(1000.0, abs=5.0)


class TestRealizedSalesEndpoint:
    """GET /api/portfolio/realized-sales returns sells with AVCO P&L."""

    def test_empty_no_sells(self, client):
        asset = create_asset(client, ticker="NOSELL", currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-01-02", broker="degiro")
        r = client.get("/api/portfolio/realized-sales")
        assert r.status_code == 200
        assert r.json() == []

    def test_sell_appears_with_pnl(self, client):
        asset = create_asset(client, ticker="RSSELL", currency="EUR")
        create_buy(client, asset["id"], shares=10, price=100.0, currency="EUR",
                   date="2024-01-02", broker="degiro")
        client.post("/api/transactions", json={
            "asset_id": asset["id"], "type": "sell", "broker": "degiro",
            "shares": 10, "price": 130.0, "currency": "EUR",
            "commission": 0, "date": "2024-06-01",
        })
        r = client.get("/api/portfolio/realized-sales")
        assert r.status_code == 200
        sales = r.json()
        assert len(sales) == 1
        assert sales[0]["ticker"] == "RSSELL"
        assert sales[0]["shares"] == pytest.approx(10.0)
        assert sales[0]["cost_basis_eur"] == pytest.approx(100.0, abs=0.5)
        assert sales[0]["realized_pnl_eur"] == pytest.approx(300.0, abs=1.0)  # 10×(130−100)
        assert sales[0]["realized_pnl_pct"] == pytest.approx(30.0, abs=0.5)   # 300/1000×100

    def test_period_filter_restricts_sells(self, client):
        asset = create_asset(client, ticker="FILTRS", currency="EUR")
        create_buy(client, asset["id"], shares=20, price=100.0, currency="EUR",
                   date="2024-01-02", broker="degiro")
        # Sell 1: January 2024
        client.post("/api/transactions", json={
            "asset_id": asset["id"], "type": "sell", "broker": "degiro",
            "shares": 5, "price": 120.0, "currency": "EUR",
            "commission": 0, "date": "2024-01-15",
        })
        # Sell 2: June 2024
        client.post("/api/transactions", json={
            "asset_id": asset["id"], "type": "sell", "broker": "degiro",
            "shares": 5, "price": 140.0, "currency": "EUR",
            "commission": 0, "date": "2024-06-01",
        })
        # Only June sell in window
        r = client.get("/api/portfolio/realized-sales?date_from=2024-05-01&date_to=2024-12-31")
        sales = r.json()
        assert len(sales) == 1
        assert sales[0]["realized_pnl_eur"] == pytest.approx(200.0, abs=1.0)  # 5×(140−100)
