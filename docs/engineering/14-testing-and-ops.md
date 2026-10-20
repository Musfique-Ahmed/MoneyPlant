# Chapter 14 — Testing, Deployment & Known Gaps

> *Test layers and what each proves, deployment postures, and the gaps the team has
> decided to defer.*

---

## 14.1 The four-layer test stack

Each layer proves something the others cannot.

```
   ┌────────────────────────────────────────────────────────────────┐
   │                                                                │
   │   L1 · Backend unit  (pytest)                                  │
   │        · Engine math is correct to the last decimal            │
   │        · LLM/Laya providers degrade honestly                   │
   │        · Sync connectors contain / sanitise / parse            │
   │        · 219 tests, ~3 seconds                                 │
   │                                                                │
   │   L2 · Frontend unit + component (Vitest + RTL)                │
   │        · Zod mirror parses valid / rejects malformed           │
   │        · Format helpers handle every currency                  │
   │        · Feature components render three fetch states          │
   │        · 42 tests, ~1 second                                   │
   │                                                                │
   │   L3 · TypeScript types (tsc --noEmit)                         │
   │        · Zod mirror and consumer never disagree                │
   │        · Page → hook → util dependency chains are valid        │
   │        · ~0 seconds, runs in every CI invocation               │
   │                                                                │
   │   L4 · E2E (Playwright)                                        │
   │        · Click flow → screen assertion                         │
   │        · 11 user journeys (A–K)                                │
   │        · Last proved-green against a Chromium binary           │
   │          in the developer environment                          │
   │                                                                │
   └────────────────────────────────────────────────────────────────┘
```

The defining property of this stack: **Layer L1 tests all have assertion on real
numeric outputs**, not snapshots. A test like
`test_metrics.py::test_gross_margin` asserts
`m.gross_margin() == "0.2500"`. That assertion is the test.

Tests do not snapshot the dashboard; they assert the engine output. The UI is tested by
the e2e suite, where snapshots add nothing over visible-text assertions.

---

## 14.2 Backend tests — `backend/tests/`

### What they cover

| Area | File | What it asserts |
|---|---|---|
| Money primitives | `test_money.py` | `quantize` per currency, ROUND_HALF_UP, `safe_div_str` for divide-by-zero |
| Periods | `test_periods.py` | Month arithmetic across year boundaries, February 29 |
| Metrics | `test_metrics.py` | `compute_metrics` produces correct revenue / cogs / opex / runway / contribution margin |
| Inventory | `test_inventory.py` | `run_manufacturing`, `run_inventory`, `run_service` |
| Invariants | `test_invariants.py` | Each `InvariantCheck` passes and fails at the right boundary |
| Profit vs cash | `test_profit_vs_cash.py` | Reconciliation under each driver scenario |
| Alerts | `test_alerts.py` | 5 alert codes × thresholds; `evaluate_alerts` empty input → `[]` |
| Financing | `test_financing.py` | Annuity formula in Decimal, DSCR ranking, "no_financing_needed" path |
| Rules | `test_rules.py` | Each of the 8 rules votes the right way; `aggregate_status` precedence |
| LLM providers | `test_llm.py` | Health probe in unavailable / misconfigured / ok; cached explanation path |
| Laya | `test_laya.py` | Heuristic fallback when package is missing |
| Ingestion | `test_ingestion.py` | `parse_rows`, suggestion mapping, encoding detection |
| Sync | `test_sync.py` | Connector path containment, SQL SELECT-only, dedup race with SAVEPOINT |
| Sync scheduler | `test_sync_scheduler.py` | `is_due` rules, daemon start/stop, interval floor |
| Sync CLI | `test_sync_cli.py` | `--all`, `--source`, `--list`, `--dry-run` |
| API endpoints | `test_api.py`, `test_insights_api.py`, `test_financing.py` | Status codes, JSON shapes |
| Insights | `test_insights.py` | `Visual[]` produced from synthetic input |

### Running

```bash
cd backend
.venv/bin/pytest                                  # all 219
.venv/bin/pytest tests/test_rules.py -v           # one file
.venv/bin/pytest -m "not slow"                    # skip markers
.venv/bin/pytest -k "min_cash_reserve"            # name substring
```

Coverage is reported by `pytest-cov` but is not a CI gate — the *quality* of an
assertion beats the line count it covers.

---

