# MoneyPlant — SME Finance Copilot

GitHub Link: https://github.com/Musfique-Ahmed/MoneyPlant

A privacy-aware financial decision copilot for small and medium-sized enterprises. Import records, simulate operating decisions, compare scenarios, and understand the risks and trade-offs of a proposed action.

The repository runs end-to-end: a FastAPI backend that owns all financial math (`Decimal` everywhere, never `float`), a Next.js 14 frontend that renders the engine's output, an idempotent sync layer for CSV/XLSX files and read-only SQL sources, a deterministic 8-rule decision engine with HARD-first precedence, a Laya soft-assessment adapter, and an LLM layer that **only explains** verdicts (never computes them).

> **Authoritative documentation:** [`docs/engineering/`](docs/engineering/README.md) — the system reference, written from the code and kept alongside the index page below.
>
> **Other docs (concerns, not implementation):**
> [`PRODUCT_SPEC`](docs/PRODUCT_SPEC.md) ·
> [`FINANCIAL_MODEL`](docs/FINANCIAL_MODEL.md) ·
> [`AI_AND_PRIVACY`](docs/AI_AND_PRIVACY.md) ·
> [`SECURITY_SELF_ASSESSMENT`](docs/SECURITY_SELF_ASSESSMENT.md) ·
> [`DESIGN_DECISIONS`](docs/DESIGN_DECISIONS.md) ·
> [`IMPLEMENTATION_STATUS`](docs/IMPLEMENTATION_STATUS.md) ·
> [`TEST_PLAN`](docs/TEST_PLAN.md)

---

## What MoneyPlant does

- **CSV / XLSX import** with column-mapping, per-row validation, and import history.
- **Financial dashboard** driven by backend-computed metrics — the frontend never fabricates a number. Six charts (KPI strip, revenue/costs/profit, cash balance, profit–cash gap, cost breakdown, sensitivity) every visual has a deterministic, pure-function text interpretation next to it. No LLM by default. Every quoted figure is verifiable in the matching `evidence` dict.
- **Five cash-flow alert codes** — `NEGATIVE_CASH`, `LOW_BUFFER`, `SHORT_RUNWAY`, `PROFITABLE_BUT_CASH_POOR`, `SHARP_DROP`. Text-label severities (Critical / Warning / Info), never colour-only signalling.
- **Financing-option matching** — a SYNTHETIC catalog of illustrative products matched against the business's revenue, runway, and projected shortfall. Hard eligibility + DSCR floor override ranking. Not a credit decision. The UI banner is always `Illustrative products. Not a credit decision.`
- **Connected data sources** — CSV/XLSX from a configured allowed root, or a SQL table described by an env-var name. Idempotent re-sync (SHA-256 `source_row_hash` dedup, DB-level unique index), per-source run history with rows-added / skipped-as-duplicate / rejected counters, a background daemon scheduler, and CLI tooling for Windows Task Scheduler / cron. Credentials are stored only as env-var names; the value never leaves the server. **No model is ever trained on your data** — a sync triggers deterministic recomputation.
- **Production and operating simulator** with industry-specific inputs for manufacturing, retail, service, wholesale, and food.
- **Scenario save, rerun, compare** with versioned, reproducible results. Scenarios are append-only; `ScenarioVersion(version_number=N+1)` never mutates N.
- **Rule-based decision engine** — eight deterministic rules, hard-constraint precedence. Laya is advisory and cannot override hard rules. The LLM is a separate `/api/decisions/{id}/explain` endpoint that **only explains** the verdict; it cannot fabricate the verdict.
- **Decision report** with assumptions, caveats, calculation timestamp, and printable layout (print stylesheet strips interactive chrome).
- **AI assistant** grounded in computed results (the chat is given an `ExplanationContext` that deliberately excludes raw transactions).
- **Five industry profiles** seeded with clearly-labeled synthetic data — manufacturing, retail, service, wholesale, food.

---

## Architecture in one diagram

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │  apps/web/   Next.js 14 · App Router · React 18 · TanStack Query · Zod │
   │              UI renders server-computed numbers. It owns no number.     │
   │                                       │                                 │
   │                                       │  HTTP/JSON (Zod-validated)     │
   │                                       ▼                                 │
   │  backend/      FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic          │
   │   ├─ routers   api/  (41 endpoints under /api)                          │
   │   ├─ services  finance (Decimal math) │ rules (8-rule engine) │ llm    │
   │   │           laya │ simulation │ ingestion (CSV/XLSX) │ sync          │
   │   └─ db        SQLite (default) or Postgres                              │
   └────────────────────────────────────────────────────────────────────────┘
