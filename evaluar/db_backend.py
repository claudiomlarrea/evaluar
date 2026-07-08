"""Conexión SQLite (local) o PostgreSQL (producción vía DATABASE_URL)."""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "evaluar.db"


def _get_database_url() -> str | None:
    url = os.environ.get("DATABASE_URL")
    if url:
        return _normalize_postgres_url(url)
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            if "DATABASE_URL" in st.secrets:
                return _normalize_postgres_url(str(st.secrets["DATABASE_URL"]))
            connections = st.secrets.get("connections")
            if connections and "postgresql" in connections:
                pg = connections["postgresql"]
                if isinstance(pg, dict) and pg.get("url"):
                    return _normalize_postgres_url(str(pg["url"]))
    except Exception:
        pass
    return None


def _normalize_postgres_url(url: str) -> str:
    cleaned = url.strip().strip('"').strip("'")
    if cleaned.startswith("postgres://"):
        cleaned = cleaned.replace("postgres://", "postgresql://", 1)
    # Neon a veces incluye channel_binding y rompe psycopg2 en algunos entornos.
    cleaned = re.sub(r"([?&])channel_binding=[^&]*&?", r"\1", cleaned)
    cleaned = cleaned.rstrip("&").rstrip("?")
    if cleaned.startswith("postgresql://") and "sslmode=" not in cleaned:
        if any(host in cleaned for host in ("neon.tech", "supabase.co", "railway.app")):
            cleaned = f"{cleaned}{'&' if '?' in cleaned else '?'}sslmode=require"
    return cleaned


def using_postgres() -> bool:
    url = _get_database_url()
    return bool(url and url.startswith(("postgres://", "postgresql://")))


def database_label() -> str:
    return "PostgreSQL" if using_postgres() else "SQLite"


def is_ephemeral_storage() -> bool:
    """SQLite en Streamlit Cloud se borra en cada redeploy."""
    if using_postgres():
        return False
    try:
        import streamlit as st

        host = ""
        if hasattr(st, "context") and hasattr(st.context, "headers"):
            headers = st.context.headers
            host = (headers.get("Host") or headers.get("host") or "").lower()
        return "streamlit.app" in host
    except Exception:
        return False


def _adapt_sql(sql: str) -> str:
    if using_postgres():
        return sql.replace("?", "%s")
    return sql


def first_value(row: Any) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


class _PostgresCursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def fetchone(self) -> dict[str, Any] | None:
        return row_to_dict(self._cursor.fetchone())

    def fetchall(self) -> list[dict[str, Any]]:
        return [row_to_dict(row) for row in self._cursor.fetchall()]


class _PostgresConnection:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _PostgresCursor:
        from psycopg2.extras import RealDictCursor

        cursor = self._conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(_adapt_sql(sql), params)
        return _PostgresCursor(cursor)

    def executescript(self, script: str) -> None:
        cursor = self._conn.cursor()
        for statement in script.split(";"):
            chunk = statement.strip()
            if chunk:
                cursor.execute(_adapt_sql(chunk))
        cursor.close()


class _SQLiteConnection:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def executescript(self, script: str) -> None:
        self._conn.executescript(script)


@contextmanager
def get_connection() -> Iterator[_SQLiteConnection | _PostgresConnection]:
    if using_postgres():
        import psycopg2

        url = _get_database_url() or ""
        conn = psycopg2.connect(url, connect_timeout=8)
        wrapper = _PostgresConnection(conn)
        try:
            yield wrapper
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        wrapper = _SQLiteConnection(conn)
        try:
            yield wrapper
            conn.commit()
        finally:
            conn.close()
