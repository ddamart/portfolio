import logging
import os
import threading
import time
import duckdb

logger = logging.getLogger(__name__)

# Path to the DB file — set once by init_db(), read by every thread
_db_path: str = ""

# Each FastAPI worker thread gets its own DuckDB connection via threading.local().
# DuckDB supports multiple connections to the same file from the same process
# (one writer + many readers via MVCC). Sharing a single connection across
# threads is explicitly NOT safe per DuckDB docs.
_local = threading.local()

MARKETS_SEED = [
    # (mic, name, timezone, open_time, close_time, country)
    ("XETR", "Xetra (Frankfurt)", "Europe/Berlin", "09:00", "17:30", "DE"),
    ("XAMS", "Euronext Amsterdam", "Europe/Amsterdam", "09:00", "17:30", "NL"),
    ("XMAD", "Bolsa de Madrid", "Europe/Madrid", "09:00", "17:35", "ES"),
    ("XLON", "London Stock Exchange", "Europe/London", "08:00", "16:30", "GB"),
    ("XNYS", "New York Stock Exchange", "America/New_York", "09:30", "16:00", "US"),
    ("XNAS", "NASDAQ", "America/New_York", "09:30", "16:00", "US"),
    ("CNMV", "CNMV Fondos (Spain)", "Europe/Madrid", "00:00", "18:00", "ES"),
    ("XSTO", "Nasdaq Stockholm AB", "Europe/Stockholm", "09:00", "17:30", "SE"),
    ("XPAR", "Euronext Paris", "Europe/Paris", "09:00", "17:30", "FR"),
    ("XHEL", "Nasdaq Helsinki", "Europe/Helsinki", "10:00", "18:30", "FI"),
    ("XTKS", "Tokyo Stock Exchange", "Asia/Tokyo", "09:00", "15:30", "JP"),
    ("XTSE", "Toronto Stock Exchange", "America/Toronto", "09:30", "16:00", "CA"),
    ("XTSX", "TSX Venture Exchange", "America/Toronto", "09:30", "16:00", "CA"),
]


def get_db() -> duckdb.DuckDBPyConnection:
    """Return the calling thread's own DuckDB connection, creating it on first use."""
    if not _db_path:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    conn = getattr(_local, "conn", None)
    if conn is None:
        _local.conn = duckdb.connect(_db_path)
    return _local.conn


def _connect_with_retry(path: str, timeout: int = 15) -> duckdb.DuckDBPyConnection:
    deadline = time.monotonic() + timeout
    interval = 0.5
    while True:
        try:
            return duckdb.connect(path)
        except Exception as e:
            err = str(e)
            if ("being utilized by another process" not in err and "already open" not in err.lower()):
                raise
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Database file is still locked after {timeout}s. "
                    "Kill the previous server process and retry."
                ) from e
            time.sleep(interval)


def init_db(path: str) -> None:
    global _db_path
    if path != ":memory:":
        os.makedirs(os.path.dirname(path), exist_ok=True)
    _db_path = path

    # Bootstrap: apply schema and seed on a temporary connection.
    # Each thread will open its own connection via get_db() on first request.
    try:
        bootstrap = duckdb.connect(path)
    except Exception as e:
        err = str(e)
        wal = path + ".wal"
        if os.path.exists(wal) and ("WAL" in err or "InternalException" in err):
            logger.warning("DuckDB WAL replay failed — removing corrupt WAL and retrying")
            os.remove(wal)
            bootstrap = duckdb.connect(path)
        elif "being utilized by another process" in err or "already open" in err.lower():
            # The previous server process may still be releasing the lock.
            # Retry for up to 15 seconds before giving up.
            logger.warning("DuckDB file locked — waiting for previous instance to exit...")
            bootstrap = _connect_with_retry(path, timeout=15)
        else:
            raise
    _apply_schema(bootstrap)
    _seed_markets(bootstrap)
    bootstrap.close()


def close_db() -> None:
    """Close this thread's connection (called from lifespan on shutdown)."""
    global _db_path
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
    _db_path = ""


