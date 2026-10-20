# MoneyPlant — Documentation Verification (read-and-verify audit)

Scope: claims made in MoneyPlant's technical document and security self-assessment, cross-referenced against the actual code in `c:\Users\nurep\MoneyPlant` on `Prachurja` at `c73ee34`. **No code was changed.** Test counts are real (run today, 2026-…; see "Verification" section below). Where a claim is right but for the wrong reason, the row is **DIFFERENT** rather than **TRUE**.

---

## 1. Claims vs. code

| # | Claim | What the docs say | What the code actually does | Evidence (file:line) | Status |
|---|---|---|---|---|---|
| 1a | Alerts list | "Cash-flow alerts … Five alert codes (NEGATIVE_CASH, LOW_BUFFER, SHORT_RUNWAY, PROFITABLE_BUT_CASH_POOR, SHARP_DROP)" | Exactly five codes match by name and order | `backend/app/engine/alerts.py:200, 225, 249, 289, 317` | **TRUE** |
| 1b | Runway: < 3 months = Warning | "Runway warning threshold = 3 months" | `cfg.short_runway_warning_months = Decimal("3")` → Critical if `< 1`, else Warning if `< 3` | `backend/app/engine/alerts.py:67-68, 246-279` | **TRUE** |
| 1c | Runway: < 1 month = Critical | "Runway critical threshold = 1 month" | `cfg.short_runway_critical_months = Decimal("1")` → severity `SEVERITY_CRITICAL` | `backend/app/engine/alerts.py:68, 246-262` | **TRUE** |
| 1d | Low-buffer default | "Closes the period below N months of average operating costs" | `cfg.low_buffer_months = Decimal("1")` (1 month of average opex) | `backend/app/engine/alerts.py:65, 218-242` | **TRUE** |
| 1e | Sharp-drop threshold | "Month-over-month closing-cash fall > 25%" | `cfg.sharp_drop_pct = Decimal("0.25")` (25% drop → Info) | `backend/app/engine/alerts.py:70, 311-336` | **TRUE** |
| 1f | Severity labels not colour alone | "Text-label severities (Critical / Warning / Info)" | Explicit severity strings; UI gets `severity` field | `backend/app/engine/alerts.py:87-89, ALL_SEVERITIES` | **TRUE** |
| 2a | DSCR = 1.2 affordability floor | "1.2 for affordability" | `min_dscr: Decimal = Decimal("1.2")` — the **only** DSCR floor in matching | `backend/app/engine/financing.py:124, 386-414` | **TRUE** |
| 2b | DSCR hard limit = 1.0 | "1.0 as a hard limit" | The hard limit is **1.2**, not 1.0. The doc-comment only describes DSCR<1.0; actual code uses 1.2 | `backend/app/engine/financing.py:17-25 (docstring) vs 386-414 (code)` | **DIFFERENT** |
| 2c | Reproductivity is annuity | Annuity formula in `Decimal` | `payment = principal * r / (1 - (1+r)**-n)`, ROUND_HALF_UP to 0.01 | `backend/app/engine/financing.py:169-194` | **TRUE** |
| 2d | Catalogue products | "5 illustrative products" | Exactly 5 in `sample_data/financing_catalog.json` | `sample_data/financing_catalog.json:5-70` | **TRUE** |
| 2e | Catalogue disclaimer | Disclaimer surfaced in API | `catalog_disclaimer` set in `FinancingOutcome`; returned through `/api/businesses/{id}/financing-options` | `backend/app/engine/financing.py:300-304` | **TRUE** |
| 3a | SQL connector: SELECT-only | "Only SELECT" | The connector inspects the table via `sa.inspect(engine).get_columns(...)` and executes one `sa.select(...).limit(...)` query — no `INSERT/UPDATE/DDL` paths | `backend/app/services/sync/sql_connector.py:188-210` | **TRUE** |
| 3b | SQL connector: parameterised | "parameterised" | `sa.bindparam("watermark")` is the only binding; identifiers go through `_IDENT_RE = ^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$` | `backend/app/services/sync/sql_connector.py:42, 49-52, 199-205` | **TRUE** |
| 3c | SQL connector: statement timeout | "statement timeout" | Postgres: `SET statement_timeout` on connect (default 30s, capped 1..300s). SQLite: `connect_args={"timeout": N}` | `backend/app/services/sync/sql_connector.py:55-96, 141` | **TRUE** |
| 3d | SQL connector: row limit | "row limit" | `row_limit` capped to 1..1,000,000; default 50_000; per-source override available | `backend/app/services/sync/sql_connector.py:140, schemas/data_source.py:49` | **TRUE** |
| 3e | No free-form SQL from client | "free-form SQL from the client" → no | The client payload has only `table`, `schema_name`, `incremental_key`, `row_limit`, `statement_timeout_seconds`. **No `query`/`sql` field exists in any schema** | `backend/app/schemas/data_source.py:24-59 (DataSourceConfig)` | **TRUE** |
| 3f | Credentials in env-var name only | "stored as env-var names" | `secret_ref` is the env-var name; the URL is read at sync-time via `os.environ.get(s.secret_ref, "")`. Never written to the DB, never returned | `backend/app/api/data_sources.py:257-259; backend/app/schemas/data_source.py:115-135` | **TRUE** |
| 3g | Credentials never in API response | "never returned by any API response" | `DataSourceRead` deliberately omits `secret_ref`. `_to_read` serialises only the listed fields | `backend/app/schemas/data_source.py:115-135; backend/app/api/data_sources.py:59-79` | **TRUE** |
| 3h | Credentials never in logs / error_summary | "never logged" | `os.environ.get("…", "")`, then wrapped in safe `SqlSourceError`s ("`db_driver_not_installed`", "`invalid_db_url`", "`query_failed:{class}`"). Test asserts `SUPERSECRETPW` never appears | `backend/app/services/sync/sql_connector.py:148-158, 213-218; backend/app/services/sync/service.py:173-181; tests/test_sync.py:445-487` | **TRUE** |
| 4a | File path scoped to allowed directory | "file path restricted" | `FileSourceRoot` = `Settings.file_source_root` (env `FILE_SOURCE_ROOT`, default `./sample_data`); resolved path must be `.relative_to(allowed_root)` | `backend/app/services/sync/file_connector.py:56-94, 109-119` | **TRUE** |
| 4b | Path traversal rejected | "rejected" | `_safe_resolve` raises `FileSourceError("path_outside_allowed_root:…")` if candidate is outside root | `backend/app/services/sync/file_connector.py:69-73, 374-376 (test)` | **TRUE** |
| 4c | Symlink escape rejected | "rejected" | Walks `candidate.parents` and rejects any symlink whose `.resolve()` is outside the root | `backend/app/services/sync/file_connector.py:75-93, 389-390 (test_skipped_on_win)` | **TRUE** |
| 4d | CSV/XLSX values-only, no formulas | "values only" | CSV reader: `csv.DictReader`. XLSX: `openpyxl.load_workbook(..., data_only=True, read_only=True)` — never evaluates formulas | `backend/app/services/sync/file_connector.py:206-210; backend/app/services/ingestion/xlsx.py:30-35` | **TRUE** |
| 4e | Upload size cap | "file size limit" | `Settings.upload_max_bytes = 10 * 1024 * 1024` (10 MiB) enforced on preview / validate / commit | `backend/app/core/config.py:60; backend/app/api/imports.py:89, 121, 157` | **TRUE** |
| 5a | LLM fields sent to provider (set) | "exact fields" (set unspecified in docs) | `ExplanationContext` carries **business_industry, reporting_period, user_question, computed_baseline, computed_scenarios, rule_evaluations, laya_assessment, assumptions, missing_information, business_goal** — no raw transaction list, no descriptions | `backend/app/services/llm/base.py:62-75` | **MISSING** (docs don't list them) |
| 5b | No raw transaction descriptions in prompts | "no raw transactions" | `ExplanationContext` schema and both call sites (assistant chat + decisions explain) **never include `description`/`category`/`customer_or_supplier` arrays**. Only compact metrics, scenarios, rule summaries, the user question, and a `business_goal` string | `backend/app/api/ai.py:99-112; backend/app/api/decisions.py:200-214` | **TRUE** |
| 5c | No business name in prompt | (not in claim) | `business_industry` is enum value (e.g. "retail"); `business.name` is **never** put in the context. The 5 business names from the demo data ("Acme") do not leave the host | `backend/app/api/ai.py:96-101; backend/app/api/decisions.py:201-203` | **TRUE** (correctness not in claim list; flagged for free-text risk) |
| 6a | Formula-injection handling (=, +, -, @) | (claim says it's handled) | **There is no formula-prefix sanitization anywhere.** CSV cells are read with `csv.DictReader` (a plain string), XLSX cells use `data_only=True` (cached value, never a formula — the formula expression itself never reaches Python), but if a string **value** in a cell begins with `=`, `+`, `-`, or `@` it is imported verbatim into `description`/`category` and persisted to the DB | `backend/app/services/ingestion/csv.py:165-247; backend/app/services/sync/file_connector.py:208-210` | **MISSING** (no `=?-prefix` strip for CSV strings; XLSX formula expressions can't reach Python anyway) |
| 6b | File size limit | "10 MB" default, configurable | `upload_max_bytes = 10 * 1024 * 1024` (10 MiB, configurable) | `backend/app/core/config.py:60-61` | **TRUE** |
| 6c | Row limit on import | (not in claim) | No **row-count** cap in `commit_import`. `upload_max_bytes` is the only bound. The sync connector caps at `row_limit=50_000` per source | `backend/app/api/imports.py:147-…; backend/app/services/sync/sql_connector.py:140` | **MISSING** (gap) |
| 7 | Authentication | "no authentication in MVP" | `app/core/security.py` is a stub that returns `True` from `is_demo_mode()`. CORS allows `Authorization` header but no auth handler exists. No `Depends(get_current_user)`, no token validation, no role checks anywhere in the codebase | `backend/app/core/security.py:12-19; backend/app/main.py:59-66; backend/app/api/businesses.py:1-7` | **TRUE** |
| 8a | Data deletion (per-business) | (claim says none) | `DELETE /api/businesses/{id}` exists and cascades. No DELETE for transactions, scenarios, decision reports, or import jobs | `backend/app/api/businesses.py:107-114; (grep no `router.delete` elsewhere in `businesses.py`, `scenarios.py`, `decisions.py`, `imports.py`, `transactions.py`)` | **DIFFERENT** — partial: business-level delete exists, but transaction-level deletion does not |
| 8b | Data export (CSV/JSON download) | (claim says none) | There is **no** `/api/.../export`, no `StreamingResponse`, no `csv.writer` in any API response path. No export endpoint at any level | `grep -i 'StreamingResponse\|download\|export' backend/app/api/*.py` → no matches | **TRUE** |
| 9a | Sync is idempotent | "re-sync never duplicates" | SHA-256 over the canonical row tuple → `uq_transactions_business_source_row_hash` unique index. Re-running a sync tries to insert and the SAVEPOINT catches `IntegrityError` | `backend/app/services/sync/service.py:278-294; backend/alembic/versions/0003_sync_dedup_columns.py:44-49; backend/app/models/transaction.py:34-39` | **TRUE** |
| 9b | Sync is transactional (failure leaves data intact) | "failure leaves existing data intact" | All writes happen under one outer `Session.flush`/`commit`; mid-loop errors roll back cleanly. The `_idempotent_insert` block uses `db.begin_nested()` (SAVEPOINT) so per-row race-loss doesn't abort the run | `backend/app/services/sync/service.py:97-100, 287-294` | **TRUE** |
| 9c | Test proof of idempotency | (claimed) | `tests/test_sync.py:150-178` `test_resync_is_idempotent` asserts `count == 2` after a re-sync of the same 2 rows | `backend/tests/test_sync.py:150-178` | **TRUE** |
| 9d | Test proof of transactional integrity | (claimed) | `tests/test_sync.py:494-…` `test_failed_sync_leaves_existing_data_intact` runs a good sync, force-fails a second, asserts `before == 1` preserved | `backend/tests/test_sync.py:494-…` (visible header at 489, body extends to EOF) | **TRUE** |

---

## 2. Verification (real, this session)

`pytest` and the frontend checks ran in the foreground. Playwright ran headlessly against installed Playwright 1.64.1 without a browser binary.

| Command | Directory | Result | Where |
|---|---|---|---|
| `pytest -v` | `backend/` | **226 passed, 1 skipped** in 22.58s (227 collected) | `t:\Users\nurep\AppData\Local\Temp\audit_junit.xml` |
| Skip reason | | `tests\test_sync.py:387: symlinks unavailable on this host` (needs Windows Developer Mode for `link.symlink_to()`) | |
| `npm run typecheck` | `apps/web/` | **exit 0** (clean) | terminal output, this session |
| `npm run lint` | `apps/web/` | **exit 0** — "No ESLint warnings or errors" | terminal output, this session |
| `npm run test` | `apps/web/` | **42 passed (42)** in 2.03s — `lib/format.test.ts (8) ✓`, `lib/schemas.test.ts (34) ✓` | terminal output, this session |
| `npx playwright test a-create-business.spec.ts` | `apps/web/` | **1 failed, 0 passed** | full text in (3) below |
| Full Playwright suite | `apps/web/` | **Not executed** — same browser-binary error | (the single-browser test reproduces it) |

**`pytest` exit code:** `0` — the JUnit XML reports `tests=227 failures=0 errors=0 skipped=1`. The skip is a real skip (Windows has no symlinks without Developer Mode), not a work-around for a failure.

**`a-create-business.spec.ts` failure (verbatim):**

```
Error: browserType.launch: Executable doesn't exist at
C:\Users\nurep\AppData\Local\ms-playwright\chromium_headless_shell-1248\
chrome-headless-shell-win64\chrome-headless-shell.exe
Looks like Playwright was just installed or updated.
Please run the following command to download new browsers:
    npx playwright install
1 failed
    [chromium] e2e\a-create-business.spec.ts:8:5 A: first-run creates a business
    and lands on dashboard
```

Full Playwright suite was not run — it would hit the same error 11×. The `npx playwright --list` step succeeded (11 tests in 11 files detected) so we know the specs parse and import cleanly. The browser binary needs `npx playwright install` (which is the installation rule — installing browsers was not in this audit's scope and would download a ~100 MB chromium snapshot).

---

## 3. Gaps, ordered by security importance

1. **No authentication anywhere.** Every endpoint is reachable without credentials. Adding it later will require a tenant-scoping `Depends(get_current_user)` on every router and a per-user `business_id` policy. Today, a process on the same host can do `POST /api/businesses`, `POST /api/imports/commit`, `DELETE /api/businesses/{id}`, etc., at will. (`backend/app/core/security.py:12-19`.)
2. **No formula-injection sanitization for CSV string fields.** A CSV cell with `=HYPERLINK("…")` or `=cmd|'/c calc'!A0` is imported byte-for-byte into `description`/`category` and reaches the dashboard UI, an Excel re-export, and the assistant context. XLSX is safe by construction (formula expressions never enter Python — only the cached scalar does), but XLSX still needs review in any downstream re-export. Mitigation today: prefix-strip in the ingestion layer (`if value.startswith(("=","+","-","@")): value = "'" + value`).
3. **No row-count cap on import.** Only `upload_max_bytes = 10 MiB` bounds `POST /api/imports/commit`. A single huge CSV (10 MiB of dense rows) is parsed in one shot into memory in `commit_import`. Sync has a per-source `row_limit` (50_000 default) — the manual upload path doesn't.
4. **SQL connector: only SQLite and Postgres.** MySQL/MSSQL/Oracle raise `SqlSourceError("unsupported_db_url_scheme")`. A misconfigured PostgreSQL URL with a typo would surface as `invalid_db_url` — neither is a full validation: the connector will still try to send `SET statement_timeout` and could leak the URL fragment in some driver errors (mitigated by the `f"query_failed:{exc.__class__.__name__}"` rule, which leaks only the exception class).
5. **No `DELETE` for transactions.** A business can be deleted (and its transactions cascade), but there's no way to delete a single erroneous imported transaction; the user would have to re-seed. Pair this with the fact that re-running a sync on the same row is a no-op (`uq_transactions_business_source_row_hash`) — a typo in a CSV becomes permanent.
6. **No data export endpoint.** There is no CSV download, no JSON dump, no portability. Users can inspect via the UI only. This isn't a vulnerability but it's a privacy claim you can't actually fulfill: a user who asks "give me my data" cannot get it.
7. **Sync `last_error_summary` is bounded at 500 chars** — fine, but the field is returned in `DataSourceRead` and could contain a connector class name plus the user-supplied path. Not a secret, but worth knowing it leaks.
8. **CORS allows `Authorization`** (`backend/app/main.py:64`) — placeholder for when you add auth. Nothing validates it today, so it has no observable effect, but a future cookie/header-based plan should revisit this list.
9. **`api/config/public` exposes `ai_local_model`, `ai_local_base_url`, `cors_origins`** — none are secrets, but worth noting they are the only endpoints that take any of these fields.
10. **`backend/app/services/ingestion/csv.py` does no encoding validation.** Falls back to `latin-1, errors="replace"` which silently replaces undecodable bytes — a CSV with intentional malformed UTF-8 (e.g. to inflate `row_count` while making some rows invisible) lands in the database as lossy strings. Low risk but a real input-validation gap.

---

## 4. Claims I did NOT verify because they're outside this audit's scope

- LLM provider key handling (OpenAI/Anthropic): I confirmed the env-var names; I did not exercise a real API call.
- Laya: same — confirmed the adapter exists, did not call it.
- Industry adapters (manufacturing / retail / etc.): not in claim list.
- Performance, concurrency, and lock-file behaviour for the SQLite default: not in claim list; the SQLAlchemy engine uses `check_same_thread=False` which is fine for FastAPI's threadpool but means tests can't run two writers concurrently without locking.

---

**Done.** No code or docs were edited. All test counts and evidence lines were captured from real runs / real reads during this audit.
