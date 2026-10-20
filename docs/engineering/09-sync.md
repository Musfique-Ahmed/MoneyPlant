# Chapter 09 — Connected Data Sources & Sync

> *Two connector types, one dedup algorithm, one scheduler. The dangerously powerful part
> of the system — and the four walls around it.*

This chapter is about a feature with a small attack surface that's disproportionately
important to get right. Sync is the part of the system that reaches outside the host,
reads files the user did not upload, runs SQL they did not type, and persists rows
without a human in the loop. Everything here is built to keep that reach controllable.

---

## 9.1 The four pieces

```
   ┌──────────────────────────────────────────────────────────────┐
   │                                                              │
   │   1. Connector Protocol                                      │
   │      Connector(Protocol)  ───  read_rows(...) → iterable     │
   │                                                              │
   │   2. Two implementations:                                    │
   │      FileConnector  (csv / xlsx under file_source_root)      │
   │      SqlConnector   (SELECT-only, parameterised, bounded)    │
   │                                                              │
   │   3. SyncService                                             │
   │      run_sync(db, source_id, trigger)                        │
   │      → maps raw → canonical via column_mapping               │
   │      → parse_rows_for_sync (the same parser as /imports)     │
   │      → SHA-256 dedup + SAVEPOINT writes                      │
   │      → updates watermarks                                   │
   │      → persists SyncRun with sanitised error_summary        │
   │                                                              │
   │   4. SyncScheduler (daemon thread)                           │
   │      interval floor 30s, Event.wait for stop responsiveness │
   │      walks DataSources, picks `is_due()` ones, calls run_sync│
   │      OR  scripts/sync_sources.py  for external schedulers   │
   │                                                              │
   └──────────────────────────────────────────────────────────────┘
```

Each piece has a boundary worth defending. Let's walk them.

---

## 9.2 The connector protocol

```python
# backend/app/services/sync/connectors.py
class Connector(Protocol):
    type: str          # "file" | "sql"

    def read_rows(
        self,
        config: dict,
        *,
        incremental_value: str | None,
    ) -> ConnectorReadResult:
        ...
```

`ConnectorReadResult` is an iterable of `dict`s, one per raw row, plus optional
metadata. That's the *entire* contract a connector implements. Everything downstream —
mapping, parsing, dedup, persistence — sits in `SyncService` and uses the same parser as
manual imports.

```
   raw row (dict)
        │
        │   DataSource.column_mapping:
        │      { canonical_field: source_field, ... }
        ▼
   canonical row (dict, same shape as the manual import path)
        │
        │   parse_rows_for_sync → (rows, issues)
        ▼
   Transaction rows (decimals, dates, idempotent on business_id+source_row_hash)
```

Two implementations of the protocol:

| Connector | Source | What it reads |
|---|---|---|
| `FileConnector` | `backend/app/services/sync/file_connector.py` | A file path under `settings.file_source_root`; `.csv` via the ingestion CSV parser, `.xlsx` via `openpyxl(..., data_only=True)` |
| `SqlConnector`  | `backend/app/services/sync/sql_connector.py` | A parameterised `SELECT` statement against SQLite or Postgres |

---

## 9.3 File connector — the path-containment guarantee

```
   DataSource.config =
       { "path": "ext_invoices.db" }
                                       (relative to file_source_root)
       OR
       { "path": "/abs/path/foo.csv" } (caller-asserted; see below)
```

The containerisation step:

```python
# file_connector.py — illustrative
root = Path(settings.file_source_root).resolve()
candidate = (root / source.config["path"]).resolve()
if not candidate.is_relative_to(root):
    raise SyncError("path_outside_root")
```

The `is_relative_to` check after `resolve()` (which collapses `..` and symlinks) is the
single point that stands between a path-traversal attack and the DB. The contract:

- A relative path stays inside the configured root.
- An absolute path that resolves inside the root is allowed.
- An absolute path that resolves outside is rejected.

The `read_rows` method, after containerisation:

```
   extension = candidate.suffix.lower()
   if extension == ".csv":
       return ConnectorReadResult(_iter_csv_rows(candidate))
   elif extension == ".xlsx":
       return ConnectorReadResult(_iter_xlsx_rows(candidate, sheet=...))
```

`is_relative_to` *does not* protect against symlinks that don't exist at the time of
containment check but exist at read time. The test at
`tests/test_sync.py::test_file_connector_rejects_path_traversal` exercises a symlink;
on Windows it is the one skipped case in the suite. Production hardening for this is a
known gap (see chapter 14).

