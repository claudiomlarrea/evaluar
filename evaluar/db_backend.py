"""Conexión SQLite (local) o PostgreSQL (producción vía DATABASE_URL)."""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "evaluar.db"

# Neon puede tardar en despertar; reintentamos solo si falla el primer intento.
CONNECT_TIMEOUT = 12
CONNECT_RETRY_DELAYS = (0.0, 0.5, 1.5)
QUERY_RETRY_ATTEMPTS = 2
POOL_MAX_CONN = 6
# Nunca bloquear el script de Streamlit esperando el pool (síntoma: "... CONNECTING").
POOL_GET_TIMEOUT = 2.0
STATEMENT_TIMEOUT_MS = 8000

_pool_lock = threading.Lock()
_pg_pool: Any | None = None


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
    return psycopg2.connect(
        url,
        connect_timeout=CONNECT_TIMEOUT,
        options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
    )


def _connect_postgres_with_retry() -> Any:
    """Conexión nueva, con reintentos (Neon cold start / red)."""
    last_exc: Exception | None = None
    for delay in CONNECT_RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        conn = None
        try:
            conn = _open_postgres_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            _safe_postgres_rollback(conn)
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


def _postgres_alive(conn: Any) -> bool:
    if conn is None or getattr(conn, "closed", 1) != 0:
        return False
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
        _safe_postgres_rollback(conn)
        return True
    except Exception:
        return False


class _TimeoutConnectionPool:
    """Pool LIFO con timeout: si no hay cupo, el caller abre una conexión efímera.

    psycopg2.ThreadedConnectionPool.getconn() espera *sin límite* cuando el pool
    está agotado o hay fugas; eso congela Streamlit en "... CONNECTING".
    """

    def __init__(self, dsn: str, maxconn: int = POOL_MAX_CONN) -> None:
        import queue

        self._dsn = dsn
        self._maxconn = maxconn
        self._queue: queue.LifoQueue = queue.LifoQueue(maxconn)
        self._created = 0
        self._lock = threading.Lock()

    def getconn(self, timeout: float = POOL_GET_TIMEOUT) -> Any:
        import queue

        try:
            return self._queue.get_nowait()
        except queue.Empty:
            pass

        create_new = False
        with self._lock:
            if self._created < self._maxconn:
                self._created += 1
                create_new = True
        if create_new:
            try:
                # No retener el lock durante TCP+SSL (Neon cold start).
                return _open_postgres_connection()
            except Exception:
                with self._lock:
                    self._created = max(0, self._created - 1)
                raise

        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("Postgres pool exhausted") from exc

    def putconn(self, conn: Any, close: bool = False) -> None:
        if conn is None:
            return
        should_close = close or getattr(conn, "closed", 1) != 0
        if should_close:
            _safe_postgres_close(conn)
            with self._lock:
                self._created = max(0, self._created - 1)
            return
        try:
            self._queue.put_nowait(conn)
        except Exception:
            _safe_postgres_close(conn)
            with self._lock:
                self._created = max(0, self._created - 1)


def _get_pg_pool() -> _TimeoutConnectionPool:
    """Pool de conexiones por proceso (evita TCP+SSL en cada click de Streamlit)."""
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    with _pool_lock:
        if _pg_pool is not None:
            return _pg_pool
        url = _get_database_url() or ""
        _pg_pool = _TimeoutConnectionPool(url, maxconn=POOL_MAX_CONN)
        return _pg_pool


def _discard_pool_connection(conn: Any) -> None:
    """Cierra y saca del pool una conexión muerta (sin filtrar el cupo)."""
    try:
        _get_pg_pool().putconn(conn, close=True)
    except Exception:
        _safe_postgres_close(conn)


def _borrow_postgres_connection() -> tuple[Any, bool]:
    """Devuelve (conn, from_pool). Si el pool no responde a tiempo, conexión efímera."""
    try:
        pg_pool = _get_pg_pool()
        conn = pg_pool.getconn(timeout=POOL_GET_TIMEOUT)
        if _postgres_alive(conn):
            return conn, True
        _discard_pool_connection(conn)
        conn = pg_pool.getconn(timeout=POOL_GET_TIMEOUT)
        if _postgres_alive(conn):
            return conn, True
        _discard_pool_connection(conn)
    except Exception:
        pass
    return _connect_postgres_with_retry(), False


def _return_postgres_connection(conn: Any, from_pool: bool) -> None:
    if not from_pool:
        _safe_postgres_close(conn)
        return
    try:
        pg_pool = _get_pg_pool()
        closed = getattr(conn, "closed", 1) != 0
        pg_pool.putconn(conn, close=closed)
    except Exception:
        _safe_postgres_close(conn)


class _PostgresCursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def fetchone(self) -> dict[str, Any] | None:
        return row_to_dict(self._cursor.fetchone())

    def fetchall(self) -> list[dict[str, Any]]:
        return [row_to_dict(row) for row in self._cursor.fetchall()]


class _PostgresConnection:
    def __init__(self, conn: Any, from_pool: bool = False) -> None:
        self._conn = conn
        self.from_pool = from_pool

    def _replace_connection(self) -> None:
        if self.from_pool:
            try:
                _get_pg_pool().putconn(self._conn, close=True)
            except Exception:
                _safe_postgres_close(self._conn)
            self.from_pool = False
        else:
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
        conn, from_pool = _borrow_postgres_connection()
        wrapper = _PostgresConnection(conn, from_pool=from_pool)
        failed = False
        try:
            yield wrapper
            wrapper._conn.commit()
        except Exception:
            failed = True
            _safe_postgres_rollback(wrapper._conn)
            raise
        finally:
            if failed and wrapper.from_pool:
                try:
                    _get_pg_pool().putconn(wrapper._conn, close=True)
                except Exception:
                    _safe_postgres_close(wrapper._conn)
            else:
                _return_postgres_connection(wrapper._conn, wrapper.from_pool)
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
