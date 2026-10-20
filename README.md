# MoneyPlant — SME Finance Copilot

A privacy-aware financial decision copilot for small and medium-sized enterprises. Import records, simulate operating decisions, compare scenarios, and understand the risks and trade-offs of a proposed action.

> **Status:** Implemented, unverified. See [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) for the honest verification matrix. The bash tool was unavailable in the session that produced this codebase, so no `pytest`, `next dev`, `playwright`, or `uvicorn` was actually executed. The user runs the verification commands below to upgrade the status.

## Features

- **CSV / XLSX import** with column-mapping, per-row validation, and import history.
- **Financial dashboard** driven by backend-computed metrics — never fabricated.
- **Dashboard interpretations** — every visual (KPI strip, revenue/costs/profit, cash balance, profit–cash gap, cost breakdown, sensitivity, scenario compare, alerts, financing) has a deterministic, pure-function text interpretation next to it. No LLM by default. The interpretation is testable: every quoted figure is verifiable in the matching evidence dict.
- **Cash-flow alerts** — deterministic monthly trajectory from imported transactions. Five alert codes (NEGATIVE_CASH, LOW_BUFFER, SHORT_RUNWAY, PROFITABLE_BUT_CASH_POOR, SHARP_DROP). Text-label severities (Critical / Warning / Info), no colour-only signalling.
- **Financing-option matching** — a SYNTHETIC catalog of 5 illustrative products matched against the business's revenue, runway, and projected shortfall. Hard eligibility + DSCR floor override ranking. Not a credit decision.
- **Connected data sources** — connect a CSV/XLSX file from the configured allowed directory, or a SQL table described by an env-var name, and have MoneyPlant pull new rows automatically. Idempotent re-sync (SHA-256 dedup), per-source run history with rows-added / skipped-as-duplicate / rejected counters, a background scheduler, a CLI (`scripts/sync_sources.py`) for Windows Task Scheduler / cron, and a demo helper (`scripts/simulate_daily_data.py`) so the dashboard can show fresh data arriving. Credentials are stored only as env-var names; the value never leaves the server. No model is ever trained on your data — a sync triggers deterministic recomputation by the engine, rules and insight generators.
- **Production and operating simulator** with industry-specific inputs.
- **Scenario save, rerun, compare** with versioned, reproducible results.
- **Rule-based decision engine** with hard-constraint precedence.
- **Laya integration** for bounded structured decision assessments (advisory; cannot override hard rules).
- **LLM explanation layer** with local (Ollama) or API (OpenAI, Anthropic) provider, schema-validated responses, no silent fallback.
- **Decision report** with assumptions, caveats, calculation timestamp, and printable layout.
- **AI assistant** grounded in computed results.
- **Five industry profiles** seeded with clearly-labeled synthetic data: manufacturing, retail, service, wholesale, food.

## Architecture

MoneyPlant is a modular monolith. Next.js 14 (App Router) frontend, FastAPI backend, SQLAlchemy + Alembic persistence. The full architecture is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). The financial engine is a pure-function module with `decimal.Decimal` arithmetic; the LLM and Laya are thin adapters behind a provider interface and cannot calculate authoritative financial results.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript strict, React 18, Tailwind CSS, React Query, Zod, Recharts, lucide-react |
| Backend | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, openpyxl, pandas |
| Database | SQLite (default), Postgres (via `DATABASE_URL`) |
| Decisions | Custom rule engine + Laya (real `laya.Router().predict()`) |
| LLM | Ollama (local) / OpenAI / Anthropic via OpenAI-compatible HTTP |
| Tests | pytest, vitest, Playwright |

## Prerequisites

- **Python 3.11+**
- **Node.js 20+**
- **Git**
- (Optional, for local LLM) **Ollama** — `winget install Ollama.Ollama` on Windows.
- (Optional, for Laya) First run downloads model weights to `HF_HUB_CACHE`.

## Installation

```bash
# Clone
git clone <repo-url> moneyplant
cd moneyplant

# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_demo.py
cd ..

# Frontend
cd apps/web
npm install
cd ../..
```

## Environment

Copy `.env.example` to `backend/.env` and `apps/web/.env.local`. See the file for placeholders. **Never commit a real `.env`.**