---

## 9.4 SQL connector — the SELECT-only guard

```
   DataSource.config =
       {
         "url":                 "postgresql+psycopg://…",
         "sql":                 "SELECT id, amount, txn_date FROM invoices WHERE updated_at > :watermark",
         "incremental_column":  "updated_at"
       }
```

The connector does **three** things before executing anything:

```
   1. Statement validation
        st = sqlalchemy.text(sql)
        compiled = st.compile(dialect=…)
        if not compiled.is_select:  raise SqlSourceError
        from_clause length == 1    (no JOIN-with-arbitrary-tables)
        every identifier matches _IDENT_RE  (whitelist of letters / digits / underscore)
        every literal is bound     (no f-string interpolation)

   2. Row limit
        LIMIT <sync_sql_row_limit>  appended only after the statement is verified SELECT-only
        (default 50,000)

   3. Per-connection timeout
        SQLite:    connect_args={"check_same_thread": False, "timeout": N}
        Postgres:  SET statement_timeout = N * 1000
        N max 300s, min 1s
```

The result envelope:

```python
@dataclass
class ConnectorReadResult:
    rows: Iterable[Mapping[str, Any]]
    file_content_sha256: str | None = None     # file connector only
    incremental_value: str | None = None       # sql connector only, for next watermark
```

A connector that fails before yielding *any* rows raises a `SyncError` containing a
synthetic category:

```
   sync_error_category:
     "path_outside_root"
     "unsupported_extension"
     "statement_not_select"
     "join_in_from_clause"
     "invalid_identifier"
     "row_limit_exceeded"   (rare; would mean > 50,000 rows)
     "connect_failed"
     "timeout"
     "parse_failed"
```

These categories are what `SyncRun.error_summary` records — never a raw `OperationalError`,
never a connection string.

---

## 9.5 The dedup engine

`SyncService.run_sync(db, source_id, trigger)` (`service.py:91`) is the only place
that writes transactions outside the manual import path. The dedup algorithm is the same
the manual path uses:

```
   trigger ∈ {"manual", "scheduled", "test"}

   for raw_row in connector.read_rows(...):
       canonical_row = map_raw(raw_row, DataSource.column_mapping)
       # ↑ column_mapping is canonical → source, the same shape users see in /imports/preview

       if canonical_row is incomplete (missing tx_date or amount):
           rows_rejected += 1
           continue

       # parse_rows_for_sync is the same parser that runs at /imports/commit
       canonical_rows, issues = parse_rows_for_sync([canonical_row], column_mapping)
       if issues or not canonical_rows:
           rows_rejected += 1
           continue

       row = canonical_rows[0]
       row["business_id"]    = business_id
       row["data_source_id"] = data_source_id
       row["source_row_hash"] = sha256(canonical_tuple(row)).hexdigest()

       if row["source_row_hash"] in seen_hashes:
           rows_skipped_duplicate += 1
           continue

       try:
           with db.begin_nested():           # SAVEPOINT
               db.add(Transaction(**row))
               seen_hashes.add(row["source_row_hash"])
               rows_added += 1
       except IntegrityError:                # race with another sync
           rows_skipped_duplicate += 1       # the other inserter won

   finally:
       persist SyncRun{trigger, counters, error_summary?}
       update DataSource.{file_content_sha256|incremental_value,
                          last_sync_at, last_error_summary?}
```

### The two watermark policies

```
   File:
     · Recompute file_content_sha256 after a successful read.
     · next run reads the same file, gets the same hash, recomputes rows …
       dedup is by source_row_hash, not by file hash, so re-running a
       changed file picks up only the rows whose canonical hash differs.

   SQL:
     · Read N rows.
     · After successful inserts, set:
         DataSource.incremental_value = str(rows[-1][incremental_column])
     · The service.py:213 guard *rejects* a regressing watermark:
         if new_watermark < old_watermark:  raise SyncError("watermark_regress")
     · Next sync pass the watermark as :watermark bound parameter.
```

### The "test" trigger

```
   POST /api/sources/{source_id}/test  →  trigger="test"
        · same path as run_sync
        · does NOT update watermarks
        · returns the SyncRun's counters in the response
        · used by the UI "Test connection" button
```

