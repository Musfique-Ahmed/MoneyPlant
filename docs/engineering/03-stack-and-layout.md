# Chapter 03 — Technology Stack & Repository Layout

> *Every dependency with the exact version constraint, and the directory map that points
> at each layer's responsibility.*

---

## 3.1 Backend stack (`backend/pyproject.toml`)

| Layer | Choice | Constraint | Where it lives |
|---|---|---|---|
| Runtime | **Python 3.11+** | `requires-python = ">=3.11"` | `pyproject.toml:25` |
| API framework | **FastAPI** | `>=0.110` | `pyproject.toml:28`, `app/main.py:46` |
| ASGI server | **Uvicorn[standard]** | — | `pyproject.toml:29` |
| Validation | **Pydantic v2** | `>=2.6` | `app/schemas/*` |
| Settings | **pydantic-settings** | `>=2.2` | `app/core/config.py:18` |
| ORM | **SQLAlchemy 2** | `>=2.0` (declarative + relationship style) | `app/models/*`, `app/db/*` |
| Migrations | **Alembic** | `>=1.13` | `alembic/versions/` |
| HTTP client | **httpx** | `>=0.27` | `app/services/llm/*`, `app/services/laya/adapter.py:67` |
| Data | **pandas 2.x**, **openpyxl 3.x** | — | `app/services/ingestion/xlsx.py` |
| Excel data-only | `openpyxl(..., data_only=True)` | — | `app/services/sync/file_connector.py` (formulas resolved to values, never carried forward) |
| LLM providers | **Ollama** (default), **OpenAI**, **Anthropic** | `OllamaProvider`, `OpenAIProvider`, `AnthropicProvider` | `app/services/llm/` |
| Soft assessment | **Laya adapter** | optional pip package; falls back to heuristic | `app/services/laya/adapter.py` |
| Tests | **pytest 8**, **pytest-asyncio**, **pytest-cov** | `>=8.0` | `tests/` (219 cases) |
| Lint / types | **ruff**, **mypy** | `>=0.3`, `>=1.8` | `pyproject.toml:45-46` |

### Why this set

- **FastAPI 0.110+** — OpenAPI generation is reliable; lifespan hooks are stable; the
  response models and dependency injection reduce boilerplate enough to matter.
- **SQLAlchemy 2 declarative** — typed models, explicit sessions, no Magic. Lets us
  keep the schema as code and the migrations as a thin layer over it.
- **Pydantic v2** — closed enums, literal types, faster validation than v1, and the
  schema-as-source-of-truth discipline that the mirror in `apps/web/lib/schemas.ts`
  depends on.
- **httpx** — async-capable, used by all external provider adapters. Symmetric
  async/sync API means an LLM call from a sync route looks the same as one from an
  async endpoint.

---

## 3.2 Frontend stack (`apps/web/package.json`)

| Layer | Choice | Where it lives |
|---|---|---|
| Runtime | **Node.js 18+** (development on Node 24 / npm 11) | (host) |
| Framework | **Next.js 14.2.5** (App Router) | `app/` |
| UI | **React 18.3** | `app/`, `components/` |
| Server-state cache | **@tanstack/react-query 5** | `lib/queryClient.ts` |
| Client store | **Zustand 4** | `components/WorkspaceContext.tsx` |
| Wire validation | **Zod 3.23** | `lib/schemas.ts` |
| Charts | **Recharts 2.12** | `components/dashboard/*.tsx` |
| Styling | **Tailwind 3.4** + design-token config | `tailwind.config.ts` |
| Theme switch | **next-themes** | `app/providers.tsx` |
| Icons | **lucide-react** | (used inline in pages) |
| Unit / component | **Vitest 1.6** + Testing Library + jsdom | `lib/*.test.ts` (42 cases) |
| E2E | **@playwright/test 1.44** | `e2e/` (11 specs, A–K) |
| Lint | **next lint** | tsconfig + eslint |
| Format | **Prettier** | `prettier --write …` |

### Why this set

- **Next.js 14 App Router + RSC** — file-system routing matches the "one file per page"
  mental model the team already has from the previous doc; server components let
  non-interactive panels (the four chart wrappers) be statically rendered.
- **TanStack Query for server state, Zustand for one piece of client state** — there is
  exactly *one* piece of client state worth a store: `{ businessId, setBusinessId }`.
  Everything else is server-derived and goes through TanStack. This is on purpose; both
  the rules and the implementation enforce it.
- **Recharts** — declarative, typed, plays well with React Server Components when
  passed a serializable payload. The chart components are dumb wrappers around a
  precomputed `Visual[]` array — see `insights/engine.py`.
- **Tailwind tokens, not raw classes** — `tailwind.config.ts` exposes six semantic
  tokens (`accent`, `surface`, `ink`, `line`, `ok`, `warn`, `bad`, `info`). Tailwind
  config is the single source of color truth in the UI (chapter 11).

---

## 3.3 Repository layout, layered

The mental model from chapter 00 is a stack with five layers. Here is the same
mapping, file-by-file.