```

Full architecture, sequence diagrams, and per-layer ownership are in [`docs/engineering/02-system-architecture.md`](docs/engineering/02-system-architecture.md).

---

## Tech stack

| Layer | What | Where |
|---|---|---|
| Frontend | Next.js 14.2 (App Router) · TypeScript 5.5 · React 18 · Tailwind 3.4 · TanStack Query 5 · Zod 3 · Recharts 2 | `apps/web/package.json` |
| Backend | Python ≥ 3.11 · FastAPI ≥ 0.110 · Pydantic v2 ≥ 2.6 · SQLAlchemy 2 ≥ 2.0 · Alembic ≥ 1.13 · openpyxl ≥ 3.1 · pandas ≥ 2.1 · httpx · python-dotenv | `backend/pyproject.toml` |
| Database | SQLite (default, `sqlite:///./moneyplant.db`) · Postgres via `DATABASE_URL=postgresql+psycopg://…` | `backend/app/core/config.py:35` |
| Decisions | 8-rule engine + Laya adapter (`≥ 0.4.11`) | `backend/app/services/rules/engine.py` · `laya/` |
| LLM | Ollama (local · default) · OpenAI · Anthropic, behind one provider interface | `backend/app/services/llm/{ollama,openai,anthropic}_provider.py` |
| Tests | pytest ≥ 8 (219 backend) · Vitest ≥ 1 (42 frontend) · Playwright ≥ 1.44 (11 e2e) | `backend/tests/` · `apps/web/{lib,e2e}/` |

The full layout, every dependency with its version constraint, and a "where to make changes" table are in [`docs/engineering/03-stack-and-layout.md`](docs/engineering/03-stack-and-layout.md).

---

## Prerequisites

| Tool | Required | Notes |
|---|---|---|
| Python 3.11+ | yes | enforced in `pyproject.toml`; 3.12 also works |
| Node.js 18+ (20+ recommended) | yes | Next.js 14 minimum |
| npm 10+ | yes | ships with Node |
| uv | yes | manages the isolated `backend/.venv` (`pip` fails on the host Python 3.14) |
| Ollama | optional | default LLM provider · without it, `/api/ai/health` returns `unavailable` and the rest of the product still works |
| OpenAI / Anthropic keys | optional | only needed if you swap providers |

---

## First-time setup

From the repo root (`F:\Git Repo\MoneyPlant`, or `/mnt/f/Git\ Repo/MoneyPlant` in WSL — the repo path contains a space; quote it in shell).

### Backend

```bash
cd backend
uv venv --python 3.11 .venv                # creates an isolated Python 3.11 venv
source .venv/bin/activate                  # macOS / Linux / WSL
# or  .venv\Scripts\activate               # Windows PowerShell
uv pip install -e ".[dev]"
cp .env.example .env                       # edit if you need to change defaults
.venv/bin/alembic upgrade head             # apply migrations
python -m scripts.seed_demo                # idempotent — 5 demo businesses
```

`scripts/seed_demo.py` lives at the **repo root**, not inside `backend/`. The convention is `cd backend` → run `python -m scripts.seed_demo` (because `scripts` is on sys.path via `pyproject.toml`), or alternatively `python ../scripts/seed_demo.py` from inside `backend/`.

### Frontend

```bash
cd apps/web
npm install
cp .env.local.example .env.local           # only NEXT_PUBLIC_API_BASE_URL is meaningful
```

---

## Run the app (development)

Two terminals:

```bash
# Terminal 1 — backend (uvicorn with --reload picks up code changes)
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd apps/web
npm run dev
```

Open <http://localhost:3000>. The backend's OpenAPI docs are at <http://localhost:8000/docs>. Verify each side independently:

```bash
curl http://localhost:8000/api/health         # {"status": "ok"}
curl http://localhost:8000/docs               # Swagger UI loads
```

A third terminal for the test loop is recommended — see [`docs/engineering/13-local-runbook.md` §13.10](docs/engineering/13-local-runbook.md).

