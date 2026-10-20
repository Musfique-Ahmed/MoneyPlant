"""Connector protocol and shared types.

A :class:`Connector` is a small interface that returns a stream of
raw rows from an external source. The :class:`SyncService` then runs
the user-confirmed column mapping through the engine's parser
(:func:`app.services.ingestion.csv.parse_rows` for CSV, the XLSX
reader for Excel), validates and de-duplicates.

The protocol is intentionally minimal so adding new sources later
(dropbox, google sheets, csv-URL-with-allowlist) only requires writing
one class.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol, runtime_checkable


@dataclass(frozen=True)
class RawRow:
    """A single untyped row from a connector, in source-keyed shape."""

    data: dict[str, Any]
    # A source-provided identifier (line number, row id, etc.). Optional:
    # the service uses the natural-key hash if this is missing.
    cursor: str | None = None


@dataclass
class ConnectorReadResult:
    """The shape returned by :meth:`Connector.read_rows`.

    ``rows`` is the live stream of untyped records. ``content_sha256`` is
    a fingerprint of the underlying source for "file replaced or appended"
    detection (SQL sources use ``watermark_after`` instead).
    """

    rows: Iterator[RawRow]
    rows_read: int = 0
    content_sha256: str | None = None
    watermark_after: str | None = None
    headers: list[str] = field(default_factory=list)
    sample_rows: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Connector(Protocol):
    """Read a stream of rows from one source. The :class:`SyncService`
    wraps this; this class itself must not touch the local DB.
    """

    def read_rows(self) -> ConnectorReadResult: ...


def row_natural_key(
    data: dict[str, Any],
    *,
    tx_keys: tuple[str, ...] = (
        "tx_date", "amount", "direction", "currency",
        "description", "category",
    ),
) -> str:
    """Stable, source-side natural key for de-duplication.

    Used as part of the row fingerprint we compare against already
    imported rows. The shape of the canonical key is intentional: it
    ignores whitespace and case in the textual fields, and treats
    amounts as plain strings so a Decimal representation in one row and
    a string in another compare equal.

    The connector sends us mapped rows (already resolved to canonical
    field names like ``tx_date``, ``amount``, ``direction``). The
    service hashes the json-stable canonical tuple.
    """
    parts: list[str] = []
    for k in tx_keys:
        v = data.get(k)
        if v is None:
            parts.append("")
            continue
        if isinstance(v, str):
            parts.append(v.strip().lower())
        else:
            parts.append(str(v).strip())
    return "||".join(parts)


def row_hash(natural_key: str) -> str:
    """Stable hash for natural-key de-duplication."""
    return hashlib.sha256(natural_key.encode("utf-8")).hexdigest()


def row_dedup_payload(canonical: dict[str, Any]) -> str:
    """Serialise a canonical-row dict to a deterministic JSON string.

    Used in two places:
    1. The natural-key hash we compare against existing rows.
    2. The ``source_row_hash`` we store on each persisted Transaction.
    """
    return json.dumps(canonical, sort_keys=True, default=str, separators=(",", ":"))


__all__ = [
    "Connector",
    "RawRow",
    "ConnectorReadResult",
    "row_natural_key",
    "row_hash",
    "row_dedup_payload",
]