# Chapter 00 — Orientation & How to Read the Code

> *What this codebase is, what's interesting about it, and the fastest path through it.*

---

## The 60-second tour

MoneyPlant turns a small business's financial history into projections, scenarios, and
decisions. The shape of the system is two long-lived processes and one database:

```
    ┌────────────────────────────────────────────────────────────┐
    │                 Browser (no auth, single user)            │
    └────────────────────────────────────────────────────────────┘
                              ▲                │
              ◄── JSON over HTTP │              │ TanStack Query
                              │                ▼
    ┌────────────────────────────────────────────────────────────┐
    │   Next.js 14 (apps/web, :3000)                             │
    │   • App Router + React Server Components                    │
    │   • Zod-parsed responses, Recharts charts                  │
    └────────────────────────────────────────────────────────────┘
                              ▲                │
                              │                ▼
    ┌────────────────────────────────────────────────────────────┐
    │   FastAPI (backend, :8000)                                 │
    │   • Pure Decimal financial engine                          │
    │   • Rule-first decision verdicts                           │
    │   • LLM explanation, Laya soft assessment                  │
    │   • CSV/XLSX ingestion + scheduled sync                    │
    └────────────────────────────────────────────────────────────┘
                              ▼
    ┌────────────────────────────────────────────────────────────┐
    │   SQLite (default) / Postgres                              │
    │   • 8 ORM tables, 3 Alembic migrations                     │
    │   • Optional in-process sync scheduler daemon              │
    └────────────────────────────────────────────────────────────┘
```

The frontend never opens the database. The backend never calls the LLM without a
precomputed numeric context already in hand. **Every number the user sees originated in
deterministic code.**

---

## The mental model in four sentences

1. **Inputs come in through two doors** — a manual CSV/XLSX upload (one-shot), or a
   registered data source (incremental, scheduled). Both reuse the same row parser.
2. **The engine is pure** — given a `Transaction` list and a `Business`, it returns numbers
   (`compute_metrics`), projection series (`run_scenario`), alerts (`evaluate_alerts`), and
   financing matches (`financing_options`). No I/O, no globals, no LLM.
3. **The decision verdict is also pure** — given a scenario result and business config,
   eight rules vote, a precedence function aggregates, and the Laya adapter (optionally)
   contributes advisory scores the verdict cannot overturn.
4. **The LLM is last and optional** — it receives a *frozen* `ExplanationContext` payload
   (computed numbers + rule evaluations + Laya scores) and produces a *summary*. The
   summary can never change the verdict.

If you keep that ordering in mind, navigating the codebase is mostly a matter of asking
"which layer am I in?".

---

## The directory layout, mapped to the mental model

```
MoneyPlant/
├── backend/                  ← FastAPI service, owns all persistence + math
│   ├── app/
│   │   ├── api/              ← FastAPI routers (HTTP edge)
│   │   ├── core/             ← settings, logging, security stub
│   │   ├── db/               ← SQLAlchemy session, declarative Base, mixins
│   │   ├── models/           ← ORM tables (Business, Transaction, Scenario, …)
│   │   ├── schemas/          ← Pydantic v2 request/response shapes
│   │   ├── engine/           ← pure-Decimal engine: alerts, financing, P-vs-C
│   │   ├── insights/         ← dashboard visual generators (engine → view-model)
│   │   └── services/
│   │       ├── decisions/    ← rules + laya + llm orchestrator
│   │       ├── finance/      ← money/periods/metrics/inventory/invariants
│   │       ├── industry_adapters/ ← Manufacturing / Service / Inventory
│   │       ├── ingestion/    ← CSV / XLSX parsing, mapping
│   │       ├── laya/         ← soft-assessment adapter (heuristic fallback)
│   │       ├── llm/          ← provider abstraction (Ollama / OpenAI / Anthropic)
│   │       ├── rules/        ← rule registry + aggregator
│   │       ├── simulation/   ← scenario runner + sensitivity analysis
│   │       └── sync/         ← connectors, sync service, scheduler, CLI
│   ├── alembic/versions/     ← 3 migrations (initial, data sources, dedup)
│   ├── tests/                ← 219 pytest cases
│   └── pyproject.toml        ← Python 3.11+, FastAPI ≥0.110, SQLAlchemy 2
│
├── apps/web/                 ← Next.js 14 frontend
│   ├── app/
│   │   ├── layout.tsx        ← root <html>, Inter font, dark-mode class
│   │   ├── page.tsx          ← static landing page
│   │   └── (app)/            ← authenticated app shell + 8 pages
│   │       ├── layout.tsx          ← sidebar shell
│   │       ├── dashboard/          ← insights + charts
│   │       ├── data/               ← data source CRUD
│   │       ├── simulator/          ← scenario builder
│   │       ├── decisions/          ← list + detail (with LLM explain)
│   │       ├── compare/            ← 1–5 scenarios side-by-side
│   │       ├── financing/          ← financing catalog matches
│   │       ├── assistant/          ← LLM chat (graceful fallbacks)
│   │       └── settings/           ← business CRUD + privacy + AI providers
│   ├── components/
│   │   ├── ui/               ← primitives (Button, Card, Dialog, Table, Tabs…)
│   │   ├── dashboard/        ← chart components, freshness strip, month panel
│   │   ├── AppShell.tsx      ← sidebar + theme toggle shell
│   │   ├── WorkspaceContext.tsx  ← Zustand store: { businessId, setBusinessId }
│   │   ├── AlertsPanel.tsx
│   │   └── FinancingPanel.tsx
│   ├── lib/
│   │   ├── api.ts            ← Zod-typed fetch wrappers (apiGet/apiPost/...)
│   │   ├── schemas.ts        ← mirror of backend Pydantic (drift fails loudly)
│   │   ├── format.ts         ← pure formatters, currency-aware
│   │   └── queryClient.ts
│   ├── e2e/                  ← 11 Playwright specs (A–K)
│   └── tests/                ← Vitest unit + component tests
│
├── docs/                     ← you're reading this one
│
├── sample_data/              ← CSVs + an XLSX + a SQLite used by demo seeding
└── PUKU.md                   ← puku-cli harness guidance (do not edit casually)
```