A test run is essentially a dry-run sync that still touches the DB (it adds rows if the
source has new ones). For a true read-only smoke test, the UI button uses a separate
flag or relies on the user inspecting the response counters.

---

## 9.6 The `SyncRun` record

| Field | What |
|---|---|
| `id` | UUID |
| `data_source_id` | FK |
| `trigger` | `manual` \| `scheduled` \| `test` |
| `rows_read` | connector yielded |
| `rows_added` | inserted |
| `rows_skipped_duplicate` | dedup hits |
| `rows_rejected` | parse / validation failures |
| `error_summary` | sanitised code (see §9.4) |
| `started_at` / `finished_at` | server timestamps |

The "synthetic category" pattern is what makes logs and the UI safely useful:

```
   ┌─────────────────────────────────────────────────────────────────────┐
   │   raw exception from psycopg2                                   ──► │
   │   sanitised category persisted to SyncRun.error_summary              │
   │   ┌───────────────────────────────────────────────────────────┐    │
   │   │  "read_failed:OperationalError"                             │    │
   │   │  "watermark_regress"                                        │    │
   │   │  "path_outside_root"                                        │    │
   │   │  "statement_not_select"                                     │    │
   │   │  "invalid_identifier:column"                                │    │
   │   │  "row_limit_exceeded"                                       │    │
   │   │  "connect_failed"                                           │    │
   │   │  "parse_failed:KeyError"                                    │    │
   │   │  "timeout"                                                  │    │
   │   └───────────────────────────────────────────────────────────┘    │
   └─────────────────────────────────────────────────────────────────────┘

   Never persisted (and never logged at INFO):
     · the raw SQL string
     · the database URL or any part of it
     · the file path outside the configured root
     · any bytes of file content
```

The same policy is in the file connector: path-traversal errors become
`path_outside_root`, never a dump of the attempted path.

---

## 9.7 The scheduler

```python
# backend/app/services/sync/scheduler.py:126
class SyncScheduler:
    """Daemon-thread scheduler (not APScheduler)."""

    def start(self): ...
    def stop(self): ...
    def run_once(self): ...
    def _loop(self): ...
```

Lifecycle:

```
   FastAPI lifespan startup  (app/main.py:19-43)
        │
        ▼
   if settings.sync_scheduler_enabled:
       scheduler = SyncScheduler(interval=settings.sync_scheduler_interval_seconds)
       scheduler.start()
        │
        │   daemon thread runs:
        │       while not stop_event.is_set():
        │           stop_event.wait(interval)         ← responsive to stop()
        │           for source in run_due_sources(session_factory):
        │               run_sync(session, source.id, trigger="scheduled")
        │
        ▼
   FastAPI lifespan shutdown
        │
        ▼
   scheduler.stop()        sets the Event → loop returns within 1 interval
```

### The `is_due(source)` rule

```python
# scheduler.py:51
_HOURLY_DUE = 70 * 60      # 1h 10m
_DAILY_DUE  = 28 * 3600    # 28h

def is_due(source) -> bool:
    if not source.enabled: return False
    if source.schedule == "manual": return False

    if source.schedule == "hourly":
        if source.last_sync_at is None: return True
        return (now - source.last_sync_at).seconds >= _HOURLY_DUE
    if source.schedule == "daily":
        if source.last_sync_at is None: return True
        return (now - source.last_sync_at).seconds >= _DAILY_DUE
    return False
```

The slack (`70min`, `28h`) prevents back-to-back runs on clock drift and gives
in-flight requests room to complete. Daily sources sync **once a day** for any reason.

### Why a daemon and not APScheduler

The daemon thread with an `Event.wait()` is:

- Trivial to `stop()` (set the event; loop returns within the wait timeout).
- Trivial to inspect (`is_alive()` on the thread).
- Free — no third-party dep.
- No job-store to coordinate.

APScheduler adds persistence, multi-host coordination, and cron-style schedules that
this product does not need.

---

## 9.8 External scheduling

For deployments where the API host should not run a daemon (e.g. a managed container
with a strict shutdown grace period), disable the in-process scheduler and drive syncs
from external cron/Task Scheduler:

```python
# backend/app/core/config.py
sync_scheduler_enabled: bool = True          # turn OFF for external scheduling
sync_scheduler_interval_seconds: int = 300   # internal scheduler poll interval
```

The CLI:

```bash
python -m scripts.sync_sources --all                # all sources for all businesses
python -m scripts.sync_sources --all --dry-run      # skip writes; show counters
python -m scripts.sync_sources --source <uuid>      # single source
python -m scripts.sync_sources --list               # show sources + last_sync_at
```

The CLI runs the same `service.py:run_sync` under the hood — there is no behaviour
difference between "the daemon did it" and "cron did it" except the trigger string
(`"scheduled"` vs `"manual"`).

---

## 9.9 Demo data

For the seeded demo, the scheduler polls `sample_data/` for changes. The repo carries:

```
   sample_data/
   ├── ext_invoices.db            SQLite used by the SQL connector demo
   ├── daily_transactions.xlsx    XLSX demo source
   └── several CSVs               file-source demos
```

`scripts/simulate_daily_data.py` mutates these files so the scheduler picks them up on
its next tick and produces a visible dashboard update. (`scripts/simulate_daily_data.py`
appends deterministic "today" data.)

---

## 9.10 The four walls

These are the defences a reviewer should look for in any sync-related PR.

```
   1. Containment (file)
        candidate.resolve().is_relative_to(file_source_root.resolve())
        → blocks path traversal and absolute-path escapes.

   2. SELECT-only (sql)
        compiled.is_select + join-count == 1 + identifier whitelist
        → blocks DML / DDL / multi-table pivots.

   3. Row limit
        LIMIT n appended after SELECT confirmed
        → blocks accidental 50GB pulls.

   4. Sanitised errors
        SyncRun.error_summary = synthetic code only
        → blocks credential / SQL leak in logs and UI.
```

A PR that weakens any of these is a release-blocker regardless of the feature it brings.

---

## 9.11 The DataSource lifecycle

```
   Business exists
        │
        ▼
   POST /api/sources
        { business_id, name, type, config, column_mapping, schedule }
        → returns DataSourceRead
        │
        ▼
   POST /api/sources/{id}/test             ← see counters, no watermark update
        │
        ▼
   POST /api/sources/{id}/sync             ← manual run
        │
        ▼
   scheduler (if enabled)                  ← runs due sources on the interval
        │
        ▼
   PATCH /api/sources/{id}                 ← edit (name + schedule only)
        │
        ▼
   GET /api/businesses/{id}/freshness      ← frontend polls every 5s
        │
        ▼
   DELETE /api/sources/{id}                ← cascade behaviour: TBD
```

The `FreshnessStrip` in the dashboard polls `/api/businesses/{id}/freshness` every 5s
when the page is open. The freshness endpoint returns the *backend-computed* headline
per source and per-business — never raw `DataSource` rows.

---

## 9.12 The "no-creative-math" discipline holds here too

A `SyncRun` is just a counter record. It is never the basis of a UI computation.
Dashboard widgets that use sync data ask for the *freshness* (timestamp + status), not
for derived metrics. The transactions are what get computed on — the sync record
metadata doesn't.

The assistant's LLM prompt explicitly does not include `SyncRun` records, even though
they are persistent DB rows. The principle is "the LLM sees pre-rendered dashboards,
not raw sync metadata".

---

## 9.13 Extending this

### Adding a third connector type (e.g. Google Sheets API)

1. Add to `sync/connectors.py` Protocol if you can reuse the iterable-of-dicts shape.
2. Create `sync/<name>_connector.py` implementing `read_rows`.
3. Extend `DataSource.type` enum in `models/data_source.py` + Alembic migration.
4. Extend `api/data_sources.py` to dispatch creation by type.
5. Extend `ui/(app)/data/page.tsx` form to capture type-specific config.
6. The dedup, watermarking, and SAVEPOINT logic in `service.py:run_sync` is reused
   unchanged.

### Adding a new "trigger" value

The trigger field is `Literal["manual", "scheduled", "test"]`. To add e.g. "retried":

1. Add to the enum in `models/data_source.py` (DB enum).
2. Add a Literal entry to `SyncRunRead` Pydantic mirror.
3. Extend any UI control that maps trigger → label.
4. Document the trigger semantics.

### Replacing the scheduler

The `SyncScheduler` class is small enough to replace with an APScheduler, a Celery
beat, or a custom timer. The seam is `run_due_sources(session_factory)` — anything
that walks `DataSource` rows and calls `run_sync(session, source.id, "scheduled")` is
a valid scheduler.

---

*Next: [Chapter 10 — REST surface](10-rest-surface.md)*