## 14.3 Frontend tests — `apps/web/lib/*.test.ts`

### What they cover

| File | What it asserts |
|---|---|
| `lib/format.test.ts` | `formatMoney` per currency, `formatPercent`, `formatDateISO` |
| `lib/schemas.test.ts` | Zod parses valid shapes; rejects drift shapes |

The Vitest configuration (`apps/web/vitest.config.ts`) sets a `jsdom` environment so
React components can mount. Tests are placed co-located (`Foo.tsx` → `Foo.test.tsx`)
when they exist; the smallest two currently live next to the modules they test.

### Running

```bash
cd apps/web
npm run test              # vitest run, ~1s
npm run test:watch        # vitest (interactive)
```

### When a feature component has tests

Some panels (`AlertsPanel.tsx`) export an `_internals` object of helper functions and
constants for testing. This is the on-purpose escape hatch for "I want to test this
constant without spinning up React Testing Library":

```typescript
// AlertsPanel.tsx:126
export const _internals = { formatMoney };
```

Tests can import `_internals` and assert without rendering. The convention is used
sparingly — a component that needs many tests should probably get a co-located
`.test.tsx` instead.

---

## 14.4 E2E tests — `apps/web/e2e/`

Eleven Playwright specs covering the critical user journeys:

| Spec | User journey |
|------|--------------|
| `a-create-business.spec.ts` | A — create workspace, land on dashboard |
| `b-import-csv.spec.ts` | B — CSV upload → preview → commit |
| `c-simulator.spec.ts` | C — run scenario with industry-aware inputs |
| `d-save-and-list.spec.ts` | D — save a scenario, see it in `/scenarios` |
| `e-compare.spec.ts` | E — pick two scenarios, see the side-by-side |
| `f-decision.spec.ts` | F — evaluate a decision, see the verdict |
| `g-explain-decision.spec.ts` | G — error path when no LLM provider |
| `h-assistant.spec.ts` | H — provider status + failed chat |
| `i-privacy-and-error-states.spec.ts` | I — settings privacy + error states |
| `j-dashboard.spec.ts` | J — dashboard interactivity |
| `k-data-sources.spec.ts` | K — connect a source, sync, see dashboard update |

### Running

```bash
cd apps/web
npm run test:e2e                          # all 11
npm run test:e2e -- --project=chromium    # a specific project
npm run test:e2e -- e2e/j-dashboard.spec.ts --headed
```

Playwright browser binaries (`@playwright/test`) are required. See `playwright.config.ts`
for the project matrix and base URL.

### The "Playwright binary missing" caveat

Playwright requires a Chromium / Firefox / WebKit binary that is not bundled with npm.
On machines without it, the suite does not run. CI is the source of truth for green;
local runs are advisory.

---

## 14.5 Deployment posture

The product has two supported deployment shapes (see chapter 02 §2.8):

```
   Shape A — Local / pilot / single box
       uvicorn :8000
       next start :3000
       moneyplant.db
       (optional) Ollama on the same host

   Shape B — Split
       api host: uvicorn :8000, CORS_ORIGINS=[web host], scheduler OFF
       web host: next start :3000, NEXT_PUBLIC_API_BASE_URL=https://api/...
       external cron: scripts.sync_sources --all
       Postgres or SQLite
```

### What a real production deployment adds

| Concern | Recommendation |
|---|---|
| **HTTPS** | Front the API with a reverse proxy (Caddy / nginx / a managed LB). Cert renewal is automated. |
| **Auth** | Out of scope today; see "Known gaps" below. |
| **Database** | Postgres for anything multi-user or >1 GiB of transactions. `DATABASE_URL=postgresql+psycopg://…` |
| **Observability** | `LOG_LEVEL=INFO` default; ship to your log sink. Add `log_redact_financial=True` for any sink. |
| **Backups** | Daily SQLite copy is fine for pilots. For Postgres: managed snapshots or `pg_dump` nightly. |
| **LLM provider** | Ollama stays local; OpenAI / Anthropic mean outbound HTTPS to the provider. Both are covered in `docs/AI_AND_PRIVACY.md`. |
| **Scheduler** | In-process for low-traffic; external cron when you run multiple API instances. |
| **Secrets** | Backend `.env` for keys; `DataSource.secret_ref` is server-only by design. |

### Environment variables that affect production behaviour