def _migrate_assets_add_balance(conn: duckdb.DuckDBPyConnection) -> None:
    """Recreate assets + FK-dependent tables to expand the type CHECK to include 'balance'.

    DuckDB does not implement ALTER TABLE DROP/ADD CONSTRAINT, so table recreation
    is the only way to change an existing CHECK constraint.
    """
    logger.info("Migrating assets table: adding 'balance' to type CHECK constraint")
    assets = conn.execute(
        "SELECT id, name, ticker, type, currency, market_id, image_url, manual_price, isin, created_at FROM assets"
    ).fetchall()
    transactions = conn.execute(
        "SELECT id, asset_id, type, broker, shares, price, price_eur, currency, "
        "commission, commission_currency, commission_eur, date, notes, created_at, updated_at "
        "FROM transactions"
    ).fetchall()
    prices = conn.execute(
        "SELECT asset_id, date, price, currency, price_eur FROM prices"
    ).fetchall()
    balance_entries = conn.execute(
        "SELECT id, asset_id, date, type, amount_eur, notes, created_at FROM balance_entries"
    ).fetchall()

    conn.execute("DROP TABLE IF EXISTS balance_entries")
    conn.execute("DROP TABLE IF EXISTS prices")
    conn.execute("DROP TABLE IF EXISTS transactions")
    conn.execute("DROP TABLE IF EXISTS assets")

    conn.execute("""
        CREATE TABLE assets (
            id           INTEGER PRIMARY KEY,
            name         VARCHAR NOT NULL,
            ticker       VARCHAR NOT NULL UNIQUE,
            type         VARCHAR NOT NULL CHECK (type IN ('etf', 'stock', 'fund', 'balance')),
            currency     VARCHAR NOT NULL DEFAULT 'EUR',
            market_id    INTEGER REFERENCES markets(id),
            image_url    VARCHAR,
            manual_price BOOLEAN NOT NULL DEFAULT false,
            isin         VARCHAR,
            created_at   TIMESTAMP DEFAULT current_timestamp
        )
    """)
    for row in assets:
        conn.execute("INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", list(row))

    conn.execute("""
        CREATE TABLE transactions (
            id                  INTEGER PRIMARY KEY,
            asset_id            INTEGER NOT NULL REFERENCES assets(id),
            type                VARCHAR NOT NULL CHECK (type IN ('buy', 'sell')),
            broker              VARCHAR NOT NULL CHECK (broker IN ('openbank', 'trade_republic', 'revolut', 'degiro')),
            shares              DECIMAL(18,8) NOT NULL,
            price               DECIMAL(18,6) NOT NULL,
            price_eur           DECIMAL(18,6) NOT NULL,
            currency            VARCHAR(3) NOT NULL DEFAULT 'EUR',
            commission          DECIMAL(10,4) NOT NULL DEFAULT 0,
            commission_currency VARCHAR(3),
            commission_eur      DECIMAL(10,4) NOT NULL DEFAULT 0,
            date                DATE NOT NULL,
            notes               VARCHAR,
            created_at          TIMESTAMP DEFAULT current_timestamp,
            updated_at          TIMESTAMP DEFAULT current_timestamp
        )
    """)
    for row in transactions:
        conn.execute(
            "INSERT INTO transactions (id, asset_id, type, broker, shares, price, price_eur, currency, "
            "commission, commission_currency, commission_eur, date, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            list(row),
        )

    conn.execute("""
        CREATE TABLE prices (
            asset_id  INTEGER NOT NULL REFERENCES assets(id),
            date      DATE NOT NULL,
            price     DECIMAL(18,6) NOT NULL,
            currency  VARCHAR(3) NOT NULL,
            price_eur DECIMAL(18,6) NOT NULL,
            PRIMARY KEY (asset_id, date)
        )
    """)
    for row in prices:
        conn.execute("INSERT INTO prices VALUES (?, ?, ?, ?, ?)", list(row))

    conn.execute("""
        CREATE TABLE balance_entries (
            id         INTEGER PRIMARY KEY,
            asset_id   INTEGER NOT NULL REFERENCES assets(id),
            date       DATE NOT NULL,
            type       VARCHAR NOT NULL CHECK (type IN ('deposit', 'withdrawal', 'snapshot')),
            amount_eur DECIMAL(18,2) NOT NULL,
            notes      VARCHAR,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
    """)
    for row in balance_entries:
        conn.execute("INSERT INTO balance_entries VALUES (?, ?, ?, ?, ?, ?, ?)", list(row))

    logger.info("Migration complete: %d assets, %d transactions, %d prices, %d balance_entries restored",
                len(assets), len(transactions), len(prices), len(balance_entries))


