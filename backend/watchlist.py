from backend.config import get_settings
from backend.database import get_connection, init_db


def seed_default_watchlist() -> None:
    init_db()
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) AS total FROM watchlist").fetchone()["total"]
        if existing:
            return
        for symbol in get_settings().watchlist_symbols:
            conn.execute(
                "INSERT OR IGNORE INTO watchlist(symbol, name) VALUES (?, ?)",
                (symbol, symbol),
            )


def list_watchlist() -> list[dict]:
    seed_default_watchlist()
    with get_connection() as conn:
        rows = conn.execute("SELECT symbol, name, created_at FROM watchlist ORDER BY symbol").fetchall()
    return [dict(row) for row in rows]


def add_to_watchlist(symbol: str, name: str | None = None) -> None:
    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise ValueError("Symbol cannot be empty.")
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO watchlist(symbol, name) VALUES (?, ?)",
            (clean_symbol, name or clean_symbol),
        )


def remove_from_watchlist(symbol: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.strip().upper(),))


def get_app_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_app_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings(key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