```python
# config.py (defaults shown)
DATABASE_URL              = "sqlite:///./moneyplant.db"
CORS_ORIGINS              = "http://localhost:3000"
AI_DEFAULT_MODE           = "local"
OLLAMA_BASE_URL           = "http://localhost:11434/v1"
OLLAMA_MODEL              = "llama3.1:8b"
SYNC_SCHEDULER_ENABLED    = True
SYNC_SCHEDULER_INTERVAL_SECONDS = 300
LOG_REDACT_FINANCIAL      = True
```

There is no command-line flag for any of these. The contract is "config goes in
`backend/.env`" (or a 12-factor equivalent on the host).

---

## 14.6 Configuration patterns

### Decision: backend reads `.env`, frontend reads `.env.local`

```
   backend/.env                 — DB, providers, scheduler, logging
   apps/web/.env.local          — only NEXT_PUBLIC_API_BASE_URL is meaningful
```

`pydantic-settings` reads `backend/.env` with the usual `os.environ` precedence.
Vite-style dotenv is read by Next.js for the frontend. The shapes are different and
intentionally so — the frontend *only* needs the API base URL; everything else is
discovered by hitting the backend.

### Decision: never change a value in `core/config.py` to change runtime behaviour

`Settings` defaults live in code. To change a runtime default, change the default in
`config.py`; do not add new keys without updating both the env template and the docs.
The two env templates (`backend/.env.example`, `apps/web/.env.local.example`) are the
documented surface for env vars.

---

## 14.7 Operational runbook

### Restarting the API

```bash
systemctl restart moneyplant-api    # or whatever supervisor you use
.venv/bin/uvicorn app.main:app --reload --port 8000   # dev

# On startup:
# · The lifespan starts logging + (optionally) the SyncScheduler
# · Frontend queries resume; first request re-warms the engine caches
```

### Inspecting a failed sync

```bash
# List data sources with their last error summary
.venv/bin/python -m scripts.sync_sources --list

# Re-run a single source (returns counters synchronously)
.venv/bin/python -m scripts.sync_sources --source <uuid>

# If a source errored, the row's last_error_summary holds a sanitised code.
# The CONNECTOR LOG (synchronous sync) records the same code + the connector.
```

### Resetting the DB

```bash
cd backend
rm moneyplant.db
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed_demo
```

### Switching to Postgres

```bash
# 1. Update DATABASE_URL
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/moneyplant

# 2. (Re)apply migrations
.venv/bin/alembic upgrade head

# 3. Re-seed (idempotent)
.venv/bin/python -m scripts.seed_demo

# 4. Update SYNC_SQL_DRIVER
SYNC_SQL_DRIVER=postgresql
```

---

## 14.8 Compliance posture (summary)

The full assessment is in [`../SECURITY_SELF_ASSESSMENT.md`](../SECURITY_SELF_ASSESSMENT.md).
Headlines:

- **No authentication.** Pilot product. Honest about this.
- **No model training on user data.** Documented in
  [`../AI_AND_PRIVACY.md`](../AI_AND_PRIVACY.md).
- **Credentials are server-only** in `DataSource.secret_ref`. The field is omitted
  from the wire response and the Zod mirror.
- **Log redaction** is on by default: `log_redact_financial=True` strips Decimal
  shapes from money-ish fields at log-format time.
- **XLSX formulas** are resolved to values at read time (`openpyxl(data_only=True)`).
  No formula string crosses into the database.
- **No stack traces** leave the API. The catch-all handler returns
  `{"detail": "internal_error"}` and logs server-side only.

---

## 14.9 Known gaps and deferred work

These are intentional. Each is a known trade-off, not a surprise.

### No authentication
- The product is single-tenant. A reverse proxy with basic auth is the intended
  boundary.
- Adding auth requires: a user model, an auth flow, refresh tokens, an OIDC/SAML
  adapter — a project of its own.

### `DataSource.secret_ref` is a typed stub
- The field exists on the model and is accepted at create-time.
- The actual credential storage is **not implemented** — it is a string slot.
- Future work: integrate with a secrets manager (Vault, AWS Secrets Manager, etc.)
  and key by `secret_ref`.

### No delete for transactions
- Combined with idempotent-import dedup, a typo is effectively permanent.
- The product team accepts this in exchange for "re-import is safe".
- Future work: a transaction-level delete (admin-only) with audit log entry.