---

## Environment

Copy `backend/.env.example` to `backend/.env` and `apps/web/.env.local.example` to `apps/web/.env.local`. **Never commit a real `.env`** — both files are gitignored.

The minimum backend `.env`:

```dotenv
DATABASE_URL=sqlite:///./moneyplant.db
CORS_ORIGINS=http://localhost:3000

AI_DEFAULT_MODE=local
AI_LOCAL_BASE_URL=http://localhost:11434/v1
AI_LOCAL_MODEL=llama3.1:8b

SYNC_SCHEDULER_ENABLED=true
SYNC_SCHEDULER_INTERVAL_SECONDS=300

LOG_LEVEL=INFO
LOG_REDACT_FINANCIAL=true
```

Anything missing falls back to the `Settings` defaults in `backend/app/core/config.py`. The canonical env-var surface is documented in [`docs/engineering/13-local-runbook.md` §13.7](docs/engineering/13-local-runbook.md) and [`docs/engineering/14-testing-and-ops.md` §14.5–14.6](docs/engineering/14-testing-and-ops.md).

---

## Demo data

Five **clearly-labelled synthetic** businesses are seeded by `scripts/seed_demo.py`, one per industry. The seed is idempotent — running it again skips businesses that already exist `(name, industry)`.

| Business | Industry | CSV | Hooked scenario |
|---|---|---|---|
| Aurora Garments (demo) | manufacturing | `clothing_demo.csv` | raw materials + labor + capacity + a `material_shortage` scenario |
| Main Street Boutique (demo) | retail | `retail_demo.csv` | inventory + shrinkage |
| Helios Consulting (demo) | service | `service_demo.csv` | billable hours + project revenue + invoice delay |
| Pioneer Distribution Co. (demo) | wholesale | `wholesale_demo.csv` | high inventory exposure + supplier payment delay |
| Maple Street Eatery (demo) | food | `food_demo.csv` | retail-like shape with tighter expiry |

The full mapping is in [`sample_data/README.md`](sample_data/README.md). The dashboard banner is always shown for these workspaces ("This workspace is showing clearly-labelled synthetic data"); a real user who imports real data never sees a banner.

---

## Connected data sources (automatic updates)

MoneyPlant supports a `file` data source (a CSV/XLSX file from a configured allowed root) and a `sql` data source (a read-only DB table — SQLite or Postgres — described by an env-var name). Both are incremental and idempotent.

**No model is ever trained on your data** — a sync triggers deterministic recomputation by the financial engine, rule engine, and insight generators. See [`docs/AI_AND_PRIVACY.md`](docs/AI_AND_PRIVACY.md) for the provider + privacy contract.

### Configuration (backend/.env)

```bash
# Where file sources may live (path traversal and symlink escapes are rejected)
FILE_SOURCE_ROOT=./sample_data

# Background scheduler (a daemon thread in the backend process; min interval 30s)
SYNC_SCHEDULER_ENABLED=true
SYNC_SCHEDULER_INTERVAL_SECONDS=300

# Per-source SQL hardening (the connector builds parameterised, bounded SELECTs)
SYNC_SQL_ROW_LIMIT=50000
SYNC_SQL_STATEMENT_TIMEOUT_SECONDS=30
SYNC_SQL_DRIVER=sqlite  # or postgresql

# A SQL connection URL — MoneyPlant stores only the NAME (see secret_ref),
# never the value.
MY_DB_URL=postgresql://readonly_user:password@localhost:5432/mydb
```

> **Use a read-only database user.** MoneyPlant only issues `SELECT`, but defence in depth matters.

### Add a source in the UI

1. Open <http://localhost:3000/data>.
2. Choose **File** or **SQL database**.
3. **File** — enter a path relative to `FILE_SOURCE_ROOT` (e.g. `daily_transactions.xlsx`) and paste the column-mapping JSON.
4. **SQL** — enter the table name, the incremental column (e.g. `updated_at` or `id`), and the **name** of the env var holding the URL (e.g. `MY_DB_URL`). Never paste the URL itself.
5. Pick a schedule (`manual` / `daily` / `hourly`) and click **Create source**.
6. Click **Test** to preview the first rows, then **Sync now**.

### Run syncs outside the backend (Windows Task Scheduler / cron)

