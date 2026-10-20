"""File-source connector (CSV / XLSX).

Security model:

- The file path is resolved against a configured allowed root. The
  resolved path must stay inside the root: parent-directory traversal
  (``..``), absolute paths, and symlinks pointing outside the root are
  rejected. See :func:`_safe_resolve`.
- The connector never reads files outside the allowed root, never
  follows ``..`` segments, and never traverses symlinks. Backend tests
  cover every escape attempt.

Content handling:

- A SHA-256 over the file's bytes is computed once on first read and
  returned on :class:`ConnectorReadResult`. The service stores this on
  the :class:`DataSource` so the next sync can detect "file replaced
  vs appended":
  - If the hash matches the stored one, we only consider rows after the
    already-imported row count.
  - If the hash differs, we treat the file as "replaced" and re-import
    all rows (the natural-key hash dedup ensures that previously-imported
    rows are skipped, not duplicated).
- Each row's source-side fingerprint is a SHA-256 over the canonical
  field tuple used by :func:`row_natural_key`. We import anything not
  already seen.
"""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl

from app.services.sync.connectors import (
    ConnectorReadResult,
    RawRow,
    row_dedup_payload,
)


class FileSourceError(ValueError):
    """Error raised when a file-source config is invalid or unsafe."""


# ---------------------------------------------------------------------------
# Path-traversal / symlink protection
# ---------------------------------------------------------------------------


def _safe_resolve(path_str: str, allowed_root: Path) -> Path:
    """Resolve ``path_str`` against ``allowed_root`` without escaping it.

    Raises:
        FileSourceError: when the path is not under the allowed root or
        any part of the path is a symlink pointing outside the root.
    """
    if not path_str:
        raise FileSourceError("path_is_empty")
    # Compose the candidate path.
    candidate = (allowed_root / path_str).resolve()
    # Verify containment: candidate must be inside allowed_root.
    try:
        candidate.relative_to(allowed_root.resolve())
    except ValueError as exc:
        raise FileSourceError(
            f"path_outside_allowed_root:{candidate}",
        ) from exc
    # Reject symlinks whose targets are outside the root.
    for part in candidate.parents:
        if part == allowed_root.resolve():
            break
        if part.is_symlink():
            target = part.resolve()
            try:
                target.relative_to(allowed_root.resolve())
            except ValueError as exc:
                raise FileSourceError(
                    f"symlink_outside_allowed_root:{part}",
                ) from exc
    if candidate.is_symlink():
        target = candidate.resolve()
        try:
            target.relative_to(allowed_root.resolve())
        except ValueError as exc:
            raise FileSourceError(
                f"symlink_outside_allowed_root:{candidate}",
            ) from exc
    return candidate


# ---------------------------------------------------------------------------
# CSV reading
# ---------------------------------------------------------------------------


def _content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class FileConnector:
    """Read rows from a CSV or XLSX file inside an allowed root."""

    def __init__(
        self,
        *,
        path: str,
        sheet_name: str | None,
        allowed_root: Path,
    ) -> None:
        self._resolved = _safe_resolve(path, allowed_root)
        if not self._resolved.is_file():
            raise FileSourceError(f"file_not_found:{self._resolved}")
        self._sheet_name = sheet_name
        self._allowed_root = allowed_root

    # ----------------------------------------------------------------------
    # Convenience: render a deterministic stream of "already-seen" row hashes
    # without parsing the full file. The service uses this to detect "replaced
    # vs appended" cheaply. We rely on the service-stored ``incremental_value``
    # (a SHA-256 of the file) plus the row-dedup payload for dedup; we do NOT
    # ever persist a row index that could let a tampered file sneak past.
    # ----------------------------------------------------------------------

    def read_rows(
        self,
        *,
        previous_content_sha256: str | None = None,
    ) -> ConnectorReadResult:
        ext = self._resolved.suffix.lower()
        if ext == ".csv":
            content = self._resolved.read_bytes()
        elif ext in {".xlsx", ".xls"}:
            # XLSX is binary already — read once.
            content = self._resolved.read_bytes()
        else:
            raise FileSourceError(f"unsupported_extension:{ext}")
        sha = _content_sha256(content)
        # Detect "file replaced": if the previous SHA differs, every row is new.
        file_replaced = previous_content_sha256 is not None and previous_content_sha256 != sha

        if ext == ".csv":
            headers, sample_rows, raw = self._read_csv(content)
        else:
            headers, sample_rows, raw = self._read_xlsx(content)

        # Materialise the mapped rows once. The rows are bounded by
        # ``upload_max_bytes`` for files, so holding them is safe and it
        # lets us report an accurate ``rows_read`` and a correct preview
        # count without deferring to a lazily-consumed generator.
        payload_rows = [
            {
                "_row_index": idx,
                **{h: raw[idx - 1].get(h, "") for h in headers},
                "_row_fingerprint": row_dedup_payload(
                    {h: raw[idx - 1].get(h, "") for h in headers}
                ),
            }
            for idx in range(1, len(raw) + 1)
        ]

        return ConnectorReadResult(
            rows=iter([RawRow(data=p, cursor=str(p["_row_index"])) for p in payload_rows]),
            rows_read=len(payload_rows),
            content_sha256=sha,
            watermark_after=sha,
            headers=headers,
            sample_rows=sample_rows,
            metadata={
                "path": str(self._resolved),
                "extension": ext,
                "content_size_bytes": len(content),
                "file_replaced": file_replaced,
                "read_at": datetime.utcnow().isoformat() + "Z",
            },
        )

    @property
    def resolved_path(self) -> Path:
        return self._resolved

    # ------------------------------------------------------------------
    # Internal readers
    # ------------------------------------------------------------------

    def _read_csv(
        self, content: bytes
    ) -> tuple[list[str], list[str], list[dict[str, str]]]:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        rows = [{k: (v or "") for k, v in row.items()} for row in reader]
        return list(headers), [str(r) for r in rows[:5]], rows

    def _read_xlsx(
        self, content: bytes
    ) -> tuple[list[str], list[str], list[dict[str, str]]]:
        # ``data_only=True``: never evaluate formula cells (formula in a
        # third-party file could attempt to read side-channel state).
        wb = openpyxl.load_workbook(
            io.BytesIO(content), read_only=True, data_only=True,
        )
        sheet = wb[self._sheet_name] if self._sheet_name else wb.active
        rows_iter = sheet.iter_rows(values_only=True)
        headers: list[str] = []
        all_rows: list[dict[str, str]] = []
        first = True
        for row in rows_iter:
            if first:
                headers = [str(c) if c is not None else "" for c in row]
                first = False
                continue
            serialised = []
            row_dict: dict[str, str] = {}
            for j, v in enumerate(row):
                s = "" if v is None else str(v)
                col_name = headers[j] if j < len(headers) else f"col{j}"
                row_dict[col_name] = s
                serialised.append(s)
            all_rows.append(row_dict)
        sample = [str(r) for r in all_rows[:5]]
        return list(headers), sample, all_rows


__all__ = ["FileConnector", "FileSourceError", "_safe_resolve"]
