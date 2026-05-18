"""
Core DuckDB analytical queries for portfolio metrics.
All calculations are dynamic — no stored snapshots.
"""
from datetime import date, timedelta
from typing import Optional

import duckdb

from app.models.portfolio import ChartPoint, HoldingRow, PortfolioSummary


def _period_to_date_range(period: str) -> tuple[Optional[date], Optional[date]]:
    today = date.today()
    mapping = {
        "1d": today - timedelta(days=1),
        "1w": today - timedelta(weeks=1),
        "1m": today - timedelta(days=30),
        "6m": today - timedelta(days=182),
        "ytd": date(today.year, 1, 1),
        "1y": today - timedelta(days=365),
        "5y": today - timedelta(days=365 * 5),
        "all": None,
    }
    from_date = mapping.get(period)
    return from_date, today


def get_holdings(
    conn: duckdb.DuckDBPyConnection,
    period: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    broker: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> list[HoldingRow]:
    if period and not date_from:
        date_from, date_to = _period_to_date_range(period)

    # Build transaction filter for date range (affects what's considered "bought by then")
    tx_date_filter = ""
    params: list = []
    if date_to:
        tx_date_filter = "AND t.date <= ?"
        params.append(date_to)

    broker_filter = ""
    if broker:
        broker_filter = "AND t.broker = ?"
        params.append(broker)

    type_filter = ""
    if asset_type:
        type_filter = "AND a.type = ?"
        params.append(asset_type)

    query = f"""
    WITH holdings AS (
        SELECT
            t.asset_id,
            SUM(CASE WHEN t.type='buy' THEN t.shares ELSE -t.shares END) AS total_shares,
            SUM(CASE WHEN t.type='buy' THEN t.shares * t.price_eur ELSE 0 END) /
                NULLIF(SUM(CASE WHEN t.type='buy' THEN t.shares ELSE 0 END), 0) AS avg_buy_price_eur
        FROM transactions t
        WHERE 1=1 {tx_date_filter} {broker_filter}
        GROUP BY t.asset_id
        HAVING SUM(CASE WHEN t.type='buy' THEN t.shares ELSE -t.shares END) > 0.000001
    ),
    latest_prices AS (
        SELECT DISTINCT ON (asset_id)
            asset_id, price, price_eur, currency, date
        FROM prices
        ORDER BY asset_id, date DESC
    ),
    prev_prices AS (
        SELECT DISTINCT ON (p.asset_id)
            p.asset_id, p.price_eur AS prev_price_eur
        FROM prices p
        JOIN (
            SELECT asset_id, MAX(date) AS max_date FROM prices GROUP BY asset_id
        ) latest ON p.asset_id = latest.asset_id AND p.date < latest.max_date
        ORDER BY p.asset_id, p.date DESC
    ),
    total_value AS (
        SELECT SUM(h2.total_shares * lp2.price_eur) AS total
        FROM holdings h2
        JOIN latest_prices lp2 ON lp2.asset_id = h2.asset_id
    )
    SELECT
        a.id                                                         AS asset_id,
        a.name,
        a.ticker,
        a.type,
        a.currency,
        a.image_url,
        a.manual_price,
        h.total_shares,
        h.avg_buy_price_eur,
        lp.price                                                     AS current_price,
        lp.price_eur                                                 AS current_price_eur,
        h.total_shares * lp.price_eur                               AS value_eur,
        h.total_shares * lp.price                                   AS value_ccy,
        h.total_shares * lp.price_eur - h.total_shares * h.avg_buy_price_eur AS pnl_eur,
        h.total_shares * lp.price - h.total_shares * (h.avg_buy_price_eur / NULLIF(lp.price_eur / NULLIF(lp.price,0),0)) AS pnl_ccy,
        (lp.price_eur / NULLIF(h.avg_buy_price_eur, 0) - 1) * 100 AS gain_pct,
        (lp.price_eur / NULLIF(pp.prev_price_eur, 0) - 1) * 100   AS daily_change_pct,
        CASE WHEN tv.total > 0
             THEN (h.total_shares * lp.price_eur) / tv.total * 100
             ELSE 0 END                                              AS allocation_pct
    FROM holdings h
    JOIN assets a ON a.id = h.asset_id
    JOIN latest_prices lp ON lp.asset_id = h.asset_id
    LEFT JOIN prev_prices pp ON pp.asset_id = h.asset_id
    CROSS JOIN total_value tv
    WHERE 1=1 {type_filter}
    ORDER BY value_eur DESC
    """

    rows = conn.execute(query, params).fetchall()
    result = []
    for row in rows:
        result.append(
            HoldingRow(
                asset_id=row[0],
                name=row[1],
                ticker=row[2],
                type=row[3],
                currency=row[4],
                broker=None,
                image_url=row[5],
                manual_price=bool(row[6]),
                total_shares=float(row[7]),
                avg_buy_price_eur=float(row[8]),
                current_price=float(row[9]),
                current_price_eur=float(row[10]),
                value_eur=float(row[11]),
                value_ccy=float(row[12]),
                pnl_eur=float(row[13]),
                pnl_ccy=float(row[14]),
                gain_pct=float(row[15]),
                daily_change_pct=float(row[16]) if row[16] is not None else None,
                allocation_pct=float(row[17]),
            )
        )
    return result


def get_summary(conn: duckdb.DuckDBPyConnection) -> PortfolioSummary:
    row = conn.execute("""
    WITH holdings AS (
        SELECT
            asset_id,
            SUM(CASE WHEN type='buy' THEN shares ELSE -shares END) AS total_shares,
            SUM(CASE WHEN type='buy' THEN shares * price_eur ELSE 0 END) /
                NULLIF(SUM(CASE WHEN type='buy' THEN shares ELSE 0 END), 0) AS avg_buy_price_eur
        FROM transactions
        GROUP BY asset_id
        HAVING SUM(CASE WHEN type='buy' THEN shares ELSE -shares END) > 0.000001
    ),
    latest_prices AS (
        SELECT DISTINCT ON (asset_id) asset_id, price_eur, date
        FROM prices ORDER BY asset_id, date DESC
    ),
    joined AS (
        SELECT
            h.total_shares * lp.price_eur                               AS value_eur,
            h.total_shares * h.avg_buy_price_eur                        AS invested_eur,
            lp.date
        FROM holdings h
        JOIN latest_prices lp ON lp.asset_id = h.asset_id
    )
    SELECT
        COALESCE(SUM(value_eur), 0)              AS total_value_eur,
        COALESCE(SUM(invested_eur), 0)           AS total_invested_eur,
        COALESCE(SUM(value_eur - invested_eur), 0) AS total_pnl_eur,
        MAX(date)                                AS last_updated
    FROM joined
    """).fetchone()

    # fetchone() returns None if the inner query has zero rows (no prices loaded yet)
    if row is None or row[0] is None:
        return PortfolioSummary(
            total_value_eur=0.0,
            total_invested_eur=0.0,
            total_pnl_eur=0.0,
            total_pnl_pct=0.0,
            last_updated=None,
        )

    total_value = float(row[0])
    total_invested = float(row[1])
    pnl = float(row[2])
    pnl_pct = (pnl / total_invested * 100) if total_invested > 0 else 0.0

    return PortfolioSummary(
        total_value_eur=total_value,
        total_invested_eur=total_invested,
        total_pnl_eur=pnl,
        total_pnl_pct=pnl_pct,
        last_updated=row[3],
    )


def get_chart_data(
    conn: duckdb.DuckDBPyConnection,
    period: Optional[str] = "ytd",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[ChartPoint]:
    if period and not date_from:
        date_from, date_to = _period_to_date_range(period)

    # Build date range filter (applied inside date_spine CTE against bare `prices` table)
    date_filter = ""
    params: list = []
    if date_from:
        date_filter += " AND date >= ?"
        params.append(date_from)
    if date_to:
        date_filter += " AND date <= ?"
        params.append(date_to)

    # For each day, calculate the portfolio value based on holdings at that time
    # Uses ASOF-style logic: for each (asset, date) we take holdings as of that date
    # and multiply by the price on that date (using last known price via window function)
    query = f"""
    WITH date_spine AS (
        SELECT DISTINCT date FROM prices
        WHERE 1=1 {date_filter}
    ),
    cumulative_holdings AS (
        SELECT
            t.asset_id,
            d.date AS price_date,
            SUM(CASE WHEN t.type='buy' AND t.date <= d.date THEN t.shares
                     WHEN t.type='sell' AND t.date <= d.date THEN -t.shares
                     ELSE 0 END) AS shares_held
        FROM date_spine d
        CROSS JOIN (SELECT DISTINCT asset_id FROM transactions) assets
        JOIN transactions t ON t.asset_id = assets.asset_id
        GROUP BY t.asset_id, d.date
        HAVING SUM(CASE WHEN t.type='buy' AND t.date <= d.date THEN t.shares
                        WHEN t.type='sell' AND t.date <= d.date THEN -t.shares
                        ELSE 0 END) > 0.000001
    ),
    prices_filled AS (
        SELECT
            ch.asset_id,
            ch.price_date,
            ch.shares_held,
            LAST_VALUE(p.price_eur IGNORE NULLS) OVER (
                PARTITION BY ch.asset_id
                ORDER BY ch.price_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS price_eur
        FROM cumulative_holdings ch
        LEFT JOIN prices p ON p.asset_id = ch.asset_id AND p.date = ch.price_date
    )
    SELECT
        price_date AS date,
        SUM(shares_held * COALESCE(price_eur, 0)) AS value_eur
    FROM prices_filled
    WHERE price_eur IS NOT NULL
    GROUP BY price_date
    ORDER BY price_date
    """

    rows = conn.execute(query, params).fetchall()
    return [ChartPoint(date=row[0], value_eur=float(row[1])) for row in rows]