### No data export endpoint
- The transactions, scenarios, and decisions are stored; an export endpoint is not
  implemented.
- All data is queryable through the SQLAlchemy session in the meantime; the simplest
  workaround is a `sqlite3 moneyplant.db ".dump"` for SQLite.

### SQL connector supports SQLite + Postgres only
- MySQL, SQL Server, and Oracle are out of scope.
- The SELECT-only / identifier-whitelist / `statement_timeout` / `LIMIT` plumbing is
  provider-agnostic; adding MySQL is mostly a driver config.

### Symlink traversal test is skipped on Windows
- `tests/test_sync.py::test_file_connector_rejects_path_traversal` exercises a symlink
  that the test runner cannot create without admin on Windows.
- Production hardening is a known gap; the containerisation code is correct for any
  environment that respects `Path.resolve()` semantics.

### Multi-currency comparison is hard-coded to USD
- `compare/page.tsx:146`, `:152` literal `"USD"`. Use of multi-currency businesses in
  compare rows assumes the user is OK with seeing USD numbers.
- Each business picks one currency at creation; the goal is to avoid mixed-currency
  charts. Adding per-row currency to the formatter is a follow-up.

### No Playwright CI green path documented
- The suite is authored and runs locally; green-against-binary in CI is up to the
  hosting environment. See chapter 13 §13.13.

### LLM provider keys not in `.env.example`
- The template deliberately omits key names to discourage accidental commit. The
  names are documented in `docs/AI_AND_PRIVACY.md`.

---

## 14.10 Pre-merge checklist

A non-exhaustive list a reviewer can apply mechanically.

```
   Backend
   ────────
   □ Python 3.11+; no `dict[str, Any]` shape escapes a function signature
   □ Decimal everywhere money is computed
   □ quantize applied after every arithmetic operation
   □ New rule / scenario / alert updates docs/engineering/06 + docs/engineering/05
   □ New ORM column → migration added in same PR, downgrade tested
   □ Service-layer function does not import FastAPI / SQLAlchemy / httpx
   □ Test added for the smallest assertion that proves the change
   □ pytest passes locally; mypy passes locally
   □ Error paths return synthetic codes; nothing leaks credentials / SQL / paths

   Frontend
   ─────────
   □ Zod mirror updated in same PR as backend Pydantic change
   □ lib/schemas.test.ts updated; typecheck passes
   □ Server-state goes through TanStack, not useState+useEffect
   □ Optimistic updates only in chat, never in financial mutations
   □ Three fetch states render (loading / error / empty) — States.tsx
   □ Status shown as text + colour, never colour alone
   □ Synthetic-data banner respected
   □ Print stylesheet hides interactive chrome
   □ Vitest unit / Playwright e2e updated for the journey affected

   Cross-cutting
   ─────────────
   □ docs/engineering/* updated where the file map says it should
   □ .env.example unchanged or extended with a comment
   □ No live secrets in the diff
   □ CHANGELOG entry if there's a CHANGELOG (today: not present; out of scope)
```

---

## 14.11 Where docs live

```
   docs/engineering/      ← this site (system reference)
   docs/PRODUCT_SPEC.md   ← what it is and for whom
   docs/FINANCIAL_MODEL.md← every formula
   docs/AI_AND_PRIVACY.md ← provider + privacy contract
   docs/SECURITY_SELF_ASSESSMENT.md ← threat model + posture
   docs/DESIGN_DECISIONS.md ← UI visual contract
   docs/IMPLEMENTATION_STATUS.md ← what is done / next
   docs/TEST_PLAN.md      ← test strategy in depth
   docs/ARCHITECTURE.md   ← higher-level architecture (legacy)
   docs/DOC_VERIFICATION.md ← claim audit
```

The two clusters are **system** (engineering/) and **concerns** (the rest). Cross-link
from a concern to a chapter when the chapter is the implementation reference.

---

## 14.12 Final words

Three principles carried the codebase this far. They will carry it further.

```
   1. Money is Decimal.
   2. Numbers come from the engine.
   3. Rules decide, the LLM explains.

   With the supporting disciplines:

   4. Failures degrade; they do not lie.
   5. Boundaries fail loudly.
```

When a change feels wrong but you cannot articulate why, walk back through the five
principles in chapter 01. One of them is the cause.

---

*→ [Back to the index](README.md)*