```bash
cd backend
.venv/bin/python -m scripts.sync_sources --list
.venv/bin/python -m scripts.sync_sources --all
.venv/bin/python -m scripts.sync_sources --source <SOURCE_ID>
.venv/bin/python -m scripts.sync_sources --all --dry-run
```

Disable `SYNC_SCHEDULER_ENABLED` if you want the CLI to be the only scheduler. Full CLI surface and `--dry-run` semantics are in [`docs/engineering/09-sync.md`](docs/engineering/09-sync.md).

---

## Tests

### Backend — 219 pytest cases, ~3s

```bash
cd backend
.venv/bin/pytest                           # all 219
.venv/bin/pytest tests/test_rules.py -v    # one file
.venv/bin/pytest -m "not slow"             # skip slow markers
.venv/bin/pytest -k "min_cash_reserve"     # name substring
```

Coverage is reported by `pytest-cov` but is not a CI gate — assertion quality beats line count.

### Frontend — 42 Vitest cases, ~1s

```bash
cd apps/web
npm run typecheck          # tsc --noEmit (catches Zod-mirror drift FIRST)
npm run lint
npm run test               # vitest run
```

`tsc --noEmit` is the gate that catches Zod-mirror drift — if a Pydantic schema changes without a Zod update, the consuming page breaks at the type level before it ever runs.

### End-to-end — 11 Playwright specs (A–K)

```bash
cd apps/web
npx playwright install --with-deps chromium   # one-time, requires a browser binary
npm run test:e2e                              # all 11
npm run test:e2e -- e2e/j-dashboard.spec.ts --headed
```

Playwright requires a Chromium / Firefox / WebKit binary that is **not bundled with npm**. CI is the source of truth for green; local runs are advisory.

### What each layer proves

| Layer | Proves | Numbers |
|---|---|---|
| **L1** Backend unit (pytest) | Engine math is correct to the last decimal; LLM/Laya degrade honestly; sync contains / sanitises / parses | 219 |
| **L2** Frontend unit + component (Vitest + RTL) | Zod mirror parses valid / rejects malformed; format helpers handle every currency; three fetch states render | 42 |
| **L3** TypeScript types (`tsc --noEmit`) | Zod mirror and consumer never disagree; page→hook→util chains are valid | runs in every CI invocation |
| **L4** E2E (Playwright) | Click flow → screen assertion, 11 user journeys | 11 |

The defining property of L1: **all assertions are on real numeric outputs**, not snapshots. A test like `test_metrics.py::test_gross_margin` asserts `m.gross_margin() == "0.2500"`. That assertion is the test.

Full coverage and per-file what-it-asserts table: [`docs/engineering/14-testing-and-ops.md`](docs/engineering/14-testing-and-ops.md).

---

## LLM setup

### Local (Ollama — default)

```bash
ollama serve
ollama pull llama3.1:8b
```

`backend/.env` needs:

```dotenv
AI_DEFAULT_MODE=local
AI_LOCAL_BASE_URL=http://localhost:11434/v1
AI_LOCAL_MODEL=llama3.1:8b
```

The Settings page's "Providers" panel reports real health-check status — `unavailable` is shown honestly when Ollama isn't reachable; the assistant never silently falls back to a non-local provider.

### OpenAI

```dotenv
AI_DEFAULT_MODE=openai
OPENAI_API_KEY=sk-...
```

The key is never returned to the browser.

### Anthropic

