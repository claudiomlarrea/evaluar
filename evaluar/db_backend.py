"""Conexión SQLite (local) o PostgreSQL (producción vía DATABASE_URL)."""

from __future__ import annotations

import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "evaluar.db"

# Neon puede tardar en despertar; reintentamos antes de fallar.
CONNECT_TIMEOUT = 15
CONNECT_RETRY_DELAYS = (0.0, 0.8, 1.6, 3.0)
QUERY_RETRY_ATTEMPTS = 3


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


def _postgres_connection_errors() -> tuple[type[BaseException], ...]:
    import psycopg2

    return (psycopg2.InterfaceError, psycopg2.OperationalError)


def _open_postgres_connection() -> Any:
    import psycopg2

    url = _get_database_url() or ""
    return psycopg2.connect(url, connect_timeout=CONNECT_TIMEOUT)


def _connect_postgres_with_retry() -> Any:
    """Conexión nueva por operación, con reintentos (Neon cold start / red)."""
    last_exc: Exception | None = None
    for delay in CONNECT_RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        conn = None
        try:
            conn = _open_postgres_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            return conn
        except _postgres_connection_errors() as exc:
            last_exc = exc
            _safe_postgres_close(conn)
        except Exception as exc:
            last_exc = exc
            _safe_postgres_close(conn)
    if last_exc:
        raise last_exc
    raise RuntimeError("No se pudo conectar a PostgreSQL.")


def _safe_postgres_rollback(conn: Any) -> None:
    try:
        if conn is not None and getattr(conn, "closed", 1) == 0:
            conn.rollback()
    except Exception:
        pass


def _safe_postgres_close(conn: Any) -> None:
    try:
        if conn is not None and getattr(conn, "closed", 1) == 0:
            conn.close()
    except Exception:
        pass


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

    def _replace_connection(self) -> None:
        _safe_postgres_close(self._conn)
        self._conn = _connect_postgres_with_retry()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _PostgresCursor:
        from psycopg2.extras import RealDictCursor

        last_exc: Exception | None = None
        for attempt in range(QUERY_RETRY_ATTEMPTS):
            try:
                cursor = self._conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute(_adapt_sql(sql), params)
                return _PostgresCursor(cursor)
            except _postgres_connection_errors() as exc:
                last_exc = exc
                if attempt < QUERY_RETRY_ATTEMPTS - 1:
                    self._replace_connection()
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("No se pudo ejecutar la consulta.")

    def executescript(self, script: str) -> None:
        last_exc: Exception | None = None
        for attempt in range(QUERY_RETRY_ATTEMPTS):
            try:
                cursor = self._conn.cursor()
                for statement in script.split(";"):
                    chunk = statement.strip()
                    if chunk:
                        cursor.execute(_adapt_sql(chunk))
                cursor.close()
                return
            except _postgres_connection_errors() as exc:
                last_exc = exc
                if attempt < QUERY_RETRY_ATTEMPTS - 1:
                    self._replace_connection()
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("No se pudo ejecutar el script SQL.")


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
        conn = _connect_postgres_with_retry()
        wrapper = _PostgresConnection(conn)
        try:
            yield wrapper
            conn.commit()
        except Exception:
            _safe_postgres_rollback(conn)
            raise
        finally:
            _safe_postgres_close(conn)
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
