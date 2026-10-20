# Chapter 08 — Ingestion Pipeline

> *Two doors into the same parser: manual upload and scheduled sync. Both produce
> `Transaction` rows with the same shape, the same idempotency guarantee, the same
> metrics.*

This chapter explains the manual upload path. Chapter 09 covers the sync path. Both paths
converge on the same idempotent write logic.

---

## 8.1 The two-door pattern

A `Transaction` row in MoneyPlant is always produced by one of two operations:

```
              ┌────────────────────┐
              │  CSV / XLSX file   │
              └─────────┬──────────┘
                        │
            ┌───────────┴───────────┐
            │                       │
            ▼                       ▼
   ┌──────────────────┐    ┌──────────────────────┐
   │  Manual upload    │    │  Scheduled sync      │
   │  POST /imports/*  │    │  SyncScheduler daemon│
   │  /preview /commit │    │  OR scripts.sync_    │
   │                   │    │  sources --all       │
   └─────────┬─────────┘    └──────────┬───────────┘
             │                         │
             └────────────┬────────────┘
                          ▼
               ┌─────────────────────┐
               │  parse_rows_for_sync│  ←  single parser for both paths
               │  (sync/service.py)  │
               └──────────┬──────────┘
                          │
                          ▼
                Transaction rows
```

The same `parse_rows` function (`backend/app/services/ingestion/csv.py:165`) is reused
by both paths. The sync path adds an indirection
(`sync/service.py:395 parse_rows_for_sync`) that re-serialises a row dict to CSV in
memory and calls `parse_rows`, so the validation, mapping, and date/Decimal parsing
rules apply identically whether the source is a manual file or a SQL connector.

---

## 8.2 The manual flow

```
   user selects file in /data or /
        │
        ▼
   POST /api/imports/preview
        │
        ├──> _ext(filename)                  identify csv vs xlsx
        ├──> read content (10 MiB max cap)
        ├──> preview_csv(content)            returns PreviewResult
        │      { headers, suggested_mapping,
        │        sample_rows (max 50) }
        ├──> return ImportPreview
        ▼
   UI shows the suggested mapping; user confirms/adjusts
        │
        ▼
   POST /api/imports/validate
        │
        ├──> parse_rows(content, mapping)
        │      returns (rows, issues)
        │
        └──> return { valid_rows: int, issues: list }
        ▼
   user clicks "Commit" only if valid_rows > 0
        │
        ▼
   POST /api/imports/commit    ← same body shape as /validate
        │
        ├──> parse_rows(content, mapping)        ← reused again
        ├──> for each row:
        │       source_row_hash = SHA-256(canonical_tuple)
        │       if hash in seen_hashes:
        │           rows_skipped_duplicate += 1
        │       else:
        │           with db.begin_nested():      SAVEPOINT
        │               db.add(Transaction(... source_row_hash=hash))
        │               rows_added += 1
        │               seen_hashes.add(hash)
        │       issues:
        │           rows_rejected += 1
        ├──> persist ImportJob{ status:committed, counters }
        │
        └──> 201 Created ImportJobRead
```

The routes (`backend/app/api/imports.py`):

| Route | Purpose |
|---|---|
| `POST /api/imports/preview` | Sample + suggested mapping |
| `POST /api/imports/validate` | Run the parser, surface validation issues without committing |
| `POST /api/imports/commit` | Run the parser, dedup, persist, return counters |
| `GET /api/imports` | List ImportJobs for a business |
| `GET /api/imports/{job_id}` | Single ImportJob |
| `GET /api/imports/fields/canonical` | The `CANONICAL_FIELDS` enum |

---

## 8.3 The canonical fields

```python
# backend/app/services/ingestion/csv.py:53
CANONICAL_FIELDS: list[str] = [
    "tx_date",
    "cash_flow_date",
    "description",
    "amount",
    "currency",
    "direction",
    "category",
    "payment_status",
    "customer_or_supplier",
]
```

`suggest_mapping(headers)` (`csv.py:101`) walks a small `SYNONYMS` dictionary that maps
common header strings (e.g. "Date", "transaction_date", "Posted", "Txn Date") to
canonical names. Anything ambiguous is left unmapped — the user resolves it in the
preview UI.

```
   "Tx Date"          → tx_date
   "Amount"            → amount
   "Credit / Debit"   → direction
   "Customer"          → customer_or_supplier
   "Description"       → description
   "Reference"         → (unmapped — user picks)
   "Project"           → (unmapped — user picks, falls in description if ignored)
```

A canonical field left unmapped is fine — it just doesn't reach the database.
Required-by-engine fields are `tx_date`, `amount`, `direction`. Missing those triggers
a `ValidationIssue(row=N, field="...", severity="error", message="...")`.

---

## 8.4 The parser

```python
# backend/app/services/ingestion/csv.py:165
def parse_rows(
    content: bytes,
    mapping: dict[str, str],
) -> tuple[list[dict[str, Any]], list[ValidationIssue]]:
    """
    Parse CSV given a user-confirmed mapping. Returns (rows, issues).
    Each row is a dict ready to be turned into a Transaction.
    """
```

