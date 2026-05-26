from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.config import settings
from app.database import get_db
from app.models.portfolio import PremarketQuote, PriceStatus
from app.services import price_fetcher
from app.services.price_status import compute_price_status

router = APIRouter(prefix="/api/prices", tags=["prices"])


@router.get("/status", response_model=PriceStatus)
def price_status():
    return compute_price_status(get_db())


@router.post("/refresh")
def refresh_prices(background_tasks: BackgroundTasks):
    """Trigger a full price refresh in the background. Returns immediately."""
    if price_fetcher.is_refreshing():
        return {"ok": False, "message": "Refresh already in progress"}
    # Pass the db path so the background thread opens its own connection —
    # sharing the main conn across threads is not safe.
    background_tasks.add_task(price_fetcher.refresh_all_prices_bg, settings.database_path)
    return {"ok": True, "message": "Price refresh started"}




@router.get("/premarket", response_model=list[PremarketQuote])
def premarket_prices():
    """Live premarket quotes via 1-minute yfinance data filtered to before 09:30 ET.
    Uses last stored DB price as previous-close reference. Only returns tickers
    that have at least one premarket candle today."""
    import yfinance as yf
    import pandas as pd
    import pytz
    from datetime import date as date_
    from app.services.currency import get_rate_to_eur

    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT a.id, a.ticker, a.currency,
               (SELECT price FROM prices WHERE asset_id = a.id ORDER BY date DESC LIMIT 1) AS last_price
        FROM assets a
        JOIN transactions t ON t.asset_id = a.id
        WHERE a.type != 'balance' AND a.manual_price = false
    """).fetchall()
    if not rows:
        return []

    today = date_.today()
    ticker_map: dict[str, tuple[int, str, float | None]] = {
        r[1]: (r[0], r[2], float(r[3]) if r[3] is not None else None)
        for r in rows
    }
    # Only US-listed tickers (no exchange suffix like .T, .HE, .L, .TO, .V) have
    # a meaningful 4:00–9:30 ET premarket window. Non-US regular sessions overlap
    # with the ET premarket hours and would produce misleading results.
    tickers_list = [t for t in ticker_map if "." not in t]
    if not tickers_list:
        return []

    try:
        data = yf.download(
            tickers_list, period="1d", interval="1m",
            prepost=True, auto_adjust=True, progress=False,
        )
    except Exception:
        return []

    if data.empty:
        return []

    # Filter to pre-market window: candles strictly before 09:30 ET
    et = pytz.timezone("America/New_York")
    market_open = pd.Timestamp("today", tz=et).normalize() + pd.Timedelta(hours=9, minutes=30)
    premarket_data = data[data.index < market_open]
    if premarket_data.empty:
        return []

    last_row = premarket_data.iloc[-1]

    result: list[PremarketQuote] = []
    for ticker, (asset_id, currency, db_prev_close) in ticker_map.items():
        try:
            if len(tickers_list) == 1:
                pre_price = float(last_row["Close"])
            else:
                pre_price = float(last_row[("Close", ticker)])
            if pd.isna(pre_price):
                continue
            prev_close = db_prev_close
            if prev_close is None or prev_close == 0:
                continue
            change_pct = (pre_price - prev_close) / prev_close * 100
            try:
                rate = get_rate_to_eur(conn, currency, today)
                price_eur: float | None = pre_price * rate
            except ValueError:
                price_eur = None
            result.append(PremarketQuote(
                asset_id=asset_id,
                ticker=ticker,
                currency=currency,
                premarket_price=pre_price,
                premarket_price_eur=price_eur,
                premarket_change_pct=change_pct,
                prev_close=prev_close,
            ))
        except Exception:
            continue

    return result


@router.get("/fx-rate")
def fx_rate(currency: str, date: str):
    """Return the EUR rate for a currency on a given date (for form hints).
    Falls back to fetching from yfinance when the date is not in the local cache."""
    from app.services.currency import get_rate_to_eur
    from app.services.price_fetcher import fetch_fx_rate_on_demand
    from dateutil.parser import parse as parse_date
    conn = get_db()
    if currency.upper() == "EUR":
        return {"rate": 1.0, "found": True}
    target_date = parse_date(date).date()
    try:
        rate = get_rate_to_eur(conn, currency.upper(), target_date)
        return {"rate": rate, "found": True}
    except ValueError:
        rate = fetch_fx_rate_on_demand(conn, currency.upper(), target_date)
        if rate is not None:
            return {"rate": rate, "found": True}
        return {"rate": None, "found": False}


@router.post("/refresh/{asset_id}/sync")
def refresh_single_sync(asset_id: int):
    """Synchronous debug refresh — raw mstarpy call to expose any errors."""
    import traceback
    import mstarpy
    from app.services.price_fetcher import _get_fetch_range, _try_investpy, _get_mstar_session
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, ticker, type, currency, manual_price, isin FROM assets WHERE id = ?", [asset_id]
        ).fetchone()
        if not row:
            return {"error": "asset not found"}
        id_, ticker, type_, currency, manual_price, isin = row
        start, end = _get_fetch_range(conn, id_)

        investpy_n = _try_investpy(conn, id_, ticker, isin, currency, start, end)

        search_term = isin or ticker
        session = _get_mstar_session()
        fund = mstarpy.Funds(term=search_term, pageSize=1, session=session)
        hist = fund.nav(start_date=start, end_date=end)
        nav_count = len(hist) if hist else 0

        prices_now = conn.execute("SELECT COUNT(*) FROM prices WHERE asset_id=?", [id_]).fetchone()[0]
        return {
            "ticker": ticker, "isin": isin, "start": str(start), "end": str(end),
            "investpy_n": investpy_n,
            "fund_name": getattr(fund, "name", None),
            "fund_isin": getattr(fund, "isin", None),
            "nav_count": nav_count,
            "prices_in_db": prices_now,
        }
    except Exception as e:
        return {"error": str(e), "trace": traceback.format_exc()}


@router.post("/refresh/{asset_id}")
def refresh_single(asset_id: int, background_tasks: BackgroundTasks):
    conn = get_db()
    if not conn.execute("SELECT id FROM assets WHERE id = ?", [asset_id]).fetchone():
        raise HTTPException(status_code=404, detail="Asset not found")
    background_tasks.add_task(price_fetcher.refresh_single_asset_bg, settings.database_path, asset_id)
    return {"ok": True, "message": f"Price refresh started for asset {asset_id}"}
