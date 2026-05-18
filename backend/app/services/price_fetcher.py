"""
Price fetching service.

Strategy per asset type:
  - stocks / ETFs  → yfinance (batch download)
  - funds (ISIN)   → investpy (primary) → mstarpy (fallback) → manual
  - FX rates       → yfinance (EURUSD=X, EURGBP=X, ...)

Fetch range logic:
  - Asset with no prices in DB → backfill from oldest transaction date (or 2y ago)
  - Asset with existing prices → last 5 trading days only
"""
import logging
from datetime import date, timedelta
from typing import Optional

import duckdb
import yfinance as yf

logger = logging.getLogger(__name__)

_refreshing: bool = False
_REFRESH_DAYS = 5          # days to fetch on a normal (non-backfill) refresh
_BACKFILL_FALLBACK_DAYS = 365 * 2  # used when no transactions exist yet


def is_refreshing() -> bool:
    return _refreshing


# ---------------------------------------------------------------------------
# Background-safe entry points (open their own connection)
# ---------------------------------------------------------------------------

def refresh_all_prices_bg(db_path: str) -> int:
    """Open a dedicated connection for the refresh so it never shares the
    request-handler connection across threads."""
    conn = duckdb.connect(db_path)
    try:
        return refresh_all_prices(conn)
    finally:
        conn.close()


