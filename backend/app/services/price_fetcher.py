"""
Price fetching service.

Strategy per asset type:
  - stocks / ETFs  → yfinance (batch download)
  - funds (ISIN)   → investpy (primary) → mstarpy (fallback) → manual
  - FX rates       → yfinance (EURUSD=X, EURGBP=X, ...)
"""
import logging
from datetime import date, timedelta, datetime
from typing import Optional

import duckdb
import yfinance as yf

logger = logging.getLogger(__name__)

# Refreshing flag (in-process; good enough for single-worker PoC)
_refreshing: bool = False


def is_refreshing() -> bool:
    return _refreshing


def refresh_all_prices(conn: duckdb.DuckDBPyConnection) -> int:
    """Refresh prices for all active holdings. Returns number of price rows upserted."""
    global _refreshing
    _refreshing = True
    log_id = _start_refresh_log(conn)
    updated = 0
    try:
        # Get active holdings (total_shares > 0) with their asset info
        holdings = conn.execute("""
            SELECT a.id, a.ticker, a.type, a.currency, a.manual_price
            FROM assets a
            WHERE a.id IN (
                SELECT asset_id FROM transactions
                GROUP BY asset_id
                HAVING SUM(CASE WHEN type='buy' THEN shares ELSE -shares END) > 0
            )
            AND a.manual_price = false
        """).fetchall()

        if not holdings:
            return 0

        # Separate by type
        yf_assets = [(id_, ticker, currency) for id_, ticker, type_, currency, _ in holdings if type_ != "fund"]
        fund_assets = [(id_, ticker, currency) for id_, ticker, type_, currency, _ in holdings if type_ == "fund"]

        # Refresh FX rates first (needed for price_eur calculation)
        currencies = set(currency for _, _, currency in yf_assets + fund_assets) - {"EUR"}
        if currencies:
            updated += _fetch_fx_rates(conn, list(currencies))

        # Batch-fetch stocks/ETFs
        if yf_assets:
            updated += _fetch_yfinance_prices(conn, yf_assets)

        # Fetch funds
        for asset_id, ticker, currency in fund_assets:
            count = _fetch_fund_price(conn, asset_id, ticker, currency)
            updated += count

        _finish_refresh_log(conn, log_id, updated, "ok")
    except Exception as e:
        logger.error("Price refresh failed: %s", e)
        _finish_refresh_log(conn, log_id, updated, "error")
        raise
    finally:
        _refreshing = False

    return updated