## Database setup

```bash
cd backend
.venv\Scripts\activate
alembic upgrade head          # creates schema
python scripts/seed_demo.py   # loads 5 demo businesses with synthetic data
```

## Run the app (development)

Two terminals:

```bash
# Terminal 1 — backend
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd apps/web
npm run dev
```

Open `http://localhost:3000`. The backend's OpenAPI docs are at `http://localhost:8000/docs`.

## Demo data

Five synthetic businesses are seeded — each clearly labeled as synthetic. See `sample_data/`.

- `clothing_demo.csv` — manufacturing, 12 months of transactions + a baseline scenario.
- `retail_demo.csv` — retail, 12 months.
- `service_demo.csv` — professional service, 12 months.
- `wholesale_demo.csv` — wholesale, 12 months.
- `food_demo.csv` — food service, 12 months.

Load: `python scripts/seed_demo.py` (idempotent; re-running it refreshes demo businesses).

## Connected data sources (automatic updates)

Connect a source once and let MoneyPlant pull new rows on a schedule. **No model is ever trained on your data** — a sync triggers deterministic recomputation by the financial engine, rule engine and insight generators. See [`docs/AI_AND_PRIVACY.md`](docs/AI_AND_PRIVACY.md) FAQ.

### Configuration (backend/.env)

```bash
# Where file sources may live (path traversal and symlink escapes are rejected)
FILE_SOURCE_ROOT=./sample_data

# Background scheduler (a daemon thread in the backend process)
SYNC_SCHEDULER_ENABLED=true
SYNC_SCHEDULER_INTERVAL_SECONDS=300

# A SQL connection URL. MoneyPlant stores only the NAME (see secret_ref), never the value.
MY_DB_URL=postgresql://readonly_user:password@localhost:5432/mydb
```

> **Use a read-only database user.** MoneyPlant only issues `SELECT`, but defense in depth matters.

### Add a source in the UI

1. Open `http://localhost:3000/data`.
2. Choose **File** or **SQL database**.
3. **File**: enter a path relative to `FILE_SOURCE_ROOT` (e.g. `daily_transactions.xlsx`) and paste the column-mapping JSON.
4. **SQL**: enter the table name, the incremental column (e.g. `updated_at` or `id`), and the **name** of the env var holding the URL (e.g. `MY_DB_URL`). Never paste the URL itself.
5. Pick a schedule (`manual` / `daily` / `hourly`) and click **Create source**.
6. Click **Test** to preview the first rows, then **Sync now**.

### Run syncs outside the backend (Windows Task Scheduler / cron)

```bash
cd backend
.venv\Scripts\activate

# List configured sources
python ..\scripts\sync_sources.py --list

# Sync everything that is due (what Task Scheduler should run daily)
python ..\scripts\sync_sources.py --all

# Sync one source regardless of schedule
python ..\scripts\sync_sources.py --source <SOURCE_ID>

# Preview without writing
python ..\scripts\sync_sources.py --all --dry-run
```

**Task Scheduler setup:** create a daily task with action
`C:\path\to\moneyplant\backend\.venv\Scripts\python.exe` and argument
`..\scripts\sync_sources.py --all`, "Start in"
`C:\path\to\moneyplant\backend`. Disable `SYNC_SCHEDULER_ENABLED` if you want the CLI to be the only scheduler.

### Demo: watch the dashboard update live

```bash
# 1. In the UI, add a file source pointing at daily_transactions.xlsx
#    (created on first run) and click "Sync now".
# 2. Append a new day of synthetic rows:
cd backend
.venv\Scripts\activate
python ..\scripts\simulate_daily_data.py
# 3. Back in the UI, click "Sync now" again. The freshness strip shows the
#    new sync time and the dashboard, alerts and interpretations update.
```

`scripts/simulate_daily_data.py` appends one deterministic day of synthetic
rows to both `sample_data/ext_invoices.db` (for the SQL source demo) and
`sample_data/daily_transactions.xlsx` (for the file source demo).

## Tests

```bash
# Backend
cd backend && .venv\Scripts\activate && pytest -v

# Frontend
cd apps/web && npm run typecheck && npm run lint && npm run test

# End-to-end
cd apps/web
npx playwright install --with-deps chromium
npm run test:e2e
```

