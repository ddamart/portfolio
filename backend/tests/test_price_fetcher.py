"""
Tests for price_fetcher helpers.

The mstarpy tests mock the HTTP layer so they run offline and stay stable,
but exercise the full code path inside _try_mstarpy and _fund_name_from_mstar.
"""
import pytest
import pandas as pd
from datetime import date
from unittest.mock import patch, MagicMock, ANY
import app.database as db_module
from app.services.price_fetcher import _try_mstarpy, _fund_name_from_mstar, _try_yahoo_fund, _try_onvista_fund


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


def _mock_search_response(quotes: list):
    resp = MagicMock()
    resp.ok = True
    resp.json.return_value = {"quotes": quotes}
    return resp


def _fake_yf_frame(dates: list, closes: list):
    return pd.DataFrame({"Close": closes}, index=pd.to_datetime(dates))


class TestTryYahooFund:
    def test_returns_zero_without_isin(self, client):
        conn = db_module.get_db()
        assert _try_yahoo_fund(
            conn, asset_id=1, ticker="NOISIN", isin=None, currency="EUR",
            start=date(2025, 1, 1), end=date(2025, 1, 31),
        ) == 0

    def test_uses_mutualfund_candidate(self, client):
        """Prefers a MUTUALFUND-typed match and stores its prices."""
        conn = db_module.get_db()
        conn.execute(
            "INSERT INTO assets(id,name,ticker,type,currency,manual_price) VALUES (995,'Avantage','ES0112231016','fund','EUR',false)"
        )
        quotes = [
            {"symbol": "0P0001MYMU.F", "quoteType": "MUTUALFUND"},
            {"symbol": "SOMEOTHER.F", "quoteType": "ETF"},
        ]
        frame = _fake_yf_frame(["2025-01-02", "2025-01-03"], [29.86, 30.10])

        with patch("app.services.price_fetcher._requests.get", return_value=_mock_search_response(quotes)), \
             patch("app.services.price_fetcher.yf.download", return_value=frame) as mock_dl:
            count = _try_yahoo_fund(
                conn, asset_id=995, ticker="ES0112231016", isin="ES0112231016",
                currency="EUR", start=date(2025, 1, 1), end=date(2025, 1, 31),
            )

        assert count == 2
        mock_dl.assert_called_once_with(
            tickers=["0P0001MYMU.F"], start=ANY, end=ANY,
            auto_adjust=True, progress=False, group_by="ticker",
        )
        rows = conn.execute(
            "SELECT date, price FROM prices WHERE asset_id = 995 ORDER BY date"
        ).fetchall()
        assert len(rows) == 2

    def test_falls_back_to_frankfurt_etf_listing(self, client):
        """When no MUTUALFUND match exists, tries a Frankfurt '.F' ETF-type listing."""
        conn = db_module.get_db()
        conn.execute(
            "INSERT INTO assets(id,name,ticker,type,currency,manual_price) VALUES (994,'THOORAT','LU0348784041','fund','EUR',false)"
        )
        quotes = [{"symbol": "DJER.F", "quoteType": "ETF"}]
        frame = _fake_yf_frame(["2025-01-02"], [565.15])

        with patch("app.services.price_fetcher._requests.get", return_value=_mock_search_response(quotes)), \
             patch("app.services.price_fetcher.yf.download", return_value=frame):
            count = _try_yahoo_fund(
                conn, asset_id=994, ticker="THOORAT", isin="LU0348784041",
                currency="EUR", start=date(2025, 1, 1), end=date(2025, 1, 31),
            )

        assert count == 1

    def test_returns_zero_when_no_candidate_has_data(self, client):
        conn = db_module.get_db()
        conn.execute(
            "INSERT INTO assets(id,name,ticker,type,currency,manual_price) VALUES (993,'MWOTEEA','LU0171310443','fund','EUR',false)"
        )
        quotes = [{"symbol": "DEAD.SG", "quoteType": "MUTUALFUND"}]
        empty = pd.DataFrame()

        with patch("app.services.price_fetcher._requests.get", return_value=_mock_search_response(quotes)), \
             patch("app.services.price_fetcher.yf.download", return_value=empty):
            count = _try_yahoo_fund(
                conn, asset_id=993, ticker="MWOTEEA", isin="LU0171310443",
                currency="EUR", start=date(2025, 1, 1), end=date(2025, 1, 31),
            )

        assert count == 0

    def test_returns_zero_on_search_failure(self, client):
        conn = db_module.get_db()
        with patch("app.services.price_fetcher._requests.get", side_effect=RuntimeError("network error")):
            count = _try_yahoo_fund(
                conn, asset_id=1, ticker="X", isin="LU0000000000", currency="EUR",
                start=date(2025, 1, 1), end=date(2025, 1, 31),
            )
        assert count == 0


def _mock_json_response(payload: dict, ok: bool = True):
    resp = MagicMock()
    resp.ok = ok
    resp.json.return_value = payload
    return resp