def _apply_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS markets (
            id         INTEGER PRIMARY KEY,
            mic        VARCHAR(6) NOT NULL UNIQUE,
            name       VARCHAR NOT NULL,
            timezone   VARCHAR NOT NULL,
            open_time  TIME NOT NULL,
            close_time TIME NOT NULL,
            country    VARCHAR(2) NOT NULL
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS markets_id_seq START 1
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id           INTEGER PRIMARY KEY,
            name         VARCHAR NOT NULL,
            ticker       VARCHAR NOT NULL UNIQUE,
            type         VARCHAR NOT NULL CHECK (type IN ('etf', 'stock', 'fund', 'balance')),
            currency     VARCHAR NOT NULL DEFAULT 'EUR',
            market_id    INTEGER REFERENCES markets(id),
            image_url    VARCHAR,
            manual_price BOOLEAN NOT NULL DEFAULT false,
            isin         VARCHAR,
            created_at   TIMESTAMP DEFAULT current_timestamp
        )
    """)

    # Migration: add isin column to existing databases that predate this column
    has_isin = conn.execute("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name = 'assets' AND column_name = 'isin'
    """).fetchone()[0]
    if not has_isin:
        conn.execute("ALTER TABLE assets ADD COLUMN isin VARCHAR")

    # Migration: add 'balance' to the allowed asset types CHECK constraint.
    # DuckDB does not support ALTER TABLE DROP/ADD CONSTRAINT on existing tables,
    # so the only approach is to recreate the table and all FK-dependent children.
    has_balance_type = conn.execute("""
        SELECT COUNT(*) FROM information_schema.check_constraints cc
        JOIN information_schema.table_constraints tc
          ON tc.constraint_name = cc.constraint_name
         AND tc.table_schema    = cc.constraint_schema
        WHERE tc.table_name = 'assets'
          AND tc.constraint_type = 'CHECK'
          AND cc.check_clause ILIKE '%balance%'
    """).fetchone()[0]
    if not has_balance_type:
        _migrate_assets_add_balance(conn)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS assets_id_seq START 1
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id                  INTEGER PRIMARY KEY,
            asset_id            INTEGER NOT NULL REFERENCES assets(id),
            type                VARCHAR NOT NULL CHECK (type IN ('buy', 'sell')),
            broker              VARCHAR NOT NULL CHECK (broker IN ('openbank', 'trade_republic', 'revolut', 'degiro')),
            shares              DECIMAL(18,8) NOT NULL,
            price               DECIMAL(18,6) NOT NULL,
            price_eur           DECIMAL(18,6) NOT NULL,
            currency            VARCHAR(3) NOT NULL DEFAULT 'EUR',
            commission          DECIMAL(10,4) NOT NULL DEFAULT 0,
            commission_currency VARCHAR(3),
            commission_eur      DECIMAL(10,4) NOT NULL DEFAULT 0,
            date                DATE NOT NULL,
            notes               VARCHAR,
            created_at          TIMESTAMP DEFAULT current_timestamp,
            updated_at          TIMESTAMP DEFAULT current_timestamp
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS transactions_id_seq START 1
    """)

    # Migration: add commission_currency for brokers (e.g. Degiro) that charge in EUR
    # even when the asset is priced in another currency
    has_comm_ccy = conn.execute("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name = 'transactions' AND column_name = 'commission_currency'
    """).fetchone()[0]
    if not has_comm_ccy:
        conn.execute("ALTER TABLE transactions ADD COLUMN commission_currency VARCHAR(3)")
        conn.execute("UPDATE transactions SET commission_currency = currency WHERE commission_currency IS NULL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            asset_id  INTEGER NOT NULL REFERENCES assets(id),
            date      DATE NOT NULL,
            price     DECIMAL(18,6) NOT NULL,
            currency  VARCHAR(3) NOT NULL,
            price_eur DECIMAL(18,6) NOT NULL,
            PRIMARY KEY (asset_id, date)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS fx_rates (
            date      DATE NOT NULL,
            from_ccy  VARCHAR(3) NOT NULL,
            to_ccy    VARCHAR(3) NOT NULL,
            rate      DECIMAL(18,8) NOT NULL,
            PRIMARY KEY (date, from_ccy, to_ccy)
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS balance_entries_id_seq START 1
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS balance_entries (
            id         INTEGER PRIMARY KEY,
            asset_id   INTEGER NOT NULL REFERENCES assets(id),
            date       DATE NOT NULL,
            type       VARCHAR NOT NULL CHECK (type IN ('deposit', 'withdrawal', 'snapshot')),
            amount_eur DECIMAL(18,2) NOT NULL,
            notes      VARCHAR,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS refresh_log (
            id         INTEGER PRIMARY KEY,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            assets_updated INTEGER,
            status     VARCHAR NOT NULL DEFAULT 'running'
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS refresh_log_id_seq START 1
    """)


def _seed_markets(conn: duckdb.DuckDBPyConnection) -> None:
    # Insert only markets not already present so new entries added to MARKETS_SEED
    # are picked up by existing databases on next startup.
    existing = {row[0] for row in conn.execute("SELECT mic FROM markets").fetchall()}
    next_id = (conn.execute("SELECT COALESCE(MAX(id), 0) FROM markets").fetchone()[0] or 0) + 1
    for mic, name, tz, open_t, close_t, country in MARKETS_SEED:
        if mic not in existing:
            conn.execute(
                "INSERT INTO markets VALUES (?, ?, ?, ?, ?, ?, ?)",
                [next_id, mic, name, tz, open_t, close_t, country],
            )
            next_id += 1