```dotenv
AI_DEFAULT_MODE=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Same constraints as OpenAI.

---

## Laya

Laya is a separate decision layer, not the LLM. It is **advisory** — its `status` never overrides a hard rule. First run downloads the model (multi-GB) and caches it under `HF_HUB_CACHE`. Pin in `backend/.env`:

```dotenv
LAYA_MODEL=convaiinnovations/laya
LAYA_DEVICE=cpu   # or cuda / mps / xpu
```

If Laya is unavailable, the rule engine still operates and the decision report shows `laya_status: unavailable` honestly. See [`docs/engineering/07-llm-and-laya.md`](docs/engineering/07-llm-and-laya.md).

---

## Privacy and security highlights

- API keys are server-side env vars; never accepted from the client; never returned in responses. `/api/config/public` exposes only safe boolean flags.
- Local mode keeps all data and inference on the configured host. **No silent fallback to API** — `unavailable` is shown honestly.
- Credentials on `DataSource` are stored only as `secret_ref` (an env-var name). The Zod mirror deliberately **omits** `secret_ref`; the field never crosses the wire.
- Logs are structured and the `LOG_REDACT_FINANCIAL=true` default strips money-shaped values from log-format fields.
- XLSX formulas are resolved to values at read time (`openpyxl(data_only=True)`). No formula string crosses into the database.
- No stack traces leave the API. The catch-all returns `{"detail": "internal_error"}` and logs server-side only.
- No authentication. Single-tenant. **Do not expose on the public internet without adding auth.**

Full treatment: [`docs/SECURITY_SELF_ASSESSMENT.md`](docs/SECURITY_SELF_ASSESSMENT.md) · [`docs/AI_AND_PRIVACY.md`](docs/AI_AND_PRIVACY.md).

---

## Known limitations (the team has decided to defer these)

- **Synthetic financing catalog.** Five illustrative products; not real lender offers.
- **File sources are single-host and file-system scoped.** Must resolve inside `FILE_SOURCE_ROOT`. No cloud-object-store connector yet.
- **SQL sources are `SELECT`-only and dialect-limited** (SQLite + Postgres). The client never supplies SQL — you name a table and an incremental column, MoneyPlant builds a parameterised, bounded, timed-out `SELECT`. **Use a read-only DB user.**
- **Sync de-duplication is per canonical row hash.** Two distinct rows that are byte-identical across all canonical fields (date, amount, direction, currency, description, category) are treated as the same. Conservative — never silently overwrites.
- **Syncs are batch, not streaming.** A source syncs on its schedule or on demand; no change-data-capture / webhook.
- **XLSX is read as values, never formulas.** First sheet (or the one you name) only.
- **Financing affordability = simple annuity + DSCR.** No fees, no tax effect, no credit score, no covenant modelling.
- **Dashboard sensitivity is observed-period, one-at-a-time** (±25% / ±10% on observed transactions). Not a forecasting model; the Simulator is for full sensitivity.
- **Dashboard insights do not cross months.** The interpretation is computed over the window you select.
- No authentication in MVP — single-tenant. Do not expose on the public internet without adding auth.
- No statistical forecasting. Sensitivity is deterministic and clearly labelled.
- No multi-currency conversion. Mixed-currency imports are quarantined.
- No depreciation, tax, FX, or loan amortization. See [`docs/FINANCIAL_MODEL.md` §11](docs/FINANCIAL_MODEL.md).

The complete list with rationale: [`docs/engineering/14-testing-and-ops.md` §14.9](docs/engineering/14-testing-and-ops.md#149-known-gaps-and-deferred-work).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: app` when starting uvicorn | venv not active, or ran from the wrong cwd | `cd backend` first, then `uvicorn app.main:app` |
| `alembic upgrade head` errors | `DATABASE_URL` not set, or path unwritable | Check `backend/.env`; SQLite needs a writable directory |
| CORS error in browser console | `CORS_ORIGINS` doesn't match the origin you're using | Add the origin to the comma-separated list in `backend/.env` |
| `/api/ai/health` returns `unavailable` for `local` | Ollama not running, or wrong base URL | `ollama serve` and `ollama pull llama3.1:8b`; check `AI_LOCAL_BASE_URL` |
| `/api/ai/health` returns `unavailable` for `openai` | Key not set | `OPENAI_API_KEY` in `backend/.env` and restart uvicorn |
| Frontend can't reach backend | Wrong `NEXT_PUBLIC_API_BASE_URL` | Set in `apps/web/.env.local`, restart `npm run dev` |
| `pip install -e ".[dev]"` fails on the host Python 3.14 | This is the gotcha | Use `uv venv --python 3.11 .venv` to isolate |
| `tsx: command not found` on Windows | Trying to run the binary directly | Use `npm run dev`, which resolves `node_modules/.bin` |
| Dashboard stays empty | No transactions, or `businessId` is null | Pick a workspace from the sidebar |
| Sync errors show `path_outside_root` | `DataSource.config.path` escapes `FILE_SOURCE_ROOT` | Move the file or change the path to be relative to the root |

Full troubleshooting matrix: [`docs/engineering/13-local-runbook.md` §13.13](docs/engineering/13-local-runbook.md).

---

## License

TBD.
