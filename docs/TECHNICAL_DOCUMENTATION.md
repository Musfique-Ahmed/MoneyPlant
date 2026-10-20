# MoneyPlant — Technical Documentation

**Report date:** 2025-XX-XX
**Repository:** `C:\Users\nurep\MoneyPlant`
**Branch:** `Prachurja`
**Commit audited:** `c73ee34`
**Scope:** Backend (`backend/`) + Frontend (`apps/web/`) + supporting scripts and docs

---

## 1. Executive Summary

MoneyPlant is an SME finance copilot delivered as a two-process monorepo:

1. A **FastAPI** backend that owns all persistence (SQLAlchemy 2 + Alembic + SQLite
   by default), runs a deterministic pure-function financial engine, exposes rule-based
   decision verdicts, performs optional LLM explanation, ingests CSV/XLSX, and
   orchestrates incremental data-source syncs.
2. A **Next.js 14 (App Router)** frontend that consumes that API, validates every
   response with Zod, renders TanStack Query-driven pages, and charts backend-computed
   metrics with Recharts.

The defining design principle is **rule-first, deterministic, pure-decimal**:
all financial math runs in `decimal.Decimal`. The LLM is used only to *explain* a
verdict the rule engine has already produced; the rule engine is never replaced by
a model call.

Posture at `c73ee34`:

- **Backend tests:** 226 passed, 1 skipped (`pytest -p no:cacheprovider`)
- **Frontend unit:** 42/42 passed (`npm run test`)
- **Typecheck / lint:** clean
- **E2E:** suite authored (11 journeys, A–K); Playwright binary was missing in the
  audit sandbox, so green-against-binary was not verified.

---

## 2. System Overview

### 2.1 Process model

```
+----------------------+   HTTP/JSON   +-----------------------------------+
|  Next.js 14 frontend |  ───────────► |  FastAPI backend (Uvicorn)       |
|  (apps/web, :3000)   |  ──────────── |  (backend, :8000, /docs enabled) |
+----------------------+               +-----------------------------------+
        │                                          │
        │   TanStack Query                         │   SQLAlchemy 2 + Alembic
        ▼                                          ▼
   Browser cookies (workspace id)               moneyplant.db (SQLite)
                                               sample_data/*.csv,*.xlsx,*.db
```

Two servers run side-by-side. The frontend never opens the database directly; it
talks only to the backend over JSON.

### 2.2 Tech stack

| Layer            | Choice                                                | Evidence |
|------------------|-------------------------------------------------------|----------|
| Backend runtime  | Python 3.11+ (`requires-python = ">=3.11"`); sandbox has 3.12.1 | `backend/pyproject.toml:25` |
| API framework    | FastAPI ≥ 0.110, Uvicorn[standard]                    | `backend/pyproject.toml:28-29` |
| Validation       | Pydantic v2 + pydantic-settings                       | `backend/pyproject.toml:30-31` |
| ORM / migrations | SQLAlchemy 2 + Alembic 1.13                           | `backend/pyproject.toml:32-33` |
| Persistence      | SQLite (`sqlite:///./moneyplant.db`); Postgres-friendly | `backend/app/core/config.py:35` |
| HTTP client      | httpx ≥ 0.27 (used by LLM/Laya adapters)             | `backend/pyproject.toml:36` |
| Data work        | pandas 2.x, openpyxl 3.x                              | `backend/pyproject.toml:37-38` |
| LLM providers    | local Ollama (default), OpenAI, Anthropic            | `backend/app/services/llm/` |
| Soft assessment  | Laya adapter                                          | `backend/app/services/laya/` |
| Tests (backend)  | pytest 8 + pytest-asyncio + pytest-cov                | `backend/pyproject.toml:41-43` |
| Lint / format    | ruff ≥ 0.3, mypy ≥ 1.8                                | `backend/pyproject.toml:45-46` |
| Frontend         | Next.js 14.2.5 (App Router), React 18.3               | `apps/web/package.json:5-6, 23-26` |
| State / cache    | @tanstack/react-query 5, Zustand 4                    | `apps/web/package.json:18, 27` |
| Validation       | Zod 3.23                                              | `apps/web/package.json:26` |
| Charts           | Recharts 2.12                                         | `apps/web/package.json:25` |
| Styling          | Tailwind 3.4 + tailwind.config.ts tokens              | `apps/web/package.json:43` |
| Tests (frontend) | Vitest 1.6 + Testing Library + jsdom                  | `apps/web/package.json:31-45` |
| E2E              | @playwright/test 1.44                                 | `apps/web/package.json:30` |