---

## First-day workflow

If you have just been handed this repository, do this in order:

1. **Read chapter 01** — *Design principles*. The five rules below this codebase are stricter
   than anything in the code review checklist. Understand them once and you will catch
   most wrong moves for free.
2. **Get both processes running** — chapter 13 walks it through. The reproducer is:
   ```bash
   # backend (PowerShell; equivalent bash works on macOS/Linux)
   cd backend
   .venv\Scripts\alembic.exe upgrade head
   .venv\Scripts\python.exe -m scripts.seed_demo
   .venv\Scripts\uvicorn.exe app.main:app --reload --port 8000

   # frontend (another terminal)
   cd apps\web
   npm install
   npm run dev   # opens http://localhost:3000
   ```
3. **Open the dashboard** — pick the seeded **Aurora Garments** workspace.
   Without anything configured, you should see five rolling months of metrics. From there
   you can go anywhere.
4. **Trace one request end-to-end** — open DevTools, click a KPI on the dashboard, and
   pick **Net cash movement** in the right panel. The request that fills the panel is
   `GET /api/businesses/{id}/dashboard-insights`. Open `apps/web/app/(app)/dashboard/page.tsx`,
   find the matching `useQuery`, then follow it server-side into `app/api/insights.py`
   and finally `app/insights/engine.py:build_dashboard_insights`.
5. **Run both test suites** — `cd backend && pytest` and `cd apps/web && npm test`.
   They are fast (under a minute total) and both should be green before you commit.

---

## How to read a number, top to bottom

Suppose the dashboard shows "Operating margin: 12.4%". Trace the value:

```
UI
└── apps/web/components/dashboard/KpiStrip.tsx            → reads SummaryOperatingMargin
    │
    │  /api/businesses/{id}/dashboard-insights (JSON)
    ▼
apps/web/app/(app)/dashboard/page.tsx                    → useQuery(apiGet, ...)
    │
    ▼
backend/app/api/insights.py                              → builds inputs from DB
    │
    ▼
backend/app/insights/engine.py:899 build_dashboard_insights()
    │                       ▲
    │                       │ no I/O, no globals, no LLM — just pure functions
    ▼
backend/app/services/finance/metrics.py:97 compute_metrics()    ← the actual math
    │
    ▼
backend/app/services/finance/money.py:97 format_money()         ← 2dp USD, ROUND_HALF_UP
```

Every arrow has a contract enforced by Pydantic (Zod on the way out, Zod again on the way
back). The contract is the same one shown at the top: numbers come from the engine,
period.

---

## What is intentionally weird

A handful of design choices will look surprising on first read. They are deliberate.

- **TypeScript everywhere, no `.js`/`.jsx`** in `apps/web/src`. Type drift between
  Pydantic and Zod fails loudly at runtime; the policy is to make that drift impossible
  to introduce silently. See `apps/web/eslint` config and the Pydantic ↔ Zod parity rule
  in chapter 11.
- **`WorkspaceContext` is a Zustand store, not a React Context.** Despite the name, it is
  `zustand/create` because there is exactly one workspace at a time and no provider
  ceremony is helpful here. (`apps/web/components/WorkspaceContext.tsx`)
- **The Laya adapter always returns responses, even when Laya is unconfigured.** A
  missing import is *not* a 503; it is a list of `LayaAssessment(status="unavailable")`
  answers. The point is to keep the decision verdict shape stable regardless of provider
  health. (`backend/app/services/laya/adapter.py:109`)
- **The dashboard's `Compare` panel and `financing` panel ignore multi-currency.** USD is
  hard-coded in a couple of formatter calls. The intent is that businesses pick one
  currency at creation and the UI never has to reconcile mixed units in a chart. Treat
  this as a known gap, not a bug.
- **The sync scheduler is a daemon thread, not APScheduler.** Daemon + `Event.wait`
  makes `stop()` effectively instant, and it costs nothing. (`backend/app/services/sync/scheduler.py:126`)
- **The Zod mirror omits `secret_ref` on the `DataSource`.** That's not a
  typo. Sealing the credential field at the *boundary* rather than the column is the
  policy. (`apps/web/lib/schemas.ts:396`)

---

## What to read next

| You want to… | Read chapter |
|---|---|
| Understand a design decision | 01 — *Design principles* |
| Add a backend endpoint | 02 → 04 → 10 |
| Add a column to an ORM table | 04 |
| Add a scenario calculation | 05 → 06 |
| Wire a new UI page to an existing API | 11 → 12 |
| Add a new alert | 06 → 17 (cross-ref to engine/alerts.py) |
| Add a new LLM provider | 07 |
| Run it | 13 |
| Ship it | 14 |

---

*Next: [Chapter 01 — Design principles](01-design-principles.md)*