class TestTryOnvistaFund:
    def test_returns_zero_without_isin(self, client):
        conn = db_module.get_db()
        assert _try_onvista_fund(
            conn, asset_id=1, ticker="X", isin=None, currency="EUR",
            start=date(2025, 1, 1), end=date(2025, 1, 31),
        ) == 0

    def test_stores_prices_when_currency_matches(self, client):
        conn = db_module.get_db()
        conn.execute(
            "INSERT INTO assets(id,name,ticker,type,currency,manual_price) VALUES (992,'MWOTEEA','LU0171310443','fund','EUR',false)"
        )
        search_payload = {"list": [{
            "entityType": "FUND", "isin": "LU0171310443",
            "entityValue": "9374993", "symbol": "MI9E",
        }]}
        import calendar
        ts1 = calendar.timegm(date(2025, 1, 2).timetuple())
        ts2 = calendar.timegm(date(2025, 1, 3).timetuple())
        history_payload = {
            "isoCurrency": "EUR",
            "datetimeLast": [ts1, ts2],
            "last": [126.64, 128.10],
        }
        with patch(
            "app.services.price_fetcher._requests.get",
            side_effect=[_mock_json_response(search_payload), _mock_json_response(history_payload)],
        ):
            count = _try_onvista_fund(
                conn, asset_id=992, ticker="MWOTEEA", isin="LU0171310443",
                currency="EUR", start=date(2025, 1, 1), end=date(2025, 1, 31),
            )

        assert count == 2
        rows = conn.execute(
            "SELECT date, price FROM prices WHERE asset_id = 992 ORDER BY date"
        ).fetchall()
        assert len(rows) == 2

    def test_skips_on_currency_mismatch(self, client):
        """A EUR-quoted cross-listing must not be stored for a USD-denominated asset."""
        conn = db_module.get_db()
        conn.execute(
            "INSERT INTO assets(id,name,ticker,type,currency,manual_price) VALUES (991,'BGFNGA2','LU1861215975','fund','USD',false)"
        )
        search_payload = {"list": [{
            "entityType": "FUND", "isin": "LU1861215975",
            "entityValue": "142640198", "symbol": "B3FM",
        }]}
        history_payload = {"isoCurrency": "EUR", "datetimeLast": [], "last": []}
        with patch(
            "app.services.price_fetcher._requests.get",
            side_effect=[_mock_json_response(search_payload), _mock_json_response(history_payload)],
        ):
            count = _try_onvista_fund(
                conn, asset_id=991, ticker="BGFNGA2", isin="LU1861215975",
                currency="USD", start=date(2025, 1, 1), end=date(2025, 1, 31),
            )

        assert count == 0

    def test_returns_zero_when_no_fund_match(self, client):
        conn = db_module.get_db()
        with patch(
            "app.services.price_fetcher._requests.get",
            return_value=_mock_json_response({"list": []}),
        ):
            count = _try_onvista_fund(
                conn, asset_id=1, ticker="X", isin="LU0000000000", currency="EUR",
                start=date(2025, 1, 1), end=date(2025, 1, 31),
            )
        assert count == 0

    def test_returns_zero_on_search_failure(self, client):
        conn = db_module.get_db()
        with patch("app.services.price_fetcher._requests.get", side_effect=RuntimeError("network error")):
            count = _try_onvista_fund(
                conn, asset_id=1, ticker="X", isin="LU0000000000", currency="EUR",
                start=date(2025, 1, 1), end=date(2025, 1, 31),
            )
        assert count == 0


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


class TestSplitRebuild:
    def test_split_rebuilds_history(self, client):
        """Stored pre-split prices are replaced when Yahoo's adjusted close differs wildly."""
        from app.services.price_fetcher import _fetch_yfinance_batch
        conn = db_module.get_db()
        conn.execute(
            "INSERT INTO assets(id,name,ticker,type,currency,manual_price) VALUES (990,'Split Co','SPL','stock','EUR',false)"
        )
        conn.execute(
            "INSERT INTO prices VALUES (990,'2026-09-16',50.0,'EUR',50.0),(990,'2026-09-17',51.0,'EUR',51.0)"
        )
        frame = _fake_yf_frame(["2026-09-16", "2026-09-17", "2026-09-18"], [16.67, 17.0, 18.0])

        with patch("app.services.price_fetcher.yf.download", return_value=frame):
            _fetch_yfinance_batch(conn, [(990, "SPL", "EUR")], date(2026, 9, 17), date(2026, 9, 18))

        rows = conn.execute("SELECT price FROM prices WHERE asset_id = 990 ORDER BY date").fetchall()
        assert [float(r[0]) for r in rows] == [16.67, 17.0, 18.0]

    def test_no_rebuild_without_split(self, client):
        from app.services.price_fetcher import _has_split_mismatch
        conn = db_module.get_db()
        conn.execute(
            "INSERT INTO assets(id,name,ticker,type,currency,manual_price) VALUES (989,'Plain','PLN','stock','EUR',false)"
        )
        conn.execute("INSERT INTO prices VALUES (989,'2026-09-17',100.0,'EUR',100.0)")
        assert not _has_split_mismatch(conn, 989, _fake_yf_frame(["2026-09-17"], [103.0]))
