"""
Core DuckDB analytical queries for portfolio metrics.
All calculations are dynamic — no stored snapshots.
"""
import bisect
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
        "3m": today - timedelta(days=91),
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
                NULLIF(SUM(CASE WHEN t.type='buy' THEN t.shares ELSE 0 END), 0) AS avg_buy_price_eur,
            SUM(CASE WHEN t.type='buy' THEN t.shares * t.price ELSE 0 END) /
                NULLIF(SUM(CASE WHEN t.type='buy' THEN t.shares ELSE 0 END), 0) AS avg_buy_price,
            STRING_AGG(DISTINCT t.broker, ', ' ORDER BY t.broker) AS broker
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
        -- LEFT JOIN so assets with no prices yet contribute 0 (not excluded)
        SELECT COALESCE(SUM(h2.total_shares * COALESCE(lp2.price_eur, 0)), 0) AS total
        FROM holdings h2
        LEFT JOIN latest_prices lp2 ON lp2.asset_id = h2.asset_id
    )
    SELECT
        a.id                                                              AS asset_id,
        a.name,
        a.ticker,
        a.type,
        a.currency,
        a.image_url,
        a.manual_price,
        h.broker,
        h.total_shares,
        h.avg_buy_price_eur,
        h.avg_buy_price,
        lp.price                                                          AS current_price,
        lp.price_eur                                                      AS current_price_eur,
        h.total_shares * lp.price_eur                                    AS value_eur,
        h.total_shares * lp.price                                        AS value_ccy,
        h.total_shares * lp.price_eur - h.total_shares * h.avg_buy_price_eur AS pnl_eur,
        h.total_shares * lp.price - h.total_shares * (h.avg_buy_price_eur / NULLIF(lp.price_eur / NULLIF(lp.price, 0), 0)) AS pnl_ccy,
        (lp.price_eur / NULLIF(h.avg_buy_price_eur, 0) - 1) * 100       AS gain_pct,
        (lp.price_eur / NULLIF(pp.prev_price_eur, 0) - 1) * 100         AS daily_change_pct,
        CASE WHEN tv.total > 0 AND lp.price_eur IS NOT NULL
             THEN (h.total_shares * lp.price_eur) / tv.total * 100
             ELSE 0 END                                                   AS allocation_pct
    FROM holdings h
    JOIN assets a ON a.id = h.asset_id
    LEFT JOIN latest_prices lp ON lp.asset_id = h.asset_id
    LEFT JOIN prev_prices pp ON pp.asset_id = h.asset_id
    CROSS JOIN total_value tv
    WHERE 1=1 {type_filter}
    ORDER BY COALESCE(value_eur, -1) DESC
    """

    rows = conn.execute(query, params).fetchall()
    result = []
    for row in rows:
        def _f(v) -> Optional[float]:
            return float(v) if v is not None else None

        result.append(
            HoldingRow(
                asset_id=row[0],
                name=row[1],
                ticker=row[2],
                type=row[3],
                currency=row[4],
                image_url=row[5],
                manual_price=bool(row[6]),
                broker=row[7],
                total_shares=float(row[8]),
                avg_buy_price_eur=float(row[9]),
                avg_buy_price=float(row[10]),
                current_price=_f(row[11]),
                current_price_eur=_f(row[12]),
                value_eur=_f(row[13]),
                value_ccy=_f(row[14]),
                pnl_eur=_f(row[15]),
                pnl_ccy=_f(row[16]),
                gain_pct=_f(row[17]),
                daily_change_pct=_f(row[18]),
                allocation_pct=float(row[19]),
            )
        )
    return result


def get_realized_pnl(conn: duckdb.DuckDBPyConnection) -> dict:
    """
    Compute realized P&L using the running Average Cost (AVCO) method.
    Processes transactions chronologically per asset; on each sell the gain is
    shares_sold × (sell_price_eur − avg_cost_eur_at_that_moment).
    """
    rows = conn.execute("""
        SELECT asset_id, type, shares, price_eur
        FROM transactions
        ORDER BY asset_id, date, id
    """).fetchall()

    avg_costs: dict[int, float] = {}
    shares_held: dict[int, float] = {}
    realized_pnl = 0.0
    cost_of_sold = 0.0
    total_invested_ever = 0.0

    for asset_id, tx_type, shares, price_eur in rows:
        shares = float(shares)
        price_eur = float(price_eur)
        cur_shares = shares_held.get(asset_id, 0.0)
        cur_avg = avg_costs.get(asset_id, 0.0)

        if tx_type == "buy":
            total_shares = cur_shares + shares
            avg_costs[asset_id] = (cur_shares * cur_avg + shares * price_eur) / total_shares
            shares_held[asset_id] = total_shares
            total_invested_ever += shares * price_eur
        else:
            gain = shares * (price_eur - cur_avg)
            realized_pnl += gain
            cost_of_sold += shares * cur_avg
            shares_held[asset_id] = max(cur_shares - shares, 0.0)

    realized_pct = (realized_pnl / cost_of_sold * 100) if cost_of_sold > 0 else 0.0
    return {
        "realized_pnl_eur": realized_pnl,
        "realized_pnl_pct": realized_pct,
        "total_invested_ever_eur": total_invested_ever,
    }


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

    realized = get_realized_pnl(conn)

    # fetchone() returns None if the inner query has zero rows (no prices loaded yet)
    if row is None or row[0] is None:
        return PortfolioSummary(
            total_value_eur=0.0,
            total_invested_eur=0.0,
            total_pnl_eur=0.0,
            total_pnl_pct=0.0,
            last_updated=None,
            **realized,
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
        **realized,
    )


def _build_invested_step_series(conn: duckdb.DuckDBPyConnection) -> tuple[list[date], list[float]]:
    """
    Return (dates, values) sorted ascending where each value is the remaining
    cost basis AFTER all transactions on that date, using the running AVCO method.

    "Invested" = cost of shares still held = total_buy_cost − (sold_shares × avg_cost_at_sell).
    This is consistent with get_realized_pnl and can never go negative.
    """
    rows = conn.execute("""
        SELECT asset_id, type, shares, price_eur, date
        FROM transactions
        ORDER BY date, id
    """).fetchall()

    def _to_date(v) -> date:
        return v if isinstance(v, date) else v.date()

    avg_costs: dict[int, float] = {}
    shares_held: dict[int, float] = {}
    cost_basis = 0.0
    step_dates: list[date] = []
    step_values: list[float] = []

    i = 0
    while i < len(rows):
        day = _to_date(rows[i][4])
        while i < len(rows) and _to_date(rows[i][4]) == day:
            asset_id, tx_type, shares, price_eur, _ = rows[i]
            shares, price_eur = float(shares), float(price_eur)
            cur = shares_held.get(asset_id, 0.0)
            avg = avg_costs.get(asset_id, 0.0)
            if tx_type == "buy":
                new_total = cur + shares
                avg_costs[asset_id] = (cur * avg + shares * price_eur) / new_total
                shares_held[asset_id] = new_total
                cost_basis += shares * price_eur
            else:
                cost_basis = max(cost_basis - shares * avg, 0.0)
                shares_held[asset_id] = max(cur - shares, 0.0)
            i += 1
        step_dates.append(day)
        step_values.append(cost_basis)

    return step_dates, step_values


def get_chart_data(
    conn: duckdb.DuckDBPyConnection,
    period: Optional[str] = "ytd",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[ChartPoint]:
    if period and not date_from:
        date_from, date_to = _period_to_date_range(period)

    date_filter = ""
    params: list = []
    if date_from:
        date_filter += " AND date >= ?"
        params.append(date_from)
    if date_to:
        date_filter += " AND date <= ?"
        params.append(date_to)

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

    # Build invested step series (AVCO cost basis) and forward-fill onto chart dates
    step_dates, step_values = _build_invested_step_series(conn)

    def _invested_at(chart_date) -> Optional[float]:
        if not step_dates:
            return None
        d = chart_date if isinstance(chart_date, date) else chart_date.date()
        idx = bisect.bisect_right(step_dates, d) - 1
        return step_values[idx] if idx >= 0 else None

    return [
        ChartPoint(date=row[0], value_eur=float(row[1]), invested_eur=_invested_at(row[0]))
        for row in rows
    ]