### One-shot QA check

For a single command that installs, migrates, and runs everything:

```bash
# Windows
powershell -ExecutionPolicy Bypass -File scripts/qa_check.ps1
```

The script runs: backend install → alembic upgrade → pytest → frontend install → typecheck → lint → vitest → playwright install → playwright.

## What the tests cover

| Layer | File | What it proves |
|---|---|---|
| Alerts | `backend/tests/test_alerts.py` | Each rule's trigger and non-trigger, boundary values, empty-input case. |
| Financing | `backend/tests/test_financing.py` | No-shortfall sentinel, hand-calculated annuity, DSCR boundary, ineligible product, ranking order, Decimal precision. |
| Dashboard insights | `backend/tests/test_insights.py` | Each visual's trigger and edge case (no data, one month, zero revenue, all-negative cash, flat series). Plus the invariant that every figure quoted in a sentence is present in the matching evidence dict. |
| Frontend Zod mirrors | `apps/web/lib/schemas.test.ts` | `Alert`, `AlertsResponse`, `FinancingMatch`, `FinancingOptionsResponse`, `DashboardVisual`, `DashboardInsights` parse correctly and reject unknowns. |
| Money primitives | `backend/tests/test_money.py` | Decimal arithmetic, currency rounding, division-by-zero semantics. |
| Periods | `backend/tests/test_periods.py` | Monthly half-open intervals, year rollovers, month arithmetic, leap-year clamping. |
| Metrics | `backend/tests/test_metrics.py` | Revenue/cost/operating-profit categorization, cash vs. profit timing, runway. |
| Inventory / manufacturing / service | `backend/tests/test_inventory.py` | Exact formulas for material-bounded production, capacity caps, inventory, service billable hours. |
| Profit vs cash | `backend/tests/test_profit_vs_cash.py` | Credit sales, inventory build-up, and the "profitable but cash-poor" reconciliation. |
| Invariants | `backend/tests/test_invariants.py` | Closing-cash identity, sold ≤ produced, revenue = units × price. |
| Simulation | `backend/tests/test_simulation.py` | End-to-end through the runner: manufacturing, retail, service, wholesale, food. |
| Rules | `backend/tests/test_rules.py` | Each rule's status transitions; hard-constraint precedence. |
| Dashboard interactivity | `apps/web/e2e/j-dashboard.spec.ts` | Loads dashboard, picks a business, sees KPI strip + synthetic banner + table-view + Print button. Requires both servers running. |
| Laya | `backend/tests/test_laya.py` | Unavailable states; answer normalization; state isolation. |
| LLM | `backend/tests/test_llm.py` | Health probe is real, JSON extraction is robust, bad responses are "unavailable". |
| Ingestion | `backend/tests/test_ingestion.py` | CSV preview, suggest_mapping, validation issue severity. |
| API | `backend/tests/test_api.py` | Business CRUD, import pipeline, simulation, decision, AI health. |
| Frontend schemas | `apps/web/lib/schemas.test.ts` | Zod mirrors of every backend response shape. |
| Frontend format | `apps/web/lib/format.test.ts` | Currency-aware formatting, em-dash for missing values. |
| E2E | `apps/web/e2e/{a..i}-*.spec.ts` | First-run, import, simulate, save, compare, decision, explain, assistant, privacy. |

## LLM setup

### Local (Ollama)

```bash
# Install Ollama (Windows: winget install Ollama.Ollama)
ollama serve
ollama pull llama3.1:8b
```

Set `AI_DEFAULT_MODE=local`, `AI_LOCAL_BASE_URL=http://localhost:11434/v1`, `AI_LOCAL_MODEL=llama3.1:8b` in `backend/.env`. The privacy settings page will report real health-check status.

### OpenAI

Set `AI_DEFAULT_MODE=openai` and `OPENAI_API_KEY=sk-...` in `backend/.env`. The key is never returned to the browser.

### Anthropic

Set `AI_DEFAULT_MODE=anthropic` and `ANTHROPIC_API_KEY=sk-ant-...` in `backend/.env`. Same constraints.

## Laya