```
F:\Git Repo\MoneyPlant
├── .env.example                      ← template for backend/.env
├── .gitignore                        ← .env*, .venv, node_modules, .next
├── LICENSE                           ← MIT
├── PUKU.md                           ← puku-cli harness guidance (don't edit)
├── README.md                         ← human-facing landing
│
├── backend/                          ┐
│   ├── .venv/                        │  Python 3.11+ venv (gitignored)
│   ├── .env                          │  active config (gitignored)
│   ├── pyproject.toml                │  ← dependencies
│   ├── alembic.ini                   │  ← migration runner config
│   ├── alembic/                      │
│   │   ├── env.py                    │  ← migration env, reads DATABASE_URL
│   │   └── versions/                 │
│   │       ├── 0001_initial.py       │
│   │       ├── 0002_data_sources.py  │
│   │       └── 0003_sync_dedup_columns.py
│   ├── app/                          │
│   │   ├── main.py                   │  ← create_app() + lifespan + routers
│   │   ├── api/                      │
│   │   │   ├── businesses.py         │
│   │   │   ├── transactions.py       │
│   │   │   ├── scenarios.py          │
│   │   │   ├── decisions.py          │
│   │   │   ├── imports.py            │
│   │   │   ├── insights.py           │
│   │   │   ├── alerts.py             │
│   │   │   ├── financing.py          │
│   │   │   ├── ai.py                 │
│   │   │   └── data_sources.py       │
│   │   ├── core/                     │
│   │   │   ├── config.py             │  Settings (lru_cache)
│   │   │   ├── logging.py            │  log_redact_financial wrapper
│   │   │   └── security.py           │  (placeholder for future auth)
│   │   ├── db/                       │
│   │   │   ├── base.py               │  Base = declarative_base()
│   │   │   ├── session.py            │  SessionLocal + get_db
│   │   │   └── mixins                │  UUIDPrimaryKeyMixin, TimestampMixin
│   │   ├── models/                   │
│   │   │   ├── business.py           │
│   │   │   ├── transaction.py
│   │   │   ├── scenario.py           │  Scenario + ScenarioVersion
│   │   │   ├── decision.py           │  DecisionReport + LlmExplanation
│   │   │   ├── import_job.py
│   │   │   └── data_source.py        │  DataSource + SyncRun
│   │   ├── schemas/                  │  Pydantic request/response
│   │   ├── engine/                   │  L1  pure-Decimal engines
│   │   │   ├── alerts.py             │     AlertConfig + evaluate_alerts
│   │   │   └── financing.py          │     annuity + DSCR ranking
│   │   ├── insights/                 │  L1 → view-model
│   │   │   └── engine.py             │     build_dashboard_insights(inputs)
│   │   └── services/                 │  L2 orchestration
│   │       ├── decisions/
│   │       │   └── evaluator.py      │     evaluate(): rules + laya (+llm)
│   │       ├── finance/              │  L1 building blocks
│   │       │   ├── money.py          │     Decimal primitives
│   │       │   ├── periods.py        │     MonthlyPeriod, month arithmetic
│   │       │   ├── metrics.py        │     compute_metrics()
│   │       │   ├── inventory.py      │     manufacturing / inventory / service
│   │       │   ├── profit_vs_cash.py │     reconcile_profit_and_cash
│   │       │   └── invariants.py     │     assert_invariants()
│   │       ├── rules/
│   │       │   └── engine.py         │     8-rule registry + aggregator
│   │       ├── simulation/
│   │       │   ├── runner.py         │     run_scenario() dispatcher
│   │       │   └── sensitivity.py    │     run_sensitivity()
│   │       ├── industry_adapters/
│   │       │   ├── base.py           │     IndustryAdapter ABC
│   │       │   ├── manufacturing.py
│   │       │   ├── inventory_based.py
│   │       │   └── service.py
│   │       ├── ingestion/
│   │       │   ├── csv.py            │     parse_rows + suggest_mapping + CANONICAL_FIELDS
│   │       │   └── xlsx.py           │     XLSX adapter (uses openpyxl data_only)
│   │       ├── sync/                 │
│   │       │   ├── connectors.py     │     Connector protocol + ConnectorReadResult
│   │       │   ├── file_connector.py │     path containment + .csv/.xlsx
│   │       │   ├── sql_connector.py  │     SELECT-only + quote + row limit
│   │       │   ├── service.py        │     run_sync + dedup + watermarks
│   │       │   └── scheduler.py      │     SyncScheduler daemon
│   │       ├── llm/
│   │       │   ├── base.py           │     ProviderMode, Explanation
│   │       │   ├── factory.py        │     get_provider(mode)
│   │       │   ├── ollama_provider.py
│   │       │   ├── openai_provider.py
│   │       │   └── anthropic_provider.py
│   │       └── laya/
│   │           └── adapter.py        │     assess_scenario + unavailable fallback
│   ├── tests/                        │  pytest (219 cases)
│   └── scripts/                      │  CLI tools
│
├── apps/                             ┘
│   └── web/                          ┐
│       ├── .env.local.example        │
│       ├── next.config.mjs
│       ├── tailwind.config.ts        │  semantic color tokens
│       ├── tsconfig.json
│       ├── vitest.config.ts
│       ├── playwright.config.ts
│       ├── package.json
│       ├── app/
│       │   ├── layout.tsx            │  root <html>, Inter, dark class
│       │   ├── page.tsx              │  landing
│       │   ├── providers.tsx         │  QueryClientProvider + ThemeProvider
│       │   └── (app)/
│       │       ├── layout.tsx        │  AppShell wrapper
│       │       ├── dashboard/page.tsx
│       │       ├── data/page.tsx
│       │       ├── simulator/page.tsx
│       │       ├── decisions/page.tsx
│       │       ├── decisions/[id]/page.tsx
│       │       ├── compare/page.tsx
│       │       ├── financing/page.tsx
│       │       ├── assistant/page.tsx
│       │       └── settings/page.tsx
│       ├── components/
│       │   ├── ui/                   │  primitives (Button, Card, …)
│       │   ├── dashboard/            │  Recharts wrappers + month panel
│       │   ├── AppShell.tsx
│       │   ├── WorkspaceContext.tsx
│       │   ├── AlertsPanel.tsx
│       │   ├── FinancingPanel.tsx
│       │   └── ThemeToggle.tsx
│       ├── lib/
│       │   ├── api.ts                │  apiGet/apiPost/apiPatch/apiDelete
│       │   ├── schemas.ts            │  Zod mirror of backend Pydantic
│       │   ├── format.ts             │  formatMoney / formatPercent
│       │   ├── queryClient.ts
│       │   ├── format.test.ts        │
│       │   └── schemas.test.ts       │
│       ├── e2e/                      │  Playwright (11 specs, A–K)
│       └── tests/                    │  Vitest co-located
│
├── docs/                             │  ← this site lives in docs/engineering/
│   ├── engineering/                  │
│   │   ├── README.md                 │
│   │   ├── 00-orientation.md
│   │   ├── 01-design-principles.md
│   │   ├── …                        │
│   │   └── 14-testing-and-ops.md
│   ├── PRODUCT_SPEC.md
│   ├── FINANCIAL_MODEL.md
│   ├── AI_AND_PRIVACY.md
│   ├── SECURITY_SELF_ASSESSMENT.md
│   ├── DESIGN_DECISIONS.md
│   ├── IMPLEMENTATION_STATUS.md
│   ├── TEST_PLAN.md
│   ├── ARCHITECTURE.md
│   └── DOC_VERIFICATION.md
│
└── sample_data/                      ┐
    ├── *.csv                         │  used by demo seed + sync tests
    ├── *.xlsx                        │
    └── ext_invoices.db               │  used by the SQL connector demo
                                     ┘
```

