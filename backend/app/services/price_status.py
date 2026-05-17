"""
Determines whether prices are stale for each active holding,
using market timezone and trading hours from the markets table.
"""
from datetime import datetime, date, time
from typing import Optional
import pytz
import duckdb

from app.models.portfolio import PriceStatus, PriceStatusAsset
from app.services.price_fetcher import is_refreshing


def compute_price_status(conn: duckdb.DuckDBPyConnection) -> PriceStatus:
    # Get all active holdings with market info
    rows = conn.execute("""
        SELECT
            a.id, a.ticker, a.manual_price,
            m.timezone, m.close_time,
            (SELECT MAX(p.date) FROM prices p WHERE p.asset_id = a.id) AS last_price_date
        FROM assets a
        LEFT JOIN markets m ON m.id = a.market_id
        WHERE a.id IN (
            SELECT asset_id FROM transactions
            GROUP BY asset_id
            HAVING SUM(CASE WHEN type='buy' THEN shares ELSE -shares END) > 0.000001
        )
    """).fetchall()

    asset_statuses = []
    any_stale = False

    for asset_id, ticker, manual_price, timezone_str, close_time, last_price_date in rows:
        if manual_price:
            stale = False
        else:
            stale = _is_stale(timezone_str, close_time, last_price_date)
        if stale:
            any_stale = True
        asset_statuses.append(
            PriceStatusAsset(
                asset_id=asset_id,
                ticker=ticker,
                last_price_date=last_price_date,
                stale=stale,
            )
        )

    # Get last successful refresh time
    row = conn.execute(
        "SELECT finished_at FROM refresh_log WHERE status = 'ok' ORDER BY finished_at DESC LIMIT 1"
    ).fetchone()
    last_refresh_str: Optional[str] = None
    if row and row[0]:
        last_refresh_str = _humanize(row[0])

    return PriceStatus(
        last_refresh=last_refresh_str,
        stale=any_stale,
        refreshing=is_refreshing(),
        assets=asset_statuses,
    )


def _is_stale(timezone_str: Optional[str], close_time, last_price_date: Optional[date]) -> bool:
    today = date.today()

    if last_price_date is None:
        return True

    # If we have today's price, not stale
    if last_price_date >= today:
        return False

    # Check if market has closed today (so we'd expect a new price)
    if timezone_str and close_time:
        try:
            tz = pytz.timezone(timezone_str)
            now_local = datetime.now(tz)
            # Parse close_time (stored as time or string "HH:MM")
            if isinstance(close_time, str):
                h, m = map(int, close_time.split(":"))
                ct = time(h, m)
            else:
                ct = close_time

            market_closed_today = now_local.time() > ct and now_local.date() == today

            if market_closed_today:
                # Market closed today, we should have today's price
                return last_price_date < today
            else:
                # Market not yet closed today; yesterday's price is fine
                from datetime import timedelta
                yesterday = today - timedelta(days=1)
                return last_price_date < yesterday
        except Exception:
            pass

    # Fallback: stale if last price is older than 2 days
    from datetime import timedelta
    return (today - last_price_date).days > 2


def _humanize(dt) -> str:
    """Return a human-readable 'X minutes ago' string."""
    from datetime import timezone as tz_mod
    now = datetime.now()
    if hasattr(dt, "tzinfo") and dt.tzinfo:
        now = datetime.now(tz_mod.utc)
    delta = now - dt
    minutes = int(delta.total_seconds() / 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return dt.strftime("%Y-%m-%d %H:%M")