### 2.3 Runtime requirements (Windows)

- **Python 3.11+** — the repo carries a 3.11 venv at `backend/.venv` (the audit
  shell's available interpreter is 3.12.1, which satisfies the floor).
- **Node.js 18+** — Node 24.16.0 / npm 11.13.0 in the audit env. `package.json`
  declares React 18.3 and Next 14.2.
- **Sufficient disk** for `node_modules` (≈400 MB) + `backend/.venv` (~700 MB).
- **Optional:** Ollama at `http://localhost:11434/v1` for the default LLM
  provider (`ai_local_base_url`); Laya model name + device for soft assessment.
- **Outbound:** OpenAI / Anthropic are only used if `OPENAI_API_KEY` /
  `ANTHROPIC_API_KEY` are set in `backend/.env`.
- **OS:** Windows / macOS / Linux. The repo path includes a space (`F:\Git Repo\MoneyPlant`
  or the local equivalent) — shell commands must quote paths.

---

## 3. Backend Architecture

### 3.1 Layout (`backend/app/`)

```
api/          FastAPI routers — one per feature; each file declares an APIRouter
core/         config (settings), logging, currency utils
db/           SQLAlchemy session + declarative base + mixins
models/       ORM tables (Business, Transaction, Scenario, ScenarioVersion,
              DecisionReport, LlmExplanation, ImportJob, DataSource, SyncRun)
schemas/      Pydantic v2 request / response models
engine/       pure-function Decimal engine — alerts, financing, profit-vs-cash
services/
  finance/    money (Decimal utilities), periods, metrics, inventory, invariants,
              profit_vs_cash
  decisions/  orchestrator wiring rule engine + Laya + LLM
  rules/      engine.py + aggregator (hard-first precedence)
  llm/        base + provider registry: local/Ollama, OpenAI, Anthropic
  laya/       adapter (heuristic fallback if laya import fails)
  ingestion/  csv_parser, xlsx_parser, mapper, commit_import, encoding detect
  simulation/ runner + sensitivity analysis
  sync/       connectors/{file,sql}_connector + service + scheduler
main.py       FastAPI app + lifespan (scheduler start/stop) + router wiring
```

### 3.2 Data layer

- **SQLAlchemy 2 declarative**, with mixins for UUID primary keys + `created_at` /
  `updated_at` timestamps (`backend/app/db/base.py`).
- **Alembic** for migrations. Current revisions (at `c73ee34`):
  `0001_initial`, `0002_data_sources`, `0003_sync_dedup_columns`
  (`backend/alembic/versions/`).
- **Models:**
  - `Business` — workspace + per-business tuning (`min_cash_reserve`,
    `target_operating_margin`, `max_unsold_inventory_exposure_pct`).
  - `Transaction` — every imported/synced row; carries `source_row_hash` and
    `data_source_id` once the data-sources feature landed.
  - `Scenario`, `ScenarioVersion` — append-only scenario history.
  - `DecisionReport`, `LlmExplanation` — decision outputs and explanations.
  - `ImportJob` — import history (filename, mapping JSON, sheet name, status).
  - `DataSource` — connected source definitions (`type ∈ {file, sql}`,
    `name`, JSON `config`, `enabled`, `schedule`, watermarks).
  - `SyncRun` — per-run counters (`rows_read`, `rows_added`,
    `rows_skipped_duplicate`, `rows_rejected`) and `error_summary`.
- **Unique index** `uq_transactions_business_source_row_hash` guards idempotency.

### 3.3 Pure-decimal financial engine

`backend/app/engine/` is the heart of the product. Every entry point is a pure
function on `decimal.Decimal`; no I/O, no globals.

- **`alerts.py`** — evaluates 5 codes against a monthly closing-cash series and
  headline metrics (`runway_months`, `operating_profit`):

  | Code                       | Severity  | Trigger |
  |----------------------------|-----------|---------|
  | `NEGATIVE_CASH`            | CRITICAL  | Closing cash `< 0` at any month |
  | `LOW_BUFFER`               | WARNING   | Closing cash `< N` months of avg opex |
  | `SHORT_RUNWAY`             | CRITICAL/WARNING | `runway < 1mo` / `< 3mo` |
  | `PROFITABLE_BUT_CASH_POOR` | WARNING   | Positive profit but closing cash fell below opening |
  | `SHARP_DROP`               | INFO      | Month-over-month closing-cash fall `> 25%` |

  Configurable thresholds live in `AlertConfig`.

- **`financing.py`** — given a (synthetic) lender catalog and engine metrics,
  returns a ranked list of financing matches:
  - Hard rules first: zero shortfall → `no_financing_needed` sentinel; failed
    eligibility → `not_recommended`; DSCR `< min_dscr` (default **1.2**) →
    `not_recommended`. Default DSCR floor (`1.2`) at `app/engine/financing.py:124`
    is **stricter than the rule-engine's `MIN_PROFIT_MARGIN` floor of 1.0**.
  - Ranking within `possible`/`recommended`: highest DSCR, then closest
    mid-point of amount range.
  - Math: standard amortising-loan annuity in `Decimal`, ROUND_HALF_UP
    (`_annuity_monthly_payment`).

- **`services/finance/`** — building blocks:
  - `money.py` — `Decimal` quantisation per currency precision, safe
    string formatting, `same_currency`, parsers.
  - `periods.py` — `MonthlyPeriod`, `shift_months`, `months_between`
    (calendar-correct month arithmetic).
  - `metrics.py` — `compute_metrics()`, the engine's core routine that returns
    revenue, cogs, opex, operating profit, contribution margin, runway months,
    cash inflection, inventory overhead. Also defines the typed `Transaction`
    the engine operates on (`metrics.py:28`), with category classifiers
    (`REVENUE_CATEGORIES`, `DIRECT_COST_CATEGORIES`, …).
  - `inventory.py` — `ManufacturingInputs` / `ManufacturingResult`,
    per-unit margin.
  - `profit_vs_cash.py` — `reconcile_profit_and_cash`, the function that
    powers the "Profitable but cash-poor" alert.
  - `invariants.py` — `assert_invariants` (zero-balance identity, revenue ≡ units ×
    price, materials balance); used by tests to guarantee engine consistency.

### 3.4 Rule-first decision engine

`backend/app/services/rules/engine.py` defines seven rules, each a pure function
returning a `RuleEvaluation` with `rule_id`, `severity` (`HARD`/`SOFT`),
`status` (`PASSED`/`BREACHED`/`INSUFFICIENT`), and `detail`:

- `MIN_CASH_RESERVE` (HARD), `NEGATIVE_CLOSING_CASH` (HARD),
  `MIN_PROFIT_MARGIN` (SOFT), `NEGATIVE_CONTRIBUTION_MARGIN` (SOFT),
  `MATERIAL_SHORTAGE` (HARD), `CAPACITY_EXCEEDED` (HARD),
  `UNSOLD_INVENTORY_EXPOSURE` (SOFT), `MISSING_CRITICAL_DATA` (BLOCKER).

`aggregate_status` precedence in `engine.py:438-460`:

1. Any **HARD** `BREACHED` → `reject`.
2. `≥ ½` of rules return `INSUFFICIENT` → `insufficient_data`.
3. Any **SOFT** warning → `proceed_with_caution`.
4. All pass → `proceed`.

`backend/app/services/decisions/evaluator.py:64-77` renders this into user-facing
copy. LLM explanations (`/decisions/{id}/explain`) are dispatched only after the
verdict exists — the LLM explains, never decides.

### 3.5 LLM providers

`backend/app/services/llm/` exposes a `BaseProvider` with `explain()` /
`health_check()` / `get_capabilities()`. Implementations:

| Mode        | Class              | Backend                                  |
|-------------|--------------------|------------------------------------------|
| `local`     | `LocalProvider`    | Ollama at `ai_local_base_url` (default `http://localhost:11434/v1`, model `llama3.1:8b`) |
| `openai`    | `OpenAIProvider`   | `OPENAI_API_KEY`; `openai>=1.30` client  |
| `anthropic` | `AnthropicProvider`| `ANTHROPIC_API_KEY`                      |

Selection is via `ai_default_mode` in `backend/.env`. `AiHealthProbe` returns
`ok` *only* when a real probe succeeded; otherwise `unavailable` / `misconfigured`
with a reason (the schema never has a silent green tick).

The `ExplanationContext` payload (`backend/app/services/llm/base.py:62-75`) fixes
the field set sent to the model: `business_industry, reporting_period,
user_question, computed_baseline, computed_scenarios, rule_evaluations,
laya_assessment, assumptions, missing_information, business_goal`.

### 3.6 Ingestion pipeline

`backend/app/services/ingestion/` is reused by both manual CSV/XLSX import and
the data-source sync service. The pipeline:

1. Detect extension + size (`upload_max_bytes = 10 MiB`).
2. Sniff encoding (UTF-8 → UTF-8-sig → latin-1 + `errors="replace"`).
3. Preview headers, suggest canonical mapping (`mapper.py`).
4. `validate` rows on the same parser rules used at commit time.
5. `commit_import` in one transaction; on unique-hash conflict the row is
   counted as duplicate, not as an error.

The DataSource + SyncRun path *reuses* `parse_rows_for_sync` so CSV/XLSX rules
apply identically (`services/sync/service.py`).

### 3.7 Connected data sources + sync

`backend/app/services/sync/` provides incremental syncing.

- **Connector contract** (`connectors/base.py`): `read_rows(...)` returns an
  `iterable[Mapping]` plus optional metadata.
- **File connector** (`file_connector.py`):
  - Containerises the path under `settings.file_source_root` (`./sample_data`
    by default) and **rejects path traversal / symlink escapes** via
    `Path.resolve(strict=False)` + `is_relative_to` checks.
  - Reads `.csv` via the same parser as manual imports; `.xlsx` via
    `openpyxl(..., data_only=True)` — formulas are resolved to values, never
    carried forward.
  - Computes `file_content_sha256` for incremental gating.
- **SQL connector** (`sql_connector.py`):
  - Accepts only **SELECT** statements — verified via SQLAlchemy `inspect()`
    on the compiled statement; any DML/DDL raises `SqlSourceError`.
  - Parameterised: literals via `bindparam`; identifiers (`column`,
    `schema_name`, `table_name`) flow through SQLAlchemy text quoting with
    `_IDENT_RE` whitelisting.
  - Wraps each connection with a **statement timeout** (`PRAGMA timeout=`
    on SQLite, `SET statement_timeout` on Postgres) and a **row limit**
    (`sync_sql_row_limit`, default 50 000) — the LIMIT clause is appended
    *only* after the statement is proven to be SELECT and the FROM-clause
    is a single recognised source.
  - Driver support: SQLite + Postgres (configurable via `sync_sql_driver`).
- **Sync service** (`service.py`):
  - Builds the right connector.
  - Maps raw rows through the user-confirmed `column_mapping` and reuses the
    engine's `parse_rows_for_sync`.
  - **Dedup by SHA-256** on the canonical tuple, against an in-memory set of
    existing hashes plus the DB unique index
    `uq_transactions_business_source_row_hash`.
  - Persists inserts inside a **SAVEPOINT** (`db.begin_nested()`) so a
    unique-constraint race rolls back only the colliding row, not the whole
    transaction.
  - Records a `SyncRun` with counters (`rows_read`, `rows_added`,
    `rows_skipped_duplicate`, `rows_rejected`) and update watermarks.
  - All error strings written to `SyncRun.error_summary` /
    `DataSource.last_error_summary` are **synthetic codes** — they never
    echo the raw URL, file path outside the configured root, or password.
- **Background scheduler** (`scheduler.py`):
  - Daemon thread started by FastAPI lifespan when
    `sync_scheduler_enabled=True`. Default interval
    `sync_scheduler_interval_seconds=300`, with a `min` of 30s.
  - `is_due()` picks sources whose `enabled=true` and whose
    `schedule` (interval + last_sync_at) indicates they're due.
  - Stops cleanly on FastAPI shutdown.
- **CLI** (`scripts/sync_sources.py`):
  - `--all` (per business), `--source <id>`, `--list`, `--dry-run`.
  - Designed to be wired into Windows Task Scheduler / cron for sites that
    prefer not to run the in-process scheduler.
- **Demo data** (`scripts/simulate_daily_data.py`):
  - Appends a deterministic "today" of synthetic invoices to
    `sample_data/ext_invoices.db` and additional rows to
    `sample_data/daily_transactions.xlsx`.

### 3.8 REST surface

The following routers (each defined under `backend/app/api/`) are mounted under
`/api/`:

| File            | Prefix          | Endpoints (method + path) |
|-----------------|-----------------|----------------------------|
| `businesses.py` | `/businesses`   | `GET ""`, `POST ""`, `GET/PATCH/DELETE {business_id}` |
| `transactions.py` | `/transactions` | `GET /transactions`, `GET /transactions/categories`, `GET /financial-summary` |
| `scenarios.py`  | `/scenarios`    | `POST /simulate`, `POST /simulate/sensitivity`, `GET ""`, `POST ""`, `GET {scenario_id}`, `GET {scenario_id}/versions`, `POST {scenario_id}/rerun`, `POST /compare` |
| `decisions.py`  | `/decisions`    | `POST /evaluate`, `GET ""`, `GET {report_id}`, `POST {report_id}/explain` |
| `imports.py`    | `/imports`      | `POST /preview`, `POST /validate`, `POST /commit`, `GET ""`, `GET {job_id}`, `GET /fields/canonical` |
| `ai.py`         | `/ai`           | `GET /providers`, `GET /health`, `POST /assistant/chat` |
| `alerts.py`     | `/businesses`   | `GET {business_id}/alerts` |
| `financing.py`  | `/businesses`   | `GET {business_id}/financing-options` |
| `insights.py`   | `/businesses`   | `GET {business_id}/dashboard-insights` |
| `data_sources.py` | `/sources`    | `GET/POST ""`, `GET/PATCH/DELETE {source_id}`, `POST {source_id}/test`, `POST {source_id}/sync`, `GET {source_id}/runs` |
| (same file, secondary router) | `/businesses` | `GET {business_id}/freshness` |

`GET /api/config/public` exposes safe boolean flags only — no secrets
(`backend/app/api/config.py`). `/docs` and `/redoc` are enabled for development.

---

## 4. Frontend Architecture

### 4.1 Routing

Next.js 14 App Router. Top-level layout in `apps/web/app/layout.tsx`. The
authenticated application lives in the `(app)` route group:

```
apps/web/app/(app)/
  layout.tsx           (sidebar + workspace context)
  dashboard/page.tsx   interactive insights + freshness strip
  data/page.tsx        full data-source CRUD + import pipeline
  simulator/page.tsx   scenario inputs + result panel
  decisions/page.tsx   decision list + verdict + explanation
  compare/page.tsx     side-by-side scenario compare
  financing/page.tsx   financing-options panel (synthetic catalog)
  assistant/page.tsx   LLM chat (graceful "unavailable" empty state)
  settings/page.tsx    privacy / provider status / business CRUD
```

Outside the group: `apps/web/app/page.tsx` (landing redirect) and any future
public routes.

### 4.2 State, data, validation

- **TanStack Query** owns all server-state fetches via `lib/api.ts` (`apiGet`
  / `apiPost` / `apiDelete`).
- **WorkspaceContext** holds the active business id; sidebar selects among
  workspaces.
- **Zod mirrors** in `apps/web/lib/schemas.ts` validate every API response —
  Pydantic is the source of truth, Zod is the client-side mirror; drift is
  caught loudly at runtime.
- **Tailwind** tokens from `tailwind.config.ts` (`accent`, `surface-*`,
  `ink-*`, `line`, `ok`, `warn`, `bad`). Reusable primitives in
  `apps/web/components/ui/`.

### 4.3 Dashboard

`apps/web/app/(app)/dashboard/page.tsx` now renders the interactive dashboard
built from `apps/web/components/dashboard/`:

- `FreshnessStrip.tsx` — last-sync freshness per data source.
- Other panels: cash trajectory, runway, monthly P/L summary, top expense
  categories, scenario residuals, alerts and a financing-options sidebar.
- Each visual pairs its chart with a **plain-English interpretation** that
  sits next to the figure (the rationale the user asked for in the previous
  turn). Every chart is a Recharts primitive (AreaChart, BarChart, LineChart,
  ComposedChart, RadialBarChart).
- TanStack Query keys are computed per business id, so panel refresh after a
  sync is automatic.

### 4.4 Data-sources page

`apps/web/app/(app)/data/page.tsx` is the CRUD page for DataSource rows:

- List + create form.
- Edit dialog (only "name", "schedule", "enabled" are user-editable post-create
  — `secret_ref` is server-managed).
- `Test connection` button (hits `POST /sources/{id}/test`).
- `Sync now` button (hits `POST /sources/{id}/sync`).
- Recent `SyncRun`s per source with counters + status.

The page reuses the upload pipeline that lived there before; nothing was
duplicated.

### 4.5 Decisions + assistant + settings

- **Decisions** — list, detail, "Explain with LLM" (graceful "unavailable"
  fallback when no provider is healthy).
- **Compare** — pairs scenario results side-by-side.
- **Assistant** — chat against the active LLM provider; clean empty state
  when no provider is healthy (`i-privacy-and-error-states.spec.ts`,
  `h-assistant.spec.ts`).
- **Settings** — business CRUD, provider status, privacy copy, "delete business"
  destructive action (DELETE `/api/businesses/{id}` was added before the audit;
  docs previously said "no data deletion" — see `DOC_VERIFICATION.md` claim D-2).

### 4.6 Tests

- **Unit/component** — Vitest + Testing Library + jsdom. Suite per component /
  hook. Coverage: business CRUD, import preview/commit, alerts/financing panels,
  Zod schemas, decision verdict rendering, assistant fallback.
- **E2E** — Playwright. Authored journeys A–K:
  | Spec | Journey |
  |------|---------|
  | `a-create-business.spec.ts` | A — create workspace, land on dashboard |
  | `b-import-csv.spec.ts` | B — CSV import end-to-end |
  | `c-simulator.spec.ts` | C — run scenario |
  | `d-save-and-list.spec.ts` | D — save and re-list |
  | `e-compare.spec.ts` | E — compare two scenarios |
  | `f-decision.spec.ts` | F — evaluate decision + open report |
  | `g-explain-decision.spec.ts` | G — explain-with-LLM error path |
  | `h-assistant.spec.ts` | H — provider status + failed chat |
  | `i-privacy-and-error-states.spec.ts` | I — settings privacy page |
  | `j-dashboard.spec.ts` | J — dashboard renders insights + interactivity |
  | `k-data-sources.spec.ts` | K — connect + sync + see dashboard update |

  Playwright binary was missing in the audit sandbox; suite was not executed
  green-against-binary in `c73ee34`. CI or a developer with the browser
  installed must run it before merge.

---

## 5. Financial Model Highlights

- **Decimal everywhere.** `Numeric(20, 4)` SQL columns, `Decimal` arguments,
  quantised to currency precision (2 dp for USD, configurable per currency).
- **Categories.** `REVENUE_CATEGORIES`, `DIRECT_COST_CATEGORIES`, `OPEX_CATEGORIES`
  — `metrics.py:45-65`. Heuristic unmapped; user can override on import mapping.
- **Direction inference.** `parse_amount_with_direction()` reads an explicit
  `direction` column first; otherwise positive amount, no direction → `inflow`
  by default.
- **Cash vs. accrual reconciliation.** `profit_vs_cash.reconcile_profit_and_cash`
  decomposes the gap between reported profit and movement of cash.
- **Alerts.** Five deterministic codes over a monthly cash series; thresholds in
  `AlertConfig`; the engine never raises — empty input returns `[]`.
- **Financing.** Annuity repayment in Decimal + DSCR ranking. DSCR floor default
  `1.2` (`app/engine/financing.py:124`). The synthetic catalog has no PII; users
  are told that real catalog wiring is out of scope and the synthetic numbers
  must never be presented as actual offers.

---

## 6. Privacy & Security Posture (see Security Report for full audit)

`docs/AI_AND_PRIVACY.md` is the canonical document. Headlines:

- **No authentication.** Pilot product; documented honestly.
- **No model training on user data.** Updated FAQ in `c73ee34`:
  - Local Ollama: never phones home.
  - OpenAI/Anthropic: subject to each provider's data-use policy.
- **Credentials storage.** DataSource credentials live as `secret_ref` server-side
  and are *never* surfaced in `DataSourceRead` (Zod mirror omits the field).
  Storage of the actual secret remains a future task; today the field is a stub.
- **Log redaction.** `log_redact_financial = True` strips Decimal money strings
  at log format time.
- **CSV / XLSX ingestion.** Same parser, same validation; XLSX is read with
  `data_only=True` so Excel formulas never cross the boundary.

---

## 7. Local Run (developer quickstart)

From the repo root on Windows PowerShell:

```powershell
# 1. Backend deps + DB schema
cd "C:\Users\nurep\MoneyPlant\backend"
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\python.exe -m scripts.seed_demo   # idempotent

# 2. Backend dev server (foreground)
.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000

# 3. Frontend deps + dev server (new terminal)
cd "C:\Users\nurep\MoneyPlant\apps\web"
npm install
npm run dev
# open http://localhost:3000
```

What each step does:

| Command                               | What it does |
|---------------------------------------|--------------|
| `alembic upgrade head`                | Apply all Alembic migrations to `moneyplant.db`. Creates tables / indexes. |
| `python -m scripts.seed_demo`         | Inserts 5 demo businesses (one per industry) + sample transactions + baseline scenarios. Skips by `(name, industry)` so it is safe to re-run. |
| `uvicorn app.main:app --reload`       | Starts FastAPI with auto-reload on `:8000`. Creates the SQLAlchemy schema on first boot if `Base.metadata.create_all` is the chosen path (migrations are the source of truth; `create_all` is a fallback). Also starts the sync scheduler if enabled. |
| `npm install`                         | Installs frontend deps into `node_modules/`. |
| `npm run dev`                         | `next dev -p 3000`. Hot reload. |

Verify:

```powershell
curl http://localhost:8000/docs                 # Swagger UI loads
curl http://localhost:3000/                     # Next.js lands
curl http://localhost:8000/api/ai/providers     # JSON list of providers
```

---

## 8. Optional Services

| Service                  | When needed                                                                 | Setup |
|--------------------------|-----------------------------------------------------------------------------|-------|
| **Local Ollama**         | Default LLM provider. Without it, `AiHealthProbe` returns `unavailable` and the Assistant shows an empty-state hint — the rest of the product still works. | Install Ollama; `ollama pull llama3.1:8b`; set `AI_DEFAULT_MODE=local`. |
| **OpenAI**               | If you want a hosted provider.                                              | Set `AI_DEFAULT_MODE=openai` and `OPENAI_API_KEY` in `backend/.env`. |
| **Anthropic**            | If you want Claude as the explainer.                                        | Set `AI_DEFAULT_MODE=anthropic` and `ANTHROPIC_API_KEY`. |
| **Laya**                 | Optional soft assessment on `DecisionReport`. Falls back to heuristics if the import is missing. | `pip install laya`; set `LAYA_MODEL=…`, `LAYA_DEVICE=cpu|cuda|mps|xpu`. |
| **Background scheduler** | In-process daemon that wakes every `sync_scheduler_interval_seconds` to run due sources. | `SYNC_SCHEDULER_ENABLED=true` (default). |
| **External sync CLI**    | For sites that prefer an external scheduler (Windows Task Scheduler, cron). | `python -m scripts.sync_sources --all` or `--source <id>`. |
| **PostgreSQL**           | If you swap SQLite for Postgres.                                            | `DATABASE_URL=postgresql+psycopg://…`; `sync_sql_driver=postgresql`. |

---

## 9. Quality Posture

- **Backend tests:** 226 passed, 1 skipped
  (`backend/tests/test_sync.py::test_file_connector_rejects_path_traversal` is
  the skip; it exercises a symlink that cannot be created without admin on
  Windows). Coverage spans money utilities, periods, metrics, inventory,
  invariants, CSV/XLSX parsing, mapping, commit, alerts (5 codes × thresholds),
  financing (annuity + DSCR + ranking + DSCR floor), decision aggregation,
  LLM providers (incl. graceful "unavailable"), Laya (heuristic fallback),
  schemas, sync (connectors + service + scheduler + CLI), and import
  idempotency.
- **Frontend tests:** 42/42 passed (`apps/web/lib/schemas.test.ts` etc.).
- **Typecheck:** clean.
- **Lint:** clean.
- **E2E:** authored; Playwright binary missing in audit env.

---

## 10. Known Limitations (excerpt; full list in `docs/IMPLEMENTATION_STATUS.md`)

- No authentication / single-user pilot.
- SQL connector supports SQLite + Postgres only (not MySQL/SQL Server).
- DataSource `secret_ref` is a typed stub — real credential storage is future
  work.
- No DELETE for transactions (combined with idempotent-import dedup, a typo is
  effectively permanent).
- No data-export endpoint.
- Playwright suite not validated against a real browser in the audit.

---

## 11. Operational Notes

- **Logs.** `log_redact_financial=True` strips monetary values from logs.
  `LOG_LEVEL` controls verbosity (`INFO` default).
- **Migrations.** Add a new file under `backend/alembic/versions/`. Always
  run `alembic upgrade head` then `alembic downgrade -1` (and back) locally to
  verify reversibility.
- **Sync watermarks.** `DataSource.last_sync_at`,
  `DataSource.incremental_value`, `DataSource.file_content_sha256`. Idempotent
  re-runs by design.
- **Env files.** `backend/.env` is gitignored. `backend/.env.example` is the
  template. Frontend reads `NEXT_PUBLIC_API_BASE_URL` only.