### Steps

```
  1. Decode bytes → text
       utf-8 → utf-8-sig → latin-1 (errors="replace")
       so a BOM-touched file or a Latin-only file still parses

  2. csv.DictReader over the row stream
       all errors are collected, never raised

  3. For each row, derive fields:
       tx_date     = _parse_date(row[mapping["tx_date"]])
       amount      = _parse_decimal(row[mapping["amount"]])
       currency    = (row[mapping["currency"]] or "USD")
       direction   = (row[mapping["direction"]] or "").lower()
                      aliases: {inflow, outflow} ∪ {income, expense} ∪ {credit, debit}
       sign-based fallback:
            amount < 0   → direction = "outflow", amount = -amount
            amount >= 0  → direction = "inflow"
       category    = (row[mapping["category"]] or "uncategorised")
       description = (row[mapping["description"]] or "")

  4. Validate
       tx_date required; issue at row N if missing/invalid
       amount required; issue at row N if missing/invalid (neither raise)

  5. Return
       (list of row dicts, list of ValidationIssue)
```

`amount` is always stored positive. `direction` carries the sign. This is the
`Transaction` dataclass's contract (`metrics.py:28`).

The two parsers:

| Format | Module | Notes |
|---|---|---|
| CSV | `services/ingestion/csv.py` | stdlib `csv.DictReader`; row-by-row streaming |
| XLSX | `services/ingestion/xlsx.py` | `openpyxl.load_workbook(data_only=True)`; formulas are resolved to values, never carried forward |

---

## 8.5 Validation issues, not exceptions

The parser never raises. Every problem surfaces as a `ValidationIssue`:

```python
class ValidationIssue:
    row: int               # 1-indexed (header = row 1)
    field: str             # "tx_date" | "amount" | ...
    severity: Literal["error", "warning"]
    message: str
```

Errors cause the row to be skipped. Warnings let the row pass with a notice. Both kinds
appear in the ImportJob record (`ImportJob.rows_rejected` counts errors).

```
   ┌──────────────────────────────────────────────────────────────────┐
   │   on error        →  rows_rejected += 1, row is NOT written      │
   │   on warning      →  row is written, issue captured             │
   │                                                                  │
   │   ImportJob counters at the end:                                 │
   │     rows_added                ← unique inserts                   │
   │     rows_skipped_duplicate    ← already-seen source_row_hash     │
   │     rows_rejected             ← unparseable rows                 │
   │                                                                  │
   │   sum(rows_added) + sum(rows_skipped_duplicate) + sum(rows_rejected) │
   │     == rows_read                                                  │
   └──────────────────────────────────────────────────────────────────┘
```

This counter math is the same one used by sync. The two paths converge.

---

## 8.6 The "Upload max bytes" cap

```python
# backend/app/core/config.py:60
upload_max_bytes: int = 10 * 1024 * 1024   # 10 MiB
```

Enforced in `imports.py:preview()`. A 10 MiB cap is generous for a CSV of ~50k
transactions and a small XLSX, and prevents accidental gigabyte uploads from a
misconfigured cron that points at the wrong file.

---

## 8.7 The shared-engine invariant

The same parser is used by:

1. **Manual import** — runs in a request, returns issues synchronously.
2. **Scheduled sync** — runs in a daemon thread, accumulates counters, persists as a
   `SyncRun`.

Why this matters: **a row that fails a manual import will fail a sync of the same
file.** A row that the manual parser accepts *exactly* the same way as a sync — same
field mapping, same date format, same Decimal handling. There are no hidden
"two-versions-of-the-truth" bugs to chase.

The indirection at `sync/service.py:395` is `parse_rows_for_sync(rows, mapping)`,
which serialises each raw row dict to CSV in memory and then calls
`parse_rows` as if the row came from a file. The cost is one cheap re-serialisation;
the benefit is that the entire ingestion validation lives in exactly one place.

---

## 8.8 XLSX specifics

`xlsx.py:11 preview_xlsx` returns the same `PreviewResult` shape as `preview_csv`. The
XLSX reader:

- Uses `openpyxl.load_workbook(..., data_only=True)` — formulas are resolved to values
  at read time, not carried forward. A formula referencing a missing cell yields `None`,
  not the formula text. This is the contract.
- Reads the first sheet by default; `?sheet=<name>` lets the user pick.
- Header row detection honours the user-supplied `header_row` field.

The XLSX path does not have a separate "validators" module — the parsed rows feed the
same `parse_rows_for_sync` indirection, so an XLSX-sourced row goes through the
same date/Decimal/direction logic as a CSV-sourced row.

---

## 8.9 The dedup contract

The manual import uses the same dedup algorithm as sync:

```
   canonical_tuple = (business_id, tx_date, amount, currency,
                      direction, category, description)
   source_row_hash = sha256(canonical_tuple).hexdigest()   # stored as hex string

   uniqueness check:
     in-memory seen_hashes set + DB unique index uq_transactions_business_source_row_hash
```

The unique index is on `(business_id, source_row_hash)`. The two checks together give:

- **Cold dedup** (in-process): known hashes are skipped without touching the DB.
- **Race dedup** (cross-process): if two uploads arrive at the same instant with the
  same row, the SAVEPOINT pattern guarantees one inserter wins, the other is counted
  as duplicate (`IntegrityError` → `rows_skipped_duplicate`).

The contract is the same as sync; see chapter 09 §9.5.

---

## 8.10 The `ImportJob` record

| Field | What |
|---|---|
| `id` | UUID |
| `business_id` | FK |
| `filename` | the original uploaded file name |
| `sheet_name` | XLSX only |
| `mapping` | JSON of the column mapping the user confirmed |
| `status` | `preview` \| `validating` \| `committed` \| `rejected` |
| `rows_added` | inserts |
| `rows_skipped_duplicate` | already-seen hash |
| `rows_rejected` | validation errors |
| `error_summary` | sanitised error code (e.g. `"parse_failed:KeyError"`); never the original trace |
| `created_at` | server timestamp |

`ImportJobRead` is the Pydantic mirror; the Zod equivalent lives in
`apps/web/lib/schemas.ts`.

---

## 8.11 When the parser lies

Three failure modes worth knowing:

1. **Encoding substitution** — `latin-1 (errors="replace")` inserts U+FFFD for
   undecodable bytes. A row with a non-Latin currency symbol in a description may
   *appear* to parse but carry an artefact. We treat this as a soft warning in
   production data validation; the IntegrityError dedup stays consistent because
   the bytes are deterministic.

2. **CSV dialects** — the parser uses `csv.DictReader` with default dialect (comma).
   A TSV (tab-separated) will parse as one column per row, fail to find any
   canonical mapping, and yield all rows as rejected with helpful errors. The user
   is expected to convert to CSV before upload; the file extension check at
   `imports.py:36 _ext()` raises on `.tsv`.

3. **Massively wide CSVs** — a CSV with 100+ columns does not break the parser; the
   unmapped columns are simply ignored. The user sees a preview with suggested
   mappings for whatever canonical fields are recognised, and proceeds.

---

## 8.12 Re-running an import

The product is **idempotent under re-import**, by design:

```
   scenario A:
     · user imports "march.csv"  → 200 rows added
     · user imports "march.csv" again → 0 added, 200 skipped_duplicate

   scenario B (one row was wrong):
     · user fixes the row in their spreadsheet
     · user imports the fixed file → 1 added, 199 skipped_duplicate, 0 rejected
       (the wrong row is still in the DB; product does not auto-update on dedup)

   scenario C (typed the row wrong):
     · row added with amount "123.450" → "123.45"
     · user re-uploads with amount "123.450" → still dedupes on canonical tuple
     · the wrong-value row remains in the DB; the user has no way to fix it
       through the import pipeline
       (intentional gap; see chapter 14, "Known limitations")
```

---

## 8.13 Where this stops being pure

The `parse_rows` function itself is pure: bytes in, `(rows, issues)` out. The wrapping
endpoint at `imports.py` is *not* — it takes a session, does the dedup, persists the
ImportJob. The split is intentional:

- **Pure parser**, easily unit-testable on bytes alone.
- **Stateful endpoint**, owns the DB lifecycle.

Anything you want to add to ingestion should start in `parse_rows` if it touches *what
counts as a row*, or in `imports.py` if it touches *what to do with one*.

---

## 8.14 Extending this

### Adding a new canonical field

1. Add to `CANONICAL_FIELDS` in `csv.py:53`.
2. Add synonyms in `SYNONYMS` (same file).
3. Add a column to `Transaction` model (`models/transaction.py`) + migration.
4. Add to `Transaction` Pydantic mirror (`schemas/transaction.py`).
5. Add the field to the `Transaction` Zod mirror (`apps/web/lib/schemas.ts`).
6. If the field affects engine math: add it to `services/finance/metrics.py` `Transaction` and to the schema validator.

### Adding a new file format

A trivial path:

1. New `services/ingestion/<format>.py` with `preview_<format>(content) -> PreviewResult`
   and a row-producing function that returns the same dict shape as `parse_rows`.
2. Extend `_ext()` in `imports.py` to dispatch.
3. Reuse `parse_rows_for_sync` indirection in `sync/service.py:395`.

A non-trivial path: there is exactly one — an integration where the upstream does not
produce a row-per-data-row shape. In that case, write a connector under
`services/sync/` and use the sync path instead of the import path.

### Replacing the parser

`parse_rows` is the single source of truth for "what counts as a row". If you replace
it, the Zod mirror and the sync indirection must move with it. There is no path that
preserves old behaviour without keeping `parse_rows` intact.

---

*Next: [Chapter 09 — Connected data sources & sync](09-sync.md)*