def refresh_single_asset_bg(db_path: str, asset_id: int) -> int:
    conn = duckdb.connect(db_path)
    try:
        return refresh_single_asset(conn, asset_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Core refresh logic (takes an explicit connection)
# ---------------------------------------------------------------------------

def refresh_all_prices(conn: duckdb.DuckDBPyConnection) -> int:
    """Refresh prices for all active holdings. Returns number of price rows upserted."""
    global _refreshing
    _refreshing = True
    log_id = _start_refresh_log(conn)
    updated = 0
    try:
        holdings = conn.execute("""
            SELECT a.id, a.ticker, a.type, a.currency, a.manual_price, a.isin
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

        yf_assets   = [(id_, t, c) for id_, t, tp, c, _, _i in holdings if tp != "fund"]
        fund_assets = [(id_, t, c, isin) for id_, t, tp, c, _, isin in holdings if tp == "fund"]

        # Determine fetch ranges per asset
        yf_ranges   = {id_: _get_fetch_range(conn, id_) for id_, _, _ in yf_assets}
        fund_ranges = {id_: _get_fetch_range(conn, id_) for id_, _, _, _ in fund_assets}

        # Fetch FX rates covering the full backfill window first
        currencies = (set(c for _, _, c in yf_assets) | set(c for _, _, c, _ in fund_assets)) - {"EUR"}
        if currencies:
            all_starts = [s for s, _ in list(yf_ranges.values()) + list(fund_ranges.values())]
            fx_start = min(all_starts) if all_starts else date.today() - timedelta(days=_REFRESH_DAYS)
            updated += _fetch_fx_rates(conn, list(currencies), fx_start)

        if yf_assets:
            updated += _fetch_yfinance_prices_ranged(conn, yf_assets, yf_ranges)

        for asset_id, ticker, currency, isin in fund_assets:
            start, end = fund_ranges[asset_id]
            updated += _fetch_fund_price(conn, asset_id, ticker, isin, currency, start, end)

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
        "SELECT id, ticker, type, currency, manual_price, isin FROM assets WHERE id = ?",
        [asset_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"Asset {asset_id} not found")
    id_, ticker, type_, currency, manual_price, isin = row
    if manual_price:
        return 0

    start, end = _get_fetch_range(conn, id_)

    currencies = {currency} - {"EUR"}
    if currencies:
        _fetch_fx_rates(conn, list(currencies), start)

    if type_ == "fund":
        return _fetch_fund_price(conn, id_, ticker, isin, currency, start, end)

    return _fetch_yfinance_prices_ranged(
        conn,
        [(id_, ticker, currency)],
        {id_: (start, end)},
    )


def fetch_asset_metadata(ticker: str) -> dict:
    """Try to fetch name, currency, and logo_url from yfinance."""
    try:
        info = yf.Ticker(ticker).info
        return {
            "name": info.get("longName") or info.get("shortName") or ticker,
            "currency": (info.get("currency") or "EUR").upper(),
            "image_url": _resolve_logo(info),
        }
    except Exception:
        return {"name": ticker, "currency": "EUR", "image_url": None}


def _resolve_logo(info: dict) -> Optional[str]:
    """
    Try multiple sources for a company logo URL.
    Priority: yfinance logo_url → Clearbit (from website domain).
    The frontend's onError handler falls back to initials if the URL returns 404.
    """
    # 1. yfinance provides logo_url directly for some tickers
    logo = info.get("logo_url")
    if logo:
        return logo

    # 2. Clearbit Logo API — free, no key required, 404 for unknown companies
    website = info.get("website") or ""
    if website:
        try:
            from urllib.parse import urlparse
            netloc = urlparse(website).netloc
            # strip leading www. safely (lstrip chars, not prefix)
            domain = netloc[4:] if netloc.startswith("www.") else netloc
            if domain:
                return f"https://logo.clearbit.com/{domain}"
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# Fetch-range helpers
# ---------------------------------------------------------------------------

def _get_fetch_range(conn: duckdb.DuckDBPyConnection, asset_id: int) -> tuple[date, date]:
    """
    Return (start, end) for a price fetch.
    - No existing prices → start from oldest transaction date (backfill).
    - Prices exist       → last N trading days only.
    """
    today = date.today()
    has_prices = conn.execute(
        "SELECT COUNT(*) FROM prices WHERE asset_id = ?", [asset_id]
    ).fetchone()[0]

    if has_prices > 0:
        return today - timedelta(days=_REFRESH_DAYS), today

    # Backfill: go back to the oldest transaction for this asset
    row = conn.execute(
        "SELECT MIN(date) FROM transactions WHERE asset_id = ?", [asset_id]
    ).fetchone()
    if row and row[0]:
        oldest = row[0] if isinstance(row[0], date) else row[0].date()
        # Give a small buffer before the first transaction
        return oldest - timedelta(days=5), today

    # Asset exists but no transactions yet — fetch 2 years as a sensible default
    return today - timedelta(days=_BACKFILL_FALLBACK_DAYS), today


# ---------------------------------------------------------------------------
# yfinance (stocks / ETFs)
# ---------------------------------------------------------------------------

def _fetch_yfinance_prices_ranged(
    conn: duckdb.DuckDBPyConnection,
    assets: list[tuple[int, str, str]],   # (asset_id, ticker, currency)
    ranges: dict[int, tuple[date, date]], # asset_id → (start, end)
) -> int:
    """
    Batch assets that share the same date range; fetch each batch together.
    Backfill assets (typically one at a time) are fetched individually.
    """
    # Group by (start, end)
    from collections import defaultdict
    groups: dict[tuple[date, date], list[tuple[int, str, str]]] = defaultdict(list)
    for asset_id, ticker, currency in assets:
        groups[ranges[asset_id]].append((asset_id, ticker, currency))

    total = 0
    for (start, end), group in groups.items():
        total += _fetch_yfinance_batch(conn, group, start, end)
    return total


def _fetch_yfinance_batch(
    conn: duckdb.DuckDBPyConnection,
    assets: list[tuple[int, str, str]],
    start: date,
    end: date,
) -> int:
    tickers = [ticker for _, ticker, _ in assets]
    ticker_to_id_ccy = {ticker: (id_, ccy) for id_, ticker, ccy in assets}

    try:
        data = yf.download(
            tickers=tickers,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),  # yfinance end is exclusive
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
    except Exception as e:
        logger.error("yfinance batch download failed (%s → %s): %s", start, end, e)
        return 0

    count = 0
    today = date.today()

    for ticker in tickers:
        asset_id, currency = ticker_to_id_ccy[ticker]
        try:
            # Newer yfinance returns MultiIndex columns even for single tickers;
            # data[ticker] always gives a flat-column DataFrame regardless.
            try:
                ticker_data = data[ticker]
            except KeyError:
                ticker_data = data  # older yfinance single-ticker fallback
            # Flatten any remaining MultiIndex (e.g. ('Close', '') artifacts)
            if hasattr(ticker_data.columns, "levels"):
                ticker_data = ticker_data.droplevel(1, axis=1)
            if ticker_data.empty:
                continue
            for idx_date, row in ticker_data.iterrows():
                price_date = idx_date.date() if hasattr(idx_date, "date") else idx_date
                if price_date > today:
                    continue
                close_price = row.get("Close")
                if close_price is None or close_price != close_price:  # None or NaN
                    continue
                close_price = float(close_price)
                if close_price <= 0:
                    continue
                price_eur = _price_to_eur(conn, close_price, currency, price_date)
                _upsert_price(conn, asset_id, price_date, close_price, currency, price_eur)
                count += 1
        except Exception as e:
            logger.warning("Failed to process price for %s: %s", ticker, e)

    return count


# ---------------------------------------------------------------------------
# Funds (investpy → mstarpy → give up)
# ---------------------------------------------------------------------------

def _fetch_fund_price(
    conn: duckdb.DuckDBPyConnection,
    asset_id: int,
    ticker: str,
    isin: Optional[str],
    currency: str,
    start: date,
    end: date,
) -> int:
    count = _try_investpy(conn, asset_id, ticker, isin, currency, start, end)
    if count > 0:
        return count
    return _try_mstarpy(conn, asset_id, ticker, isin, currency, start, end)


def _try_investpy(
    conn, asset_id, ticker, isin: Optional[str], currency, start: date, end: date
) -> int:
    try:
        import investpy
        from_str = start.strftime("%d/%m/%Y")
        to_str   = end.strftime("%d/%m/%Y")

        # ISIN is more reliable than ticker/name for investpy fund search
        search_term = isin or ticker
        search_results = investpy.search_quotes(text=search_term, products=["funds"], n_results=1)
        if not search_results:
            return 0
        fund = search_results[0]
        hist = fund.retrieve_historical_data(from_date=from_str, to_date=to_str)
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
        logger.debug("investpy failed for %s (isin=%s): %s", ticker, isin, e)
        return 0


def _try_mstarpy(
    conn, asset_id, ticker, isin: Optional[str], currency, start: date, end: date
) -> int:
    try:
        import mstarpy
        # Prefer ISIN for Morningstar lookup — avoids ambiguity on name matches
        search_term = isin or ticker
        fund = mstarpy.Fund(term=search_term, country="esp")
        hist = fund.nav(start_date=start, end_date=end)
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
        logger.debug("mstarpy failed for %s (isin=%s): %s", ticker, isin, e)
        return 0


# ---------------------------------------------------------------------------
# FX rates
# ---------------------------------------------------------------------------

def _fetch_fx_rates(
    conn: duckdb.DuckDBPyConnection,
    currencies: list[str],
    start: date,
) -> int:
    pairs = [f"EUR{ccy}=X" for ccy in currencies]
    today = date.today()

    try:
        data = yf.download(
            tickers=pairs,
            start=start.isoformat(),
            end=(today + timedelta(days=1)).isoformat(),
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
    except Exception as e:
        logger.error("FX rate fetch failed: %s", e)
        return 0

    count = 0
    for pair, ccy in zip(pairs, currencies):
        try:
            try:
                pair_data = data[pair]
            except KeyError:
                pair_data = data
            if hasattr(pair_data.columns, "levels"):
                pair_data = pair_data.droplevel(1, axis=1)
            if pair_data.empty:
                continue
            for idx_date, row in pair_data.iterrows():
                rate_date = idx_date.date() if hasattr(idx_date, "date") else idx_date
                if rate_date > today:
                    continue
                eur_rate = row.get("Close")
                if eur_rate is None or eur_rate != eur_rate:
                    continue
                eur_rate = float(eur_rate)
                if eur_rate <= 0:
                    continue
                conn.execute(
                    "INSERT INTO fx_rates VALUES (?, ?, ?, ?) ON CONFLICT (date, from_ccy, to_ccy) DO UPDATE SET rate = excluded.rate",
                    [rate_date, "EUR", ccy, eur_rate],
                )
                conn.execute(
                    "INSERT INTO fx_rates VALUES (?, ?, ?, ?) ON CONFLICT (date, from_ccy, to_ccy) DO UPDATE SET rate = excluded.rate",
                    [rate_date, ccy, "EUR", 1.0 / eur_rate],
                )
                count += 1
        except Exception as e:
            logger.warning("Failed to process FX rate for %s: %s", ccy, e)

    return count


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _price_to_eur(conn, price: float, currency: str, on_date: date) -> float:
    if currency.upper() == "EUR":
        return price
    row = conn.execute(
        "SELECT rate FROM fx_rates WHERE from_ccy = ? AND to_ccy = 'EUR' AND date <= ? ORDER BY date DESC LIMIT 1",
        [currency.upper(), on_date],
    ).fetchone()
    return price * float(row[0]) if row else price


def _upsert_price(conn, asset_id: int, price_date: date, price: float, currency: str, price_eur: float) -> None:
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


def _start_refresh_log(conn) -> int:
    row = conn.execute(
        "INSERT INTO refresh_log VALUES (nextval('refresh_log_id_seq'), current_timestamp, NULL, NULL, 'running') RETURNING id"
    ).fetchone()
    return row[0]


def _finish_refresh_log(conn, log_id: int, count: int, status: str) -> None:
    conn.execute(
        "UPDATE refresh_log SET finished_at = current_timestamp, assets_updated = ?, status = ? WHERE id = ?",
        [count, status, log_id],
    )
