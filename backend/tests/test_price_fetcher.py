"""
Tests for price_fetcher helpers.

The mstarpy tests mock the HTTP layer so they run offline and stay stable,
but exercise the full code path inside _try_mstarpy and _fund_name_from_mstar.
"""
import pytest
from datetime import date
from unittest.mock import patch, MagicMock, ANY
import app.database as db_module
from app.services.price_fetcher import _try_mstarpy, _fund_name_from_mstar


def _mock_funds_class(name: str, isin: str, nav_data: list):
    """Return a MagicMock that behaves like mstarpy.Funds."""
    instance = MagicMock()
    instance.name = name
    instance.isin = isin
    instance.nav.return_value = nav_data
    instance.metaData.return_value = {"isin": isin}
    klass = MagicMock(return_value=instance)
    return klass


class TestTryMstarpy:
    def test_returns_count_on_success(self, client):
        """_try_mstarpy inserts price rows and returns the count."""
        conn = db_module.get_db()
        # Seed a EUR asset
        conn.execute(
            "INSERT INTO assets(id,name,ticker,type,currency,manual_price) VALUES (999,'Test Fund','LU0996179007','fund','EUR',false)"
        )

        nav_payload = [
            {"date": "2025-01-02", "nav": 483.64},
            {"date": "2025-01-03", "nav": 491.35},
            {"date": "2025-01-06", "nav": 488.10},
        ]
        mock_cls = _mock_funds_class("Amundi S&P 500 Screened INDEX AE Acc", "LU0996179007", nav_payload)

        _no_secid = "app.services.price_fetcher._mstar_resolve_secid"
        _no_direct = "app.services.price_fetcher._try_mstar_direct"
        with patch.dict("sys.modules", {"mstarpy": MagicMock(Funds=mock_cls)}), \
             patch(_no_secid, return_value=None), \
             patch(_no_direct, return_value=0):
            count = _try_mstarpy(
                conn, asset_id=999, ticker="LU0996179007",
                isin="LU0996179007", currency="EUR",
                start=date(2025, 1, 1), end=date(2025, 1, 31),
            )

        assert count == 3
        rows = conn.execute(
            "SELECT date, price FROM prices WHERE asset_id = 999 ORDER BY date"
        ).fetchall()
        assert len(rows) == 3
        assert abs(float(rows[0][1]) - 483.64) < 0.01
        assert abs(float(rows[2][1]) - 488.10) < 0.01

    def test_returns_zero_on_empty_nav(self, client):
        """Returns 0 when mstarpy returns an empty list."""
        conn = db_module.get_db()
        conn.execute(
            "INSERT INTO assets(id,name,ticker,type,currency,manual_price) VALUES (998,'Empty Fund','LU0000000000','fund','EUR',false)"
        )
        mock_cls = _mock_funds_class("Empty Fund", "LU0000000000", [])

        with patch.dict("sys.modules", {"mstarpy": MagicMock(Funds=mock_cls)}):
            count = _try_mstarpy(
                conn, asset_id=998, ticker="LU0000000000",
                isin="LU0000000000", currency="EUR",
                start=date(2025, 1, 1), end=date(2025, 1, 31),
            )

        assert count == 0

    def test_uses_isin_as_search_term(self, client):
        """mstarpy.Funds is called with the ISIN, not the ticker alias."""
        conn = db_module.get_db()
        conn.execute(
            "INSERT INTO assets(id,name,ticker,type,currency,manual_price) VALUES (997,'AMIEAEC','AMIEAEC','fund','EUR',false)"
        )
        mock_cls = _mock_funds_class("Amundi IS MSCI World AE-C", "LU0996182563", [])

        _no_secid = "app.services.price_fetcher._mstar_resolve_secid"
        _no_direct = "app.services.price_fetcher._try_mstar_direct"
        with patch.dict("sys.modules", {"mstarpy": MagicMock(Funds=mock_cls)}), \
             patch(_no_secid, return_value=None), \
             patch(_no_direct, return_value=0):
            _try_mstarpy(
                conn, asset_id=997, ticker="AMIEAEC",
                isin="LU0996182563", currency="EUR",
                start=date(2025, 1, 1), end=date(2025, 1, 31),
            )

        mock_cls.assert_called_once_with(term="LU0996182563", pageSize=1, session=ANY)

    def test_falls_back_to_ticker_when_no_isin(self, client):
        """When ISIN is None, search term falls back to ticker."""
        conn = db_module.get_db()
        conn.execute(
            "INSERT INTO assets(id,name,ticker,type,currency,manual_price) VALUES (996,'No ISIN Fund','NOISINFUND','fund','EUR',false)"
        )
        mock_cls = _mock_funds_class("No ISIN Fund", "", [])

        with patch.dict("sys.modules", {"mstarpy": MagicMock(Funds=mock_cls)}):
            _try_mstarpy(
                conn, asset_id=996, ticker="NOISINFUND",
                isin=None, currency="EUR",
                start=date(2025, 1, 1), end=date(2025, 1, 31),
            )

        mock_cls.assert_called_once_with(term="NOISINFUND", pageSize=1, session=ANY)


class TestFundNameFromMstar:
    def test_returns_name_on_success(self):
        mock_cls = _mock_funds_class("Amundi S&P 500 Screened INDEX AE Acc", "LU0996179007", [])

        with patch.dict("sys.modules", {"mstarpy": MagicMock(Funds=mock_cls)}):
            name = _fund_name_from_mstar("LU0996179007")

        assert name == "Amundi S&P 500 Screened INDEX AE Acc"

    def test_returns_none_when_name_equals_isin(self):
        mock_cls = _mock_funds_class("LU0000000000", "LU0000000000", [])

        with patch.dict("sys.modules", {"mstarpy": MagicMock(Funds=mock_cls)}):
            name = _fund_name_from_mstar("LU0000000000")

        assert name is None

    def test_returns_none_on_exception(self):
        bad_cls = MagicMock(side_effect=RuntimeError("network error"))

        with patch.dict("sys.modules", {"mstarpy": MagicMock(Funds=bad_cls)}):
            name = _fund_name_from_mstar("LU0996179007")

        assert name is None