Laya is a separate decision layer, not the LLM. First run downloads the model (multi-GB) and caches it under `HF_HUB_CACHE`. Set `LAYA_MODEL=convaiinnovations/laya` (or pin a specific version) in `backend/.env`. If Laya is unavailable, the rule engine still operates and the decision report shows `laya_status: unavailable` honestly.

## Privacy

See [`docs/AI_AND_PRIVACY.md`](docs/AI_AND_PRIVACY.md). Highlights:

- API keys are server-side env vars; never accepted from the client; never returned in responses.
- Local mode keeps all data and inference on the configured host. No silent fallback to API.
- Logs are structured and do not include raw transaction descriptions.
- The privacy settings page reports real `health_check()` results — no green check without a successful probe.

## Known limitations

- **Synthetic financing catalog.** The 5 products are illustrative placeholders; eligibility thresholds and APRs are not real lender offers. UI is labelled `Illustrative products. Not a credit decision.`
- **Data sources are single-host and file-system scoped.** File sources must resolve inside `FILE_SOURCE_ROOT` (default `sample_data/`); symlink escapes and `..` traversal are rejected. There is no cloud-object-store connector yet.
- **SQL sources are `SELECT`-only and dialect-limited.** Only SQLite and Postgres are supported. The client never supplies SQL: you name a table and an incremental column, and MoneyPlant builds a parameterised, bounded, timed-out `SELECT`. **Use a read-only database user.** No JOINs, no aggregation, no views across schemas beyond the one you name.
- **Sync de-duplication is per canonical row hash.** Two genuinely distinct transactions that are byte-identical across all canonical fields (date, amount, direction, currency, description, category) are treated as the same row and the second is skipped. This is deliberate and conservative — it never silently overwrites, it only declines to add.
- **Syncs are batch, not streaming.** A source syncs on its schedule or on demand; there is no change-data-capture or webhook. The scheduler is a single daemon thread in the backend process, so a backend that is not running does not sync — use `scripts/sync_sources.py` from Task Scheduler for that case.
- **XLSX is read as values, never as formulas**, and only the first sheet (or the one you name) is read.
- **Financing affordability = simple annuity + DSCR.** No fees, no tax effect, no credit score, no covenant modelling. The matcher answers "could the monthly payment fit?" — nothing more.
- **Dashboard sensitivity is observed-period, one-at-a-time.** It scales monthly inflows and outflows independently by ±25% / ±10% on the observed transactions. It is not a forecasting model and does not re-run the full scenario simulator. For full sensitivity, open the **Simulator** page and run a saved scenario with sensitivity enabled.
- **Dashboard insights do not cross months.** The interpretation is computed over the [period_start, period_end_exclusive) window you select; pick a different range to test different months. No missing-data fabrication: an empty period returns an edge-case visual.
- No authentication in MVP — single-tenant. Do not expose on the public internet without adding auth.
- No statistical forecasting. Sensitivity is deterministic one-at-a-time, clearly labelled.
- No multi-currency conversion. Mixed-currency imports are quarantined.
- No depreciation, tax, FX, or loan amortization. See [`docs/FINANCIAL_MODEL.md`](docs/FINANCIAL_MODEL.md) §11.
- Impeccable design: the formal `concept-seed.mjs` roll was not performed in the session that produced this codebase (bash unavailable). The Operate-mode craft floor was applied directly. See [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `pip install -e ".[dev]"` fails on `laya` | Laya needs Python 3.11–3.13 | Check `python --version`. |
| `npm run dev` errors on missing modules | `npm install` not run | `cd apps/web && npm install`. |
| `/api/ai/health` returns `unavailable` for `local` | Ollama not running | `ollama serve` and `ollama pull llama3.1:8b`. |
| `/api/ai/health` returns `unavailable` for `openai` | Key not set | Set `OPENAI_API_KEY` in `backend/.env` and restart. |
| `alembic upgrade head` errors | `DATABASE_URL` not set or path unwritable | Check `backend/.env`; SQLite needs a writable directory. |
| Frontend can't reach backend | Wrong `NEXT_PUBLIC_API_BASE_URL` | Set in `apps/web/.env.local`, restart `npm run dev`. |

## License

TBD.
