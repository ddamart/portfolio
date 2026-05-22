"""
Core DuckDB analytical queries for portfolio metrics.
All calculations are dynamic — no stored snapshots.
"""
import bisect
from datetime import date, timedelta
from typing import Optional

import duckdb

from app.models.portfolio import ChartPoint, HoldingRow, PortfolioSummary


def _parse_filter_list(value: Optional[str]) -> list[str]:
    """Split a comma-separated filter string into a non-empty list, or [] if None/empty."""
    if not value:
        return []
    return [v.strip() for v in value.split(',') if v.strip()]


def _in_clause(column: str, values: list[str], params: list) -> str:
    """Append values to params and return 'AND column IN (?, ...)' or '' if no values."""
    if not values:
        return ""
    placeholders = ','.join('?' * len(values))
    params.extend(values)
    return f"AND {column} IN ({placeholders})"


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

    # latest_date caps price lookups so historical date_to shows correct prices
    latest_date = date_to or date.today()

    # Build transaction filter for date range (affects what's considered "bought by then")
    tx_date_filter = ""
    params: list = []
    if date_to:
        tx_date_filter = "AND t.date <= ?"
        params.append(date_to)

    broker_list = _parse_filter_list(broker)
    broker_filter = _in_clause("t.broker", broker_list, params)

    params.append(latest_date)  # for latest_prices WHERE date <= ?

    type_list = _parse_filter_list(asset_type)
    type_filter = _in_clause("a.type", type_list, params)

    query = f"""
    WITH holdings AS (
        SELECT
            t.asset_id,
            SUM(CASE WHEN t.type='buy' THEN t.shares::DOUBLE ELSE -t.shares::DOUBLE END) AS total_shares,
            SUM(CASE WHEN t.type='buy' THEN t.shares::DOUBLE * t.price_eur::DOUBLE ELSE 0.0 END) /
                NULLIF(SUM(CASE WHEN t.type='buy' THEN t.shares::DOUBLE ELSE 0.0 END), 0) AS avg_buy_price_eur,
            SUM(CASE WHEN t.type='buy' THEN t.shares::DOUBLE * t.price::DOUBLE ELSE 0.0 END) /
                NULLIF(SUM(CASE WHEN t.type='buy' THEN t.shares::DOUBLE ELSE 0.0 END), 0) AS avg_buy_price,
            STRING_AGG(DISTINCT t.broker, ', ' ORDER BY t.broker) AS broker
        FROM transactions t
        WHERE 1=1 {tx_date_filter} {broker_filter}
        GROUP BY t.asset_id
        HAVING SUM(CASE WHEN t.type='buy' THEN t.shares::DOUBLE ELSE -t.shares::DOUBLE END) > 0.000001
    ),
    latest_prices AS (
        SELECT DISTINCT ON (asset_id)
            asset_id, price::DOUBLE AS price, price_eur::DOUBLE AS price_eur, currency, date
        FROM prices
        WHERE date <= ?
        ORDER BY asset_id, date DESC
    ),
    prev_prices AS (
        SELECT DISTINCT ON (p.asset_id)
            p.asset_id, p.price_eur::DOUBLE AS prev_price_eur
        FROM prices p
        JOIN (
            SELECT asset_id, MAX(date) AS max_date FROM prices GROUP BY asset_id
        ) latest ON p.asset_id = latest.asset_id AND p.date < latest.max_date
        ORDER BY p.asset_id, p.date DESC
    ),
    total_value AS (
        -- LEFT JOIN so assets with no prices yet contribute 0 (not excluded)
        SELECT COALESCE(SUM(h2.total_shares * COALESCE(lp2.price_eur, 0.0)), 0.0) AS total
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

    # Per-asset Modified Dietz performance when a period start date is known
    if date_from and result:
        period_data = _compute_period_holding_data(
            conn, result, date_from, date_to or date.today()
        )
        result = [h.model_copy(update=period_data.get(h.asset_id, {})) for h in result]

    # Append balance-type asset rows (unless a non-balance asset_type filter is active)
    if not type_list or 'balance' in type_list:
        balance_rows = _get_balance_holdings(conn, latest_date, broker=broker, date_from=date_from)
        if balance_rows:
            tx_total = sum((h.value_eur or 0.0) for h in result)
            bal_total = sum((h.balance_value_eur or 0.0) for h in balance_rows)
            # Allocation pools are separate: balance % among balance, stocks % among stocks
            if tx_total > 0:
                result = [
                    h.model_copy(update={"allocation_pct": ((h.value_eur or 0.0) / tx_total * 100)})
                    for h in result
                ]
            if bal_total > 0:
                balance_rows = [
                    h.model_copy(update={"allocation_pct": ((h.balance_value_eur or 0.0) / bal_total * 100)})
                    for h in balance_rows
                ]
            result = result + balance_rows

    return result


def _get_balance_holdings(
    conn: duckdb.DuckDBPyConnection,
    latest_date: date,
    broker: Optional[str] = None,
    date_from: Optional[date] = None,
) -> list[HoldingRow]:
    """Return HoldingRow entries for all balance-type assets."""
    # broker filter not applicable to balance assets (they have no broker), but we
    # skip the entire query if a broker filter is set (balance assets have no broker).
    if broker:
        return []

    rows = conn.execute("""
    WITH latest_snap AS (
        SELECT DISTINCT ON (asset_id) asset_id, amount_eur AS value_eur, date AS snap_date
        FROM balance_entries
        WHERE type = 'snapshot' AND date <= ?
        ORDER BY asset_id, date DESC
    ),
    net_contrib AS (
        SELECT asset_id,
               SUM(CASE WHEN type='deposit' THEN amount_eur ELSE -amount_eur END) AS contrib_eur
        FROM balance_entries
        WHERE type IN ('deposit', 'withdrawal')
        GROUP BY asset_id
    )
    SELECT a.id, a.name, a.ticker, a.currency, a.image_url, a.manual_price,
           COALESCE(ls.value_eur, 0) AS value_eur,
           ls.snap_date,
           COALESCE(nc.contrib_eur, 0) AS contrib_eur
    FROM assets a
    LEFT JOIN latest_snap ls ON ls.asset_id = a.id
    LEFT JOIN net_contrib nc ON nc.asset_id = a.id
    WHERE a.type = 'balance'
    """, [latest_date]).fetchall()

    # Period start snapshot per asset: earliest snapshot >= date_from
    start_by_asset: dict[int, float] = {}
    if date_from:
        start_rows = conn.execute("""
            SELECT DISTINCT ON (asset_id) asset_id, amount_eur
            FROM balance_entries
            WHERE type = 'snapshot' AND date >= ?
            ORDER BY asset_id, date ASC
        """, [date_from]).fetchall()
        start_by_asset = {int(r[0]): float(r[1]) for r in start_rows}

    # Individual period flows per asset (date > date_from AND date <= latest_date)
    # Used for Modified Dietz: need amounts and dates for time-weighting
    D = max((latest_date - date_from).days, 1) if date_from else 1
    period_flows_by_asset: dict[int, list[tuple[float, date]]] = {}
    if date_from:
        flow_rows = conn.execute("""
            SELECT be.asset_id, be.type, be.amount_eur::DOUBLE, be.date
            FROM balance_entries be
            JOIN assets a ON a.id = be.asset_id
            WHERE a.type = 'balance'
              AND be.type IN ('deposit', 'withdrawal')
              AND be.date > ? AND be.date <= ?
            ORDER BY be.asset_id, be.date
        """, [date_from, latest_date]).fetchall()
        for r in flow_rows:
            aid = int(r[0])
            cf = float(r[2]) if r[1] == 'deposit' else -float(r[2])
            cf_date = r[3] if isinstance(r[3], date) else r[3].date()
            period_flows_by_asset.setdefault(aid, []).append((cf, cf_date))

    result = []
    for row in rows:
        asset_id = int(row[0])
        name = row[1]
        ticker = row[2]
        currency = row[3]
        image_url = row[4]
        manual_price = bool(row[5])
        value_eur = float(row[6]) if row[6] is not None else 0.0
        snap_date = row[7]
        contrib_eur = float(row[8]) if row[8] is not None else 0.0

        pnl_eur = value_eur - contrib_eur
        gain_pct = (pnl_eur / contrib_eur * 100) if contrib_eur > 0 else None

        period_start = start_by_asset.get(asset_id)
        flows = period_flows_by_asset.get(asset_id, [])

        # Net flows within the period window (shown in "Aportaciones netas" column)
        period_net_flows = sum(cf for cf, _ in flows) if date_from else None

        # Modified Dietz for the period
        if period_start is not None:
            weighted_cf = sum(
                cf * (D - (cf_date - date_from).days) / D
                for cf, cf_date in flows
            ) if date_from else 0.0
            period_gain = value_eur - period_start - (period_net_flows or 0.0)
            denominator = period_start + weighted_cf
            period_pct = (period_gain / denominator * 100) if abs(denominator) > 0.01 else None
        else:
            period_gain = None
            period_pct = None

        result.append(
            HoldingRow(
                asset_id=asset_id,
                name=name,
                ticker=ticker,
                type="balance",
                currency=currency,
                broker=None,
                image_url=image_url,
                manual_price=manual_price,
                total_shares=0.0,
                avg_buy_price_eur=0.0,
                avg_buy_price=0.0,
                current_price=None,
                current_price_eur=None,
                value_eur=value_eur,
                value_ccy=None,
                pnl_eur=pnl_eur,
                pnl_ccy=None,
                gain_pct=gain_pct,
                daily_change_pct=None,
                allocation_pct=0.0,  # will be recalculated by caller
                balance_value_eur=value_eur,
                balance_contributions_eur=contrib_eur,
                balance_last_snapshot_date=str(snap_date) if snap_date is not None else None,
                period_start_value_eur=period_start,
                period_gain_eur=period_gain,
                period_gain_pct=period_pct,
                period_net_flows_eur=period_net_flows,
            )
        )
    return result


def get_value_at_date(
    conn: duckdb.DuckDBPyConnection,
    target_date: date,
    broker: Optional[str] = None,
    asset_type: Optional[str] = None,
    bal_direction: str = 'before',
) -> float:
    """Portfolio market value as of target_date using the last price on or before that date."""
    asset_type_filter = ""
    broker_filter = ""
    # Param order must match SQL placeholder order:
    #   1-2: SELECT CASE WHEN t.date <= ?
    #   3+:  WHERE filters (asset_type?, broker?) ← injected between SELECT and HAVING dates
    #   N+1: HAVING CASE WHEN t.date <= ?
    #   N+2: HAVING CASE WHEN t.date <= ?
    #   N+3: price_asof WHERE date <= ?
    params: list = [target_date, target_date]

    type_list = _parse_filter_list(asset_type)
    if type_list:
        placeholders = ','.join('?' * len(type_list))
        asset_type_filter = f"AND t.asset_id IN (SELECT id FROM assets WHERE type IN ({placeholders}))"
        params.extend(type_list)
    broker_list = _parse_filter_list(broker)
    broker_filter = _in_clause("t.broker", broker_list, params)

    params.extend([target_date, target_date, target_date])  # HAVING dates + price_asof

    query = f"""
    WITH holdings_at AS (
        SELECT
            t.asset_id,
            SUM(CASE WHEN t.type='buy'  AND t.date <= ? THEN  t.shares::DOUBLE
                     WHEN t.type='sell' AND t.date <= ? THEN -t.shares::DOUBLE
                     ELSE 0.0 END) AS shares_held
        FROM transactions t
        WHERE 1=1 {asset_type_filter} {broker_filter}
        GROUP BY t.asset_id
        HAVING SUM(CASE WHEN t.type='buy'  AND t.date <= ? THEN  t.shares::DOUBLE
                        WHEN t.type='sell' AND t.date <= ? THEN -t.shares::DOUBLE
                        ELSE 0.0 END) > 0.000001
    ),
    price_asof AS (
        SELECT DISTINCT ON (asset_id)
            asset_id, price_eur::DOUBLE AS price_eur
        FROM prices
        WHERE date <= ?
        ORDER BY asset_id, date DESC
    )
    SELECT COALESCE(SUM(h.shares_held * p.price_eur), 0.0)
    FROM holdings_at h
    JOIN price_asof p ON p.asset_id = h.asset_id
    """
    row = conn.execute(query, params).fetchone()
    tx_value = float(row[0]) if row and row[0] is not None else 0.0

    # Add balance asset snapshot values (unless filtering by a non-balance asset_type)
    if not type_list or 'balance' in type_list:
        # broker filter skips balance assets (they have no broker)
        if not broker_list:
            if bal_direction == 'after':
                snap_where = "AND date >= ?"
                snap_order = "ASC"
            else:
                snap_where = "AND date <= ?"
                snap_order = "DESC"
            bal_row = conn.execute(f"""
                SELECT COALESCE(SUM(be.amount_eur), 0)
                FROM (
                    SELECT DISTINCT ON (asset_id) asset_id, amount_eur
                    FROM balance_entries
                    WHERE type = 'snapshot' {snap_where}
                    ORDER BY asset_id, date {snap_order}
                ) be
                JOIN assets a ON a.id = be.asset_id
                WHERE a.type = 'balance'
            """, [target_date]).fetchone()
            bal_value = float(bal_row[0]) if bal_row and bal_row[0] is not None else 0.0
            return tx_value + bal_value

    return tx_value


def get_realized_pnl(
    conn: duckdb.DuckDBPyConnection,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    broker: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> dict:
    """
    Compute realized P&L using the running Average Cost (AVCO) method.

    When date_from / date_to are provided only sells within that window are
    counted towards the P&L figures; the AVCO cost basis is still built from
    all historical transactions (including those before the window) so the
    per-share cost is always correct.

    Two figures returned:
    - realized_pnl_eur / _pct  : price-only gain (no commissions)
    - realized_pnl_net_eur / _pct : net of all commissions — buy commissions
      are folded into the AVCO cost basis; sell commissions are deducted on exit.
    """
    asset_join = ""
    filters = ""
    params: list = []

    type_list = _parse_filter_list(asset_type)
    broker_list = _parse_filter_list(broker)
    if type_list:
        asset_join = "JOIN assets a ON a.id = t.asset_id"
        filters += " " + _in_clause("a.type", type_list, params)
    if broker_list:
        filters += " " + _in_clause("t.broker", broker_list, params)

    rows = conn.execute(f"""
        SELECT t.asset_id, t.type, t.shares, t.price_eur, t.commission_eur, t.date
        FROM transactions t
        {asset_join}
        WHERE 1=1 {filters}
        ORDER BY t.asset_id, t.date, t.id
    """, params).fetchall()

    avg_costs: dict[int, float] = {}      # AVCO price-only
    avg_costs_net: dict[int, float] = {}  # AVCO including buy commissions
    shares_held: dict[int, float] = {}
    realized_pnl = 0.0
    cost_of_sold = 0.0
    realized_pnl_net = 0.0
    cost_of_sold_net = 0.0
    total_invested_ever = 0.0

    for asset_id, tx_type, shares, price_eur, commission_eur, tx_date in rows:
        shares = float(shares)
        price_eur = float(price_eur)
        commission_eur = float(commission_eur)
        tx_date = tx_date if isinstance(tx_date, date) else tx_date.date()

        cur_shares = shares_held.get(asset_id, 0.0)
        cur_avg = avg_costs.get(asset_id, 0.0)
        cur_avg_net = avg_costs_net.get(asset_id, 0.0)

        if tx_type == "buy":
            total_shares = cur_shares + shares
            avg_costs[asset_id] = (cur_shares * cur_avg + shares * price_eur) / total_shares
            # Net AVCO: spread buy commission across acquired shares
            avg_costs_net[asset_id] = (cur_shares * cur_avg_net + shares * price_eur + commission_eur) / total_shares
            shares_held[asset_id] = total_shares
            total_invested_ever += shares * price_eur
        else:
            # Always advance AVCO state for sells (even outside the window)
            shares_held[asset_id] = max(cur_shares - shares, 0.0)

            in_window = (
                (date_from is None or tx_date >= date_from) and
                (date_to   is None or tx_date <= date_to)
            )
            if in_window:
                gain = shares * (price_eur - cur_avg)
                realized_pnl += gain
                cost_of_sold += shares * cur_avg
                # Net: use commission-adjusted AVCO and subtract sell commission
                gain_net = shares * (price_eur - cur_avg_net) - commission_eur
                realized_pnl_net += gain_net
                cost_of_sold_net += shares * cur_avg_net

    realized_pct = (realized_pnl / cost_of_sold * 100) if cost_of_sold > 0 else 0.0
    realized_net_pct = (realized_pnl_net / cost_of_sold_net * 100) if cost_of_sold_net > 0 else 0.0
    return {
        "realized_pnl_eur": realized_pnl,
        "realized_pnl_pct": realized_pct,
        "total_invested_ever_eur": total_invested_ever,
        "realized_pnl_net_eur": realized_pnl_net,
        "realized_pnl_net_pct": realized_net_pct,
    }


def _compute_period_holding_data(
    conn: duckdb.DuckDBPyConnection,
    holdings: list,
    date_from: date,
    date_to: date,
) -> dict:
    """
    Per-asset period performance for [date_from, date_to].

    Returns dict mapping asset_id → partial HoldingRow field overrides:
      period_start_value_eur, period_invested_eur, period_avg_price_eur,
      period_gain_eur, period_gain_pct.

    gain_pct uses simple ROI (gain / period_invested) rather than
    time-weighted Modified Dietz, which is reserved for the portfolio summary.
    """
    # V_ini per asset: shares held at close of date_from × price at date_from.
    # Transactions on date_from are included in V_ini (not in CF), so the per-asset
    # "start value" aligns with the first visible chart point.
    ini_rows = conn.execute("""
    WITH holdings_at AS (
        SELECT
            asset_id,
            SUM(CASE WHEN type='buy'  AND date <= ? THEN  shares::DOUBLE
                     WHEN type='sell' AND date <= ? THEN -shares::DOUBLE
                     ELSE 0.0 END) AS shares_held
        FROM transactions
        GROUP BY asset_id
        HAVING SUM(CASE WHEN type='buy'  AND date <= ? THEN  shares::DOUBLE
                        WHEN type='sell' AND date <= ? THEN -shares::DOUBLE
                        ELSE 0.0 END) > 0.000001
    ),
    price_asof AS (
        SELECT DISTINCT ON (asset_id)
            asset_id,
            price::DOUBLE     AS price,
            price_eur::DOUBLE AS price_eur
        FROM prices
        WHERE date <= ?
        ORDER BY asset_id, date DESC
    )
    SELECT h.asset_id, p.price, p.price_eur, h.shares_held * p.price_eur AS value_eur
    FROM holdings_at h
    JOIN price_asof p ON p.asset_id = h.asset_id
    """, [date_from, date_from, date_from, date_from, date_from]).fetchall()

    ini_by_asset: dict[int, dict] = {}
    for row in ini_rows:
        ini_by_asset[int(row[0])] = {
            "price":     float(row[1]),
            "price_eur": float(row[2]),
            "value_eur": float(row[3]),
        }

    # Cash flows per asset: date_from transactions already in V_ini, so start from date_from+1
    tx_rows = conn.execute("""
        SELECT asset_id, type, shares::DOUBLE, price_eur::DOUBLE, commission_eur::DOUBLE, date
        FROM transactions
        WHERE date > ? AND date <= ?
        ORDER BY asset_id, date, id
    """, [date_from, date_to]).fetchall()

    from collections import defaultdict
    cfs_by_asset: dict[int, list] = defaultdict(list)
    for row in tx_rows:
        asset_id = int(row[0])
        tx_type, shares, price_eur, commission_eur = row[1], float(row[2]), float(row[3]), float(row[4])
        tx_date = row[5] if isinstance(row[5], date) else row[5].date()
        cfs_by_asset[asset_id].append((tx_type, shares, price_eur, commission_eur, tx_date))

    result: dict[int, dict] = {}
    for h in holdings:
        asset_id = h.asset_id

        if h.value_eur is None:
            result[asset_id] = {
                "period_start_value_eur": None,
                "period_invested_eur": None,
                "period_avg_price_eur": None,
                "period_gain_eur": None,
                "period_gain_pct": None,
            }
            continue

        ini = ini_by_asset.get(asset_id)
        v_ini = ini["value_eur"] if ini else 0.0
        v_fin = float(h.value_eur)

        cf_total = 0.0
        for tx_type, shares, price_eur, commission_eur, tx_date in cfs_by_asset.get(asset_id, []):
            cf = (shares * price_eur + commission_eur) if tx_type == "buy" \
                 else -(shares * price_eur - commission_eur)
            cf_total += cf

        # period_invested = V_ini + net cash flows (buy cost − sell proceeds + commissions)
        # Simple ROI: gain / period_invested — consistent with the € amount shown.
        # Time-weighted Modified Dietz is reserved for the portfolio-level summary.
        period_invested = v_ini + cf_total
        period_avg_price = (period_invested / h.total_shares) if h.total_shares > 0.000001 else None

        gain_eur = v_fin - period_invested
        # Use max(period_invested, v_ini) as denominator so sells within the period
        # cannot collapse it to near-zero and produce nonsensical percentages.
        # When there are no sells (or new positions), max() has no effect.
        pct_denom = max(period_invested, v_ini)
        gain_pct = (gain_eur / pct_denom * 100) if abs(pct_denom) > 0.01 else 0.0

        result[asset_id] = {
            "period_start_value_eur": ini["value_eur"] if ini else None,
            "period_invested_eur": period_invested,
            "period_avg_price_eur": period_avg_price,
            "period_gain_eur": gain_eur,
            "period_gain_pct": gain_pct,
        }

    return result


def get_modified_dietz(
    conn: duckdb.DuckDBPyConnection,
    date_from: date,
    date_to: date,
    current_value: float,
    broker: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> dict:
    """
    Modified Dietz performance measurement for [date_from, date_to].

    V_ini  = portfolio value at close of date_from (the first visible chart point).
             Transactions on date_from are included in V_ini, NOT in CF, so the
             card and chart first point are always aligned.
    V_fin  = current_value (passed in from get_summary).
    CF_i   = external cash flows on dates AFTER date_from:
               buy  → positive (investor injects capital)
               sell → negative (investor withdraws capital)
               balance deposit → positive (same as buy)
               balance withdrawal → negative (same as sell)
             Commissions are folded into transaction CFs.
    W_i    = (D − d_i) / D  — fraction of the period still remaining when CF_i occurred.

    R% = (V_fin − V_ini − ΣCF) / (V_ini + Σ(CF_i × W_i))
    Gain€ = V_fin − V_ini − ΣCF  (pure market contribution, net of capital movements)
    """
    V_ini = get_value_at_date(conn, date_from, broker=broker, asset_type=asset_type, bal_direction='after')
    V_fin = current_value
    D = max((date_to - date_from).days, 1)  # avoid /0 on same-day periods

    cf_filters = ""
    cf_params: list = [date_from, date_to]
    type_list = _parse_filter_list(asset_type)
    broker_list = _parse_filter_list(broker)
    if type_list:
        placeholders = ','.join('?' * len(type_list))
        cf_filters += f" AND asset_id IN (SELECT id FROM assets WHERE type IN ({placeholders}))"
        cf_params.extend(type_list)
    if broker_list:
        cf_filters += " " + _in_clause("broker", broker_list, cf_params)

    rows = conn.execute(f"""
        SELECT type, shares::DOUBLE, price_eur::DOUBLE, commission_eur::DOUBLE, date
        FROM transactions
        WHERE date > ? AND date <= ? {cf_filters}
        ORDER BY date
    """, cf_params).fetchall()

    cf_total = 0.0
    weighted_cf = 0.0

    for tx_type, shares, price_eur, commission_eur, tx_date in rows:
        tx_date = tx_date if isinstance(tx_date, date) else tx_date.date()
        di = (tx_date - date_from).days
        wi = (D - di) / D

        cf = (shares * price_eur + commission_eur) if tx_type == "buy" \
             else -(shares * price_eur - commission_eur)

        cf_total += cf
        weighted_cf += cf * wi

    # Balance deposits/withdrawals are external CFs (no broker filter applies to balance)
    if (not type_list or 'balance' in type_list) and not broker_list:
        bal_cf_rows = conn.execute("""
            SELECT be.type, be.amount_eur::DOUBLE, be.date
            FROM balance_entries be
            JOIN assets a ON a.id = be.asset_id
            WHERE a.type = 'balance'
              AND be.type IN ('deposit', 'withdrawal')
              AND be.date > ? AND be.date <= ?
            ORDER BY be.date
        """, [date_from, date_to]).fetchall()

        for cf_type, amount_eur, cf_date in bal_cf_rows:
            cf_date = cf_date if isinstance(cf_date, date) else cf_date.date()
            di = (cf_date - date_from).days
            wi = (D - di) / D
            cf = amount_eur if cf_type == 'deposit' else -amount_eur
            cf_total += cf
            weighted_cf += cf * wi

    denominator = V_ini + weighted_cf
    gain_eur = V_fin - V_ini - cf_total
    return_pct = (gain_eur / denominator * 100) if abs(denominator) > 0.01 else 0.0

    return {
        "period_start_value_eur": V_ini,
        "period_return_eur": gain_eur,
        "period_return_pct": return_pct,
    }


def get_summary(
    conn: duckdb.DuckDBPyConnection,
    period: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    broker: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> PortfolioSummary:
    # Build SQL filter fragments (same pattern as get_holdings)
    asset_join = ""
    broker_filter = ""
    type_filter = ""
    summary_params: list = []

    type_list = _parse_filter_list(asset_type)
    broker_list = _parse_filter_list(broker)
    if type_list:
        asset_join = "JOIN assets a ON a.id = t.asset_id"
        type_filter = _in_clause("a.type", type_list, summary_params)
    if broker_list:
        broker_filter = _in_clause("t.broker", broker_list, summary_params)

    # Resolve period mode and date range before building SQL
    if period == "all":
        is_period = False
    elif period and period != "custom":
        # Named period (ytd, 1m, …) — resolve dates if not already provided
        is_period = True
        if not date_from:
            date_from, date_to = _period_to_date_range(period)
    else:
        # custom period string or no period at all — active only when date_from is explicit
        is_period = date_from is not None

    effective_date_to = date_to or date.today()

    # Add date_to filter to the holdings CTE so only transactions up to that date count
    date_to_filter = "AND t.date <= ?"
    summary_params.append(effective_date_to)

    row = conn.execute(f"""
    WITH holdings AS (
        SELECT
            t.asset_id,
            SUM(CASE WHEN t.type='buy' THEN t.shares::DOUBLE ELSE -t.shares::DOUBLE END) AS total_shares,
            SUM(CASE WHEN t.type='buy' THEN t.shares::DOUBLE * t.price_eur::DOUBLE ELSE 0.0 END) /
                NULLIF(SUM(CASE WHEN t.type='buy' THEN t.shares::DOUBLE ELSE 0.0 END), 0) AS avg_buy_price_eur
        FROM transactions t
        {asset_join}
        WHERE 1=1 {type_filter} {broker_filter} {date_to_filter}
        GROUP BY t.asset_id
        HAVING SUM(CASE WHEN t.type='buy' THEN t.shares::DOUBLE ELSE -t.shares::DOUBLE END) > 0.000001
    ),
    latest_prices AS (
        SELECT DISTINCT ON (asset_id) asset_id, price_eur::DOUBLE AS price_eur, date
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
    """, summary_params).fetchone()

    # Realized P&L: period-filtered when period mode is active
    if is_period and date_from:
        realized = get_realized_pnl(conn, date_from=date_from, date_to=date_to, broker=broker, asset_type=asset_type)
    else:
        realized = get_realized_pnl(conn, broker=broker, asset_type=asset_type)

    # Fetch balance asset totals — all use effective_date_to
    balance_value = 0.0
    balance_contrib = 0.0
    balance_gross_deposits = 0.0
    balance_gross_withdrawals = 0.0
    if (not type_list or 'balance' in type_list) and not broker_list:
        # latest snapshot sum for balance assets up to effective_date_to
        bv_row = conn.execute("""
            SELECT COALESCE(SUM(be.amount_eur), 0)
            FROM (
                SELECT DISTINCT ON (asset_id) asset_id, amount_eur
                FROM balance_entries
                WHERE type = 'snapshot' AND date <= ?
                ORDER BY asset_id, date DESC
            ) be
            JOIN assets a ON a.id = be.asset_id
            WHERE a.type = 'balance'
        """, [effective_date_to]).fetchone()
        balance_value = float(bv_row[0]) if bv_row and bv_row[0] is not None else 0.0

        bc_row = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN be.type='deposit' THEN be.amount_eur ELSE -be.amount_eur END), 0),
                COALESCE(SUM(CASE WHEN be.type='deposit' THEN be.amount_eur ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN be.type='withdrawal' THEN be.amount_eur ELSE 0 END), 0)
            FROM balance_entries be
            JOIN assets a ON a.id = be.asset_id
            WHERE a.type = 'balance' AND be.type IN ('deposit', 'withdrawal')
            AND be.date <= ?
        """, [effective_date_to]).fetchone()
        if bc_row:
            balance_contrib = float(bc_row[0]) if bc_row[0] is not None else 0.0
            balance_gross_deposits = float(bc_row[1]) if bc_row[1] is not None else 0.0
            balance_gross_withdrawals = float(bc_row[2]) if bc_row[2] is not None else 0.0

    # Balance deposits count towards total ever invested
    if balance_gross_deposits > 0:
        realized["total_invested_ever_eur"] += balance_gross_deposits

    # fetchone() returns None if the inner query has zero rows (no prices loaded yet)
    if (row is None or row[0] is None) and balance_value == 0.0:
        return PortfolioSummary(
            total_value_eur=0.0,
            total_invested_eur=0.0,
            total_pnl_eur=0.0,
            total_pnl_pct=0.0,
            last_updated=None,
            **realized,
        )

    tx_value = float(row[0]) if row and row[0] is not None else 0.0
    tx_invested = float(row[1]) if row and row[1] is not None else 0.0
    total_value = tx_value + balance_value
    total_invested = tx_invested + balance_contrib
    pnl = total_value - total_invested
    pnl_pct = (pnl / total_invested * 100) if total_invested > 0 else 0.0

    # Period return using Modified Dietz (accounts for capital injections/withdrawals)
    period_start_value: Optional[float] = None
    period_return_eur: Optional[float] = None
    period_return_pct: Optional[float] = None
    if is_period and date_from:
        # When the period ends in the past, V_fin must be the historical value at
        # effective_date_to, not today's portfolio value (which inflates the return figure).
        if effective_date_to < date.today():
            v_fin = get_value_at_date(conn, effective_date_to, broker=broker, asset_type=asset_type)
        else:
            v_fin = total_value
        md = get_modified_dietz(conn, date_from, effective_date_to, v_fin, broker=broker, asset_type=asset_type)
        period_start_value = md["period_start_value_eur"]
        period_return_eur = md["period_return_eur"]
        period_return_pct = md["period_return_pct"]

    last_updated = row[3] if row is not None else None

    return PortfolioSummary(
        total_value_eur=total_value,
        total_invested_eur=total_invested,
        total_pnl_eur=pnl,
        total_pnl_pct=pnl_pct,
        last_updated=last_updated,
        period_start_value_eur=period_start_value,
        period_return_eur=period_return_eur,
        period_return_pct=period_return_pct,
        **realized,
    )


def _build_invested_step_series(
    conn: duckdb.DuckDBPyConnection,
    broker: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> tuple[list[date], list[float]]:
    """
    Return (dates, values) sorted ascending where each value is the remaining
    cost basis AFTER all transactions on that date, using the running AVCO method.

    "Invested" = cost of shares still held = total_buy_cost − (sold_shares × avg_cost_at_sell).
    This is consistent with get_realized_pnl and can never go negative.
    """
    asset_join = ""
    filters = ""
    params: list = []

    type_list = _parse_filter_list(asset_type)
    broker_list = _parse_filter_list(broker)
    if type_list:
        asset_join = "JOIN assets a ON a.id = t.asset_id"
        filters += " " + _in_clause("a.type", type_list, params)
    if broker_list:
        filters += " " + _in_clause("t.broker", broker_list, params)

    rows = conn.execute(f"""
        SELECT t.asset_id, t.type, t.shares, t.price_eur, t.date
        FROM transactions t
        {asset_join}
        WHERE 1=1 {filters}
        ORDER BY t.date, t.id
    """, params).fetchall()

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
    broker: Optional[str] = None,
    asset_type: Optional[str] = None,
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

    # Build broker/asset_type filter fragments (same pattern as get_holdings)
    type_list = _parse_filter_list(asset_type)
    broker_list = _parse_filter_list(broker)

    asset_join = ""
    broker_filter = ""
    type_filter = ""
    extra_params: list = []
    # SQL inner query: WHERE 1=1 {broker_filter} {type_filter} — broker params must come first
    if broker_list:
        broker_filter = _in_clause("t2.broker", broker_list, extra_params)
    if type_list:
        asset_join = "JOIN assets a ON a.id = t2.asset_id"
        type_filter = _in_clause("a.type", type_list, extra_params)

    # Filters for the outer transactions join (use t alias)
    outer_broker_filter = ""
    outer_type_filter = ""
    outer_extra_params: list = []
    if broker_list:
        outer_broker_filter = _in_clause("t.broker", broker_list, outer_extra_params)
    if type_list:
        placeholders = ','.join('?' * len(type_list))
        outer_type_filter = f"AND t.asset_id IN (SELECT id FROM assets WHERE type IN ({placeholders}))"
        outer_extra_params.extend(type_list)

    all_params = params + extra_params + outer_extra_params

    query = f"""
    WITH date_spine AS (
        SELECT DISTINCT date FROM prices
        WHERE 1=1 {date_filter}
    ),
    cumulative_holdings AS (
        SELECT
            t.asset_id,
            d.date AS price_date,
            SUM(CASE WHEN t.type='buy' AND t.date <= d.date THEN t.shares::DOUBLE
                     WHEN t.type='sell' AND t.date <= d.date THEN -t.shares::DOUBLE
                     ELSE 0.0 END) AS shares_held
        FROM date_spine d
        CROSS JOIN (
            SELECT DISTINCT t2.asset_id
            FROM transactions t2
            {asset_join}
            WHERE 1=1 {broker_filter} {type_filter}
        ) asset_ids
        JOIN transactions t ON t.asset_id = asset_ids.asset_id
        WHERE 1=1 {outer_broker_filter} {outer_type_filter}
        GROUP BY t.asset_id, d.date
        HAVING SUM(CASE WHEN t.type='buy' AND t.date <= d.date THEN t.shares::DOUBLE
                        WHEN t.type='sell' AND t.date <= d.date THEN -t.shares::DOUBLE
                        ELSE 0.0 END) > 0.000001
    ),
    prices_filled AS (
        SELECT
            ch.asset_id,
            ch.price_date,
            ch.shares_held,
            p.price_eur::DOUBLE AS price_eur
        FROM cumulative_holdings ch
        ASOF LEFT JOIN (
            SELECT asset_id, date, price_eur FROM prices ORDER BY asset_id, date
        ) p ON p.asset_id = ch.asset_id AND ch.price_date >= p.date
    )
    SELECT
        price_date AS date,
        SUM(shares_held * COALESCE(price_eur, 0.0)) AS value_eur
    FROM prices_filled
    WHERE price_eur IS NOT NULL
    GROUP BY price_date
    ORDER BY price_date
    """

    rows = conn.execute(query, all_params).fetchall()

    # Build invested step series (AVCO cost basis) and forward-fill onto chart dates
    step_dates, step_values = _build_invested_step_series(conn, broker=broker, asset_type=asset_type)

    def _invested_at(chart_date) -> Optional[float]:
        if not step_dates:
            return None
        d = chart_date if isinstance(chart_date, date) else chart_date.date()
        idx = bisect.bisect_right(step_dates, d) - 1
        return step_values[idx] if idx >= 0 else None

    # Add balance asset values if not filtered to non-balance types (and no broker filter)
    balance_by_date: dict[date, tuple[float, float]] = {}  # date → (value_eur, net_contrib_eur)
    if (not type_list or 'balance' in type_list) and not broker_list:
        balance_by_date = _build_balance_chart_series(conn, [row[0] for row in rows])

    chart = []
    for row in rows:
        chart_date = row[0]
        value_eur = float(row[1])
        invested_eur = _invested_at(chart_date)

        if balance_by_date:
            bal_value, bal_contrib = balance_by_date.get(chart_date, (0.0, 0.0))
            value_eur += bal_value
            if invested_eur is not None:
                invested_eur = invested_eur + bal_contrib
            elif bal_contrib > 0:
                invested_eur = bal_contrib

        chart.append(ChartPoint(date=chart_date, value_eur=value_eur, invested_eur=invested_eur))
    return chart


def _build_balance_chart_series(
    conn: duckdb.DuckDBPyConnection,
    chart_dates: list,
) -> dict:
    """
    For each date in chart_dates, compute:
    - balance_value: latest snapshot amount_eur per balance asset <= date, summed
    - balance_invested: cumulative net contributions (deposits - withdrawals) up to date

    Returns dict mapping date → (balance_value_eur, balance_net_contrib_eur).
    """
    if not chart_dates:
        return {}

    # Fetch all balance entries sorted ascending
    all_entries = conn.execute("""
        SELECT be.asset_id, be.type, be.amount_eur::DOUBLE, be.date
        FROM balance_entries be
        JOIN assets a ON a.id = be.asset_id
        WHERE a.type = 'balance'
        ORDER BY be.date, be.id
    """).fetchall()

    if not all_entries:
        return {}

    def _to_date(v) -> date:
        return v if isinstance(v, date) else v.date()

    # Separate snapshots and contributions into sorted lists
    snapshots: dict[int, list] = {}   # asset_id → [(date, amount)]
    contrib_dates: list = []          # [(date, delta_eur)]

    for asset_id, entry_type, amount_eur, entry_date in all_entries:
        entry_date = _to_date(entry_date)
        if entry_type == "snapshot":
            snapshots.setdefault(asset_id, []).append((entry_date, amount_eur))
        elif entry_type in ("deposit", "withdrawal"):
            delta = amount_eur if entry_type == "deposit" else -amount_eur
            contrib_dates.append((entry_date, delta))

    contrib_dates.sort(key=lambda x: x[0])

    result: dict[date, tuple[float, float]] = {}
    for chart_date in chart_dates:
        d = _to_date(chart_date)

        # Sum latest snapshot per asset up to d
        bal_value = 0.0
        for asset_id, snaps in snapshots.items():
            # snaps is sorted ascending by date
            val = None
            for snap_date, snap_amount in snaps:
                if snap_date <= d:
                    val = snap_amount
                else:
                    break
            if val is not None:
                bal_value += val

        # Sum all net contributions up to d
        bal_contrib = sum(delta for cd, delta in contrib_dates if cd <= d)

        result[d] = (bal_value, bal_contrib)

    return result