---

## 3.4 Where to make changes

| You want to… | Open these files first |
|---|---|
| Add a backend endpoint | `app/api/<feature>.py`, the matching `app/schemas/*.py`, then `app/services/*` |
| Add a column to an ORM table | The model in `app/models/*`, then a new Alembic revision under `alembic/versions/` |
| Add a scenario calculation | `app/services/finance/inventory.py` or a new file in `app/services/finance/`, then `app/simulation/runner.py` to dispatch |
| Add a rule | `app/services/rules/engine.py` (add a function, register in `RULES`) |
| Add an alert | `app/engine/alerts.py` (add a check + `Alert` instance to `evaluate_alerts`) |
| Add a metric | `app/services/finance/metrics.py` `compute_metrics`, then `app/schemas/finance.py` mirror |
| Add a financing rule | `app/engine/financing.py` (rank logic in `evaluate_financing_options`) |
| Add an LLM provider | New file in `app/services/llm/` + register in `app/services/llm/factory.py` |
| Add an ingestion column type | `app/services/ingestion/csv.py` `CANONICAL_FIELDS` |
| Add a sync connector | New file in `app/services/sync/*_connector.py`, extend `connectors.py` ABC |
| Add a UI page | `app/(app)/<feature>/page.tsx` + `app/api/<feature>.py` + Zod mirror in `lib/schemas.ts` |
| Add a chart | `app/components/dashboard/<chart>.tsx` + visual generator in `app/insights/engine.py` |
| Add a primitive | `app/components/ui/<component>.tsx` + use existing tokens |

---

## 3.5 Version drift, snapshots, and how this doc is kept honest

This documentation sits on commit `f01314a` of `main`. As the codebase moves:

1. **Every line citation is a starting point**, not a guarantee. When it drifts, search
   by the symbol, not the line.
2. **The "principles" in chapter 01 are load-bearing**. If a PR relaxes one, the doc
   needs a corresponding update — same review.
3. **The relationship between this site and the existing `*.md` files** is deliberate:
   - `engineering/` is the *system reference* — what it is and how it works.
   - `docs/` siblings are *concerns* — security, product spec, privacy, financial formulas
     in depth, testing strategy, design tokens.

If you find yourself wanting to put content that is "how the engine works" in the
*product spec* doc, or "what the product is for" in *engineering*, stop and pick a
different file.

---

*Next: [Chapter 04 — Data layer & migrations](04-data-layer.md)*