def refresh_single_asset(conn: duckdb.DuckDBPyConnection, asset_id: int) -> int:
    row = conn.execute(
        "SELECT id, ticker, type, currency, manual_price FROM assets WHERE id = ?",
        [asset_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"Asset {asset_id} not found")
    id_, ticker, type_, currency, manual_price = row
    if manual_price:
        return 0

    currencies = {currency} - {"EUR"}
    if currencies:
        _fetch_fx_rates(conn, list(currencies))

    if type_ == "fund":
        return _fetch_fund_price(conn, id_, ticker, currency)
    return _fetch_yfinance_prices(conn, [(id_, ticker, currency)])


def fetch_asset_metadata(ticker: str) -> dict:
    """Try to fetch name, currency, logo_url and market hint from yfinance."""
    try:
        info = yf.Ticker(ticker).info
        return {
            "name": info.get("longName") or info.get("shortName") or ticker,
            "currency": (info.get("currency") or "EUR").upper(),
            "image_url": info.get("logo_url"),
        }
    except Exception:
        return {"name": ticker, "currency": "EUR", "image_url": None}


def _fetch_yfinance_prices(
    conn: duckdb.DuckDBPyConnection,
    assets: list[tuple[int, str, str]],
) -> int:
    tickers = [ticker for _, ticker, _ in assets]
    ticker_to_id_ccy = {ticker: (id_, ccy) for id_, ticker, ccy in assets}

    try:
        data = yf.download(
            tickers=tickers,
            period="5d",
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
    except Exception as e:
        logger.error("yfinance batch download failed: %s", e)
        return 0

    count = 0
    today = date.today()

    for ticker in tickers:
        asset_id, currency = ticker_to_id_ccy[ticker]
        try:
            if len(tickers) == 1:
                ticker_data = data
            else:
                ticker_data = data[ticker]

            if ticker_data.empty:
                continue

            for idx_date, row in ticker_data.iterrows():
                price_date = idx_date.date() if hasattr(idx_date, "date") else idx_date
                if price_date > today:
                    continue
                close_price = float(row["Close"])
                if close_price <= 0:
                    continue
                price_eur = _price_to_eur(conn, close_price, currency, price_date)
                _upsert_price(conn, asset_id, price_date, close_price, currency, price_eur)
                count += 1
        except Exception as e:
            logger.warning("Failed to process price for %s: %s", ticker, e)

    return count


def _fetch_fund_price(
    conn: duckdb.DuckDBPyConnection,
    asset_id: int,
    ticker: str,
    currency: str,
) -> int:
    """Try investpy, then mstarpy, return number of rows upserted."""
    count = _try_investpy(conn, asset_id, ticker, currency)
    if count > 0:
        return count
    count = _try_mstarpy(conn, asset_id, ticker, currency)
    return count


def _try_investpy(conn, asset_id, ticker, currency) -> int:
    try:
        import investpy
        from_date = (date.today() - timedelta(days=10)).strftime("%d/%m/%Y")
        to_date = date.today().strftime("%d/%m/%Y")

        # Try to search fund by ISIN
        search_results = investpy.search_quotes(text=ticker, products=["funds"], n_results=1)
        if not search_results:
            return 0
        fund = search_results[0]
        hist = fund.retrieve_historical_data(from_date=from_date, to_date=to_date)
        if hist is None or hist.empty:
            return 0

        count = 0
        for idx_date, row in hist.iterrows():
            price_date = idx_date.date() if hasattr(idx_date, "date") else idx_date
            close_price = float(row["Close"])
            if close_price <= 0:
                continue
            price_eur = _price_to_eur(conn, close_price, currency, price_date)
            _upsert_price(conn, asset_id, price_date, close_price, currency, price_eur)
            count += 1
        return count
    except Exception as e:
        logger.debug("investpy failed for %s: %s", ticker, e)
        return 0


def _try_mstarpy(conn, asset_id, ticker, currency) -> int:
    try:
        import mstarpy
        fund = mstarpy.Fund(term=ticker, country="esp")
        hist = fund.nav(start_date=date.today() - timedelta(days=10), end_date=date.today())
        if not hist:
            return 0

        count = 0
        for entry in hist:
            price_date = entry.get("date")
            nav = entry.get("nav")
            if not price_date or not nav:
                continue
            if isinstance(price_date, str):
                from dateutil.parser import parse
                price_date = parse(price_date).date()
            price_eur = _price_to_eur(conn, float(nav), currency, price_date)
            _upsert_price(conn, asset_id, price_date, float(nav), currency, price_eur)
            count += 1
        return count
    except Exception as e:
        logger.debug("mstarpy failed for %s: %s", ticker, e)
        return 0


def _fetch_fx_rates(conn: duckdb.DuckDBPyConnection, currencies: list[str]) -> int:
    pairs = [f"EUR{ccy}=X" for ccy in currencies]
    try:
        data = yf.download(
            tickers=pairs,
            period="5d",
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
    except Exception as e:
        logger.error("FX rate fetch failed: %s", e)
        return 0

    count = 0
    today = date.today()

    for pair, ccy in zip(pairs, currencies):
        try:
            if len(pairs) == 1:
                pair_data = data
            else:
                pair_data = data[pair]
            if pair_data.empty:
                continue
            for idx_date, row in pair_data.iterrows():
                rate_date = idx_date.date() if hasattr(idx_date, "date") else idx_date
                if rate_date > today:
                    continue
                eur_rate = float(row["Close"])
                if eur_rate <= 0:
                    continue
                # Store both directions
                conn.execute(
                    """
                    INSERT INTO fx_rates VALUES (?, ?, ?, ?)
                    ON CONFLICT (date, from_ccy, to_ccy) DO UPDATE SET rate = excluded.rate
                    """,
                    [rate_date, "EUR", ccy, eur_rate],
                )
                conn.execute(
                    """
                    INSERT INTO fx_rates VALUES (?, ?, ?, ?)
                    ON CONFLICT (date, from_ccy, to_ccy) DO UPDATE SET rate = excluded.rate
                    """,
                    [rate_date, ccy, "EUR", 1.0 / eur_rate],
                )
                count += 1
        except Exception as e:
            logger.warning("Failed to process FX rate for %s: %s", ccy, e)

    return count


def _price_to_eur(
    conn: duckdb.DuckDBPyConnection,
    price: float,
    currency: str,
    on_date: date,
) -> float:
    if currency.upper() == "EUR":
        return price
    row = conn.execute(
        """
        SELECT rate FROM fx_rates
        WHERE from_ccy = ? AND to_ccy = 'EUR' AND date <= ?
        ORDER BY date DESC LIMIT 1
        """,
        [currency.upper(), on_date],
    ).fetchone()
    if row is None:
        return price  # best-effort fallback: treat as EUR
    return price * float(row[0])


def _upsert_price(
    conn: duckdb.DuckDBPyConnection,
    asset_id: int,
    price_date: date,
    price: float,
    currency: str,
    price_eur: float,
) -> None:
    conn.execute(
        """
        INSERT INTO prices VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (asset_id, date) DO UPDATE SET
            price = excluded.price,
            currency = excluded.currency,
            price_eur = excluded.price_eur
        """,
        [asset_id, price_date, price, currency.upper(), price_eur],
    )


def _start_refresh_log(conn: duckdb.DuckDBPyConnection) -> int:
    row = conn.execute(
        "INSERT INTO refresh_log VALUES (nextval('refresh_log_id_seq'), current_timestamp, NULL, NULL, 'running') RETURNING id"
    ).fetchone()
    return row[0]


def _finish_refresh_log(conn, log_id: int, count: int, status: str) -> None:
    conn.execute(
        "UPDATE refresh_log SET finished_at = current_timestamp, assets_updated = ?, status = ? WHERE id = ?",
        [count, status, log_id],
    )
