from datetime import date
import duckdb


def get_rate_to_eur(conn: duckdb.DuckDBPyConnection, currency: str, on_date: date) -> float:
    """Return the exchange rate from `currency` to EUR on or before `on_date`.
    Returns 1.0 for EUR. Raises ValueError if no rate found."""
    ccy = currency.upper()
    if ccy == "EUR":
        return 1.0
    # GBX = pence sterling = 1/100 GBP
    if ccy == "GBX":
        return get_rate_to_eur(conn, "GBP", on_date) / 100

    row = conn.execute(
        """
        SELECT rate FROM fx_rates
        WHERE from_ccy = ? AND to_ccy = 'EUR' AND date <= ?
        ORDER BY date DESC LIMIT 1
        """,
        [currency.upper(), on_date],
    ).fetchone()

    if row is None:
        raise ValueError(
            f"No FX rate found for {ccy}→EUR on or before {on_date}. "
            "Run a price refresh first."
        )
    return float(row[0])


def convert_to_eur(amount: float, currency: str, conn: duckdb.DuckDBPyConnection, on_date: date) -> float:
    rate = get_rate_to_eur(conn, currency, on_date)
    return amount * rate
