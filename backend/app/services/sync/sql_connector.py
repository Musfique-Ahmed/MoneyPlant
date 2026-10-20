"""SQL-source connector.

Reads rows from a single table or view in an external SQL database
(SQLite or Postgres). The connection URL is never stored on the
:class:`DataSource` — only an env-var name. The connector resolves
the env-var at read time and **does not** log the URL.

Security:

- A :class:`sqlalchemy.engine.Engine` is built with a server-side
  ``statement_timeout`` (Postgres) or ``connect_args={"timeout": N}``
  (SQLite) and a hard ``row_limit`` enforced server-side via a
  parameterised SELECT statement.
- The query is the ONLY thing this module runs. No free-form SQL
  comes from the user. ``table`` is matched against a strict
  identifier regex and combined with the configured ``incremental_key``
  using parameterised bind values for the watermark.
- Watermarks are stored on the :class:`DataSource` and used as a
  bound parameter (``WHERE incremental_key > :watermark``). The
  ``incremental_key`` column itself is matched against a strict regex.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.services.sync.connectors import (
    ConnectorReadResult,
    RawRow,
)


# Strict identifier regex. Lets common Postgres / SQLite identifiers through
# and blocks SQL-injection vectors (spaces, semicolons, comments).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")


class SqlSourceError(ValueError):
    """Raised when a SQL-source config is invalid or the source query fails."""


def _validate_identifier(value: str, kind: str) -> str:
    if not value or not _IDENT_RE.match(value):
        raise SqlSourceError(f"invalid_{kind}_identifier:{value}")
    return value


def _make_engine(url: str, *, statement_timeout_seconds: int) -> Engine:
    """Build a SQLAlchemy engine for the given URL.

    SQLite gets a small connect timeout (because SQLite's lock_wait_time
    is what bounds statement execution). Postgres gets a server-side
    ``statement_timeout`` set via a connection event handler.
    """
    if url.startswith("sqlite"):
        # Accept sqlite:///./path/to.db, sqlite:////abs/path.db or even
        # ``sqlite://path``. Pass it through directly to SQLAlchemy.
        engine = sa.create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False, "timeout": max(1, statement_timeout_seconds)},
        )
        return engine
    if url.startswith(("postgresql", "postgres")):
        engine = sa.create_engine(url, future=True)
        sa.event.listen(
            engine,
            "connect",
            _postgres_statement_timeout(statement_timeout_seconds),
        )
        return engine
    # Anything else (mysql, mssql, oracle, ...) — we don't speak it. The
    # service translates the failure into a public error code without
    # echoing the URL.
    raise SqlSourceError("unsupported_db_url_scheme")
    raise SqlSourceError(f"unsupported_db_url_scheme:{url[:10]}…")


def _postgres_statement_timeout(seconds: int) -> Any:
    """Hook that emits a per-connection ``SET statement_timeout`` on Postgres."""

    def hook(dbapi_connection: Any, connection_record: Any) -> None:  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET statement_timeout = {int(seconds) * 1000}")
        finally:
            cursor.close()

    return hook


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


class SqlConnector:
    """Read new rows from a single table/view.

    Args:
        url: SQLAlchemy URL. Comes from the env var referenced by
            ``DataSource.secret_ref``. Never logged.
        table: fully-qualified table name (``schema.table`` or ``table``).
        incremental_key: column name to filter by. Must be a simple
            identifier. The connector issues
            ``SELECT * FROM table WHERE incremental_key > :watermark
            ORDER BY incremental_key ASC LIMIT :row_limit``.
        row_limit: enforced server-side via a parameterised LIMIT.
        statement_timeout_seconds: bounded for every connection.
    """

    def __init__(
        self,
        *,
        url: str,
        table: str,
        schema: str | None = None,
        incremental_key: str | None,
        row_limit: int,
        statement_timeout_seconds: int,
        previous_watermark: str | None,
    ) -> None:
        if not url:
            raise SqlSourceError("url_is_empty")
        self._table = _validate_identifier(table, "table")
        # Validate schema identifier too when present; pass-through to
        # ``inspector.get_columns`` so we can reflect the actual columns.
        self._schema = _validate_identifier(schema, "schema") if schema else None
        if incremental_key is not None:
            self._incremental_key = _validate_identifier(incremental_key, "incremental_key")
        else:
            self._incremental_key = None
        self._row_limit = max(1, min(int(row_limit), 1_000_000))
        self._statement_timeout_seconds = max(1, min(int(statement_timeout_seconds), 300))
        self._url = url
        self._engine: Engine | None = None
        self._previous_watermark = previous_watermark

    def _ensure_engine(self) -> Engine:
        if self._engine is None:
            try:
                self._engine = _make_engine(
                    self._url,
                    statement_timeout_seconds=self._statement_timeout_seconds,
                )
            except (ImportError, ModuleNotFoundError) as exc:
                # The DB driver (psycopg, pymysql, …) is not installed in
                # this Python. Surface a safe code, never the URL.
                raise SqlSourceError("db_driver_not_installed") from exc
            except sa.exc.ArgumentError as exc:
                raise SqlSourceError("invalid_db_url") from exc
        return self._engine

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def read_rows(self) -> ConnectorReadResult:
        """Read up to ``row_limit`` rows newer than the previous watermark.

        When ``incremental_key`` is None, returns an empty result (we never
        re-import the whole table on every sync).
        """
        if self._incremental_key is None:
            return ConnectorReadResult(
                rows=iter(()),
                rows_read=0,
                watermark_after=self._previous_watermark,
                headers=[],
                sample_rows=[],
                metadata={"skipped": "no_incremental_key"},
            )

        engine = self._ensure_engine()

        # Reflect the real column list for the target table. Using
        # ``sa.select(table_obj)`` with a bare ``sa.table()`` would emit an
        # empty column list, so we introspect the live table instead. This is
        # SELECT-only metadata access; it never executes user SQL.
        table_name_only = self._table.split(".")[-1]
        inspector = sa.inspect(engine)
        try:
            columns = inspector.get_columns(table_name_only, schema=self._schema)
        except sa.exc.NoSuchTableError as exc:
            raise SqlSourceError("table_not_found") from exc
        except sa.exc.SQLAlchemyError as exc:
            raise SqlSourceError(f"inspect_failed:{exc.__class__.__name__}") from exc
        if not columns:
            raise SqlSourceError("table_has_no_columns")

        col_names = [c["name"] for c in columns]
        table_obj = sa.table(table_name_only, *(sa.column(n) for n in col_names))

        stmt = sa.select(table_obj).order_by(sa.column(self._incremental_key).asc()).limit(self._row_limit)
        params: dict[str, Any] = {}
        if self._previous_watermark is not None:
            stmt = stmt.where(sa.column(self._incremental_key) > sa.bindparam("watermark"))
            params["watermark"] = self._coerce_watermark(self._previous_watermark)

        with engine.connect() as conn:
            try:
                result = conn.execute(stmt, params)
                columns_out: list[str] = list(result.keys())
                rows = result.fetchall()
            except (ImportError, ModuleNotFoundError) as exc:
                raise SqlSourceError("db_driver_not_installed") from exc
            except sa.exc.SQLAlchemyError as exc:
                # Deliberately NOT including the underlying message: a driver
                # error can echo the connection string (with the password).
                raise SqlSourceError(f"query_failed:{exc.__class__.__name__}") from exc

        last_watermark = self._previous_watermark
        headers: list[str] = list(columns_out)
        sample_strings: list[str] = [
            str(dict(zip(columns_out, row))) for row in rows[:5]
        ]

        def iterate() -> Any:
            nonlocal last_watermark
            for row in rows:
                payload = {}
                for col, value in zip(columns_out, row):
                    payload[col] = self._serialise_value(value)
                yield RawRow(
                    data=payload,
                    cursor=str(payload.get(self._incremental_key, "")),
                )
                new_wm = payload.get(self._incremental_key)
                if new_wm is not None:
                    last_watermark = str(new_wm)

        return ConnectorReadResult(
            rows=iterate(),
            rows_read=len(rows),
            watermark_after=last_watermark,
            headers=headers,
            sample_rows=sample_strings,
            metadata={
                "table": self._table,
                "schema": self._schema,
                "incremental_key": self._incremental_key,
                "row_limit": self._row_limit,
                "statement_timeout_seconds": self._statement_timeout_seconds,
                "read_at": datetime.utcnow().isoformat() + "Z",
            },
        )

    @staticmethod
    def _coerce_watermark(value: str) -> Any:
        """Best-effort coercion so that the bind parameter has the right type."""
        # ISO date / datetime?
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        # Integer id?
        try:
            return int(value)
        except ValueError:
            pass
        # Fall back to raw string (the SQL side will cast as needed).
        return value

    @staticmethod
    def _serialise_value(v: Any) -> Any:
        # Decimal: keep Decimal so the parser can apply currency rounding.
        if isinstance(v, Decimal):
            return str(v)
        # datetime/date: ISO string for canonical hashing.
        if hasattr(v, "isoformat"):
            return v.isoformat()
        # bytes: short hex preview (raw bytes never reach MoneyCell).
        if isinstance(v, (bytes, bytearray)):
            return v.hex()
        return v


__all__ = ["SqlConnector", "SqlSourceError", "_validate_identifier"]