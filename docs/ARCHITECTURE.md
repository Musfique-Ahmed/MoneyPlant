# Architecture — MoneyPlant

## 1. System overview

MoneyPlant is a **modular monolith** consisting of a Next.js frontend, a FastAPI backend, and a shared persistence layer (SQLite by default, Postgres-ready). There is one database, one web app, one API service. No microservices, no message queue, no distributed cache. The structure is modular so the boundaries are real and the parts can be reasoned about independently.

```
┌─────────────────────────────────────────────────────────┐
│ Browser (Next.js 14 App Router, RSC + client islands)   │
│  - React Query for client-side fetching                  │
│  - Zod for runtime response validation                  │
│  - Local UI primitives (no external UI dep)              │
└─────────────────────────────────────────────────────────┘
                       │ HTTP / JSON
                       ▼
┌─────────────────────────────────────────────────────────┐
│ FastAPI backend (Python 3.11)                            │
│  /api/health, /api/config/public                         │
│  /api/businesses, /api/imports/*, /api/transactions      │
│  /api/financial-summary                                   │
│  /api/scenarios/* (simulate, save, compare, rerun)       │
│  /api/decisions/* (evaluate, explain, get)               │
│  /api/ai/providers, /api/ai/health, /api/assistant/chat  │
└─────────────────────────────────────────────────────────┘
        │                          │                  │
        ▼                          ▼                  ▼
┌──────────────────┐  ┌─────────────────────┐  ┌────────────────┐
│ Deterministic    │  │ Rule engine + Laya  │  │ LLM providers  │
│ finance engine   │  │ adapter             │  │ (Ollama,       │
│ (pure functions, │  │                     │  │  OpenAI,       │
│  Decimal)        │  │                     │  │  Anthropic)    │
└──────────────────┘  └─────────────────────┘  └────────────────┘
                       │
                       ▼
        ┌────────────────────────────┐
        │ SQLAlchemy + Alembic       │
        │ (SQLite default, Postgres  │
        │  via DATABASE_URL)         │
        └────────────────────────────┘
```

## 2. Logical layers

| Layer | Path | Responsibility |
|---|---|---|
| Presentation | `apps/web/app/**` | Render UI, capture inputs, display results. RSC fetches dashboard data; client islands handle interactive flows. |
| API | `backend/app/api/**` | HTTP surface; request validation; auth gates (when added); serialization. |
| Ingestion | `backend/app/services/ingestion/**` | CSV/XLSX parse, column mapping suggestions, validation issue reporting. |
| Financial domain | `backend/app/services/finance/**` | Pure functions over typed inputs. **No FastAPI or LLM imports.** |
| Simulation | `backend/app/services/simulation/**` | Run scenarios; sensitivity; cash-flow timing. |
| Rules | `backend/app/services/rules/**` | Rule registry, evaluator, severity aggregation. |
| Laya adapter | `backend/app/services/laya/**` | Thin wrapper around `laya.Router().predict()`. |
| LLM providers | `backend/app/services/llm/**` | Provider abstraction, factory, health checks. |
| Reporting | `backend/app/services/reporting/**` | Decision report assembly. |
| Industry adapters | `backend/app/services/industry_adapters/**` | Per-industry input extensions and validators. |
| Persistence | `backend/app/db/**`, `backend/app/models/**` | SQLAlchemy models, Alembic migrations. |
| Schemas | `backend/app/schemas/**` | Pydantic v2 request/response contracts. |
| Observability / tests | `backend/tests/**`, `backend/app/core/logging.py` | pytest, structured logging that excludes financial records. |

## 3. Cross-cutting decisions

### 3.1 Money

All monetary values in the backend are `decimal.Decimal`. A `Money` value object wraps a `Decimal` and a `Currency` enum and enforces consistent rounding (`ROUND_HALF_UP` at 2 decimal places for most currencies). The frontend formats only — never recalculates.

### 3.2 Determinism

The financial engine has no time-of-day, no I/O, no random sampling, no LLM calls. Re-running a scenario with the same inputs and engine version returns the same bytes. Sensitivity is one-at-a-time around the user's baseline values; it is **not** a statistical forecast.

### 3.3 Frontend as renderer

The frontend may show preview values for responsiveness, but every authoritative number comes from a backend endpoint whose response is Zod-validated. If a preview disagrees with a server response, the server wins. Preview logic is unit-tested for consistency with the backend.

### 3.4 Hard vs soft rules

A small set of rules are **hard** (`NEGATIVE_CLOSING_CASH`, `CAPACITY_EXCEEDED`, `MATERIAL_SHORTAGE` when shortage > 0). Their `breached` status cannot be downgraded by Laya preference or LLM recommendation. All other rules are advisory. This is enforced in `services/decisions/evaluator.py`.

### 3.5 LLM provider boundary

The LLM explains, never calculates. The structured context sent to the provider contains only:

- The user's question
- Compact computed metrics (not raw transactions)
- Computed scenario outcomes
- Rule evaluation summaries
- Laya assessment (when present)
- Explicit assumptions and warnings
- Stated business goal

A response that fails Pydantic validation is surfaced as `unavailable`, not coerced.

### 3.6 Laya boundary

Laya is invoked through `laya.Router().predict(state, questions, model=...)`. We never invent functions beyond what the upstream package documents. A `LayaAssessment` includes the question, the answer label, any probability, and the model identifier. Missing checkpoints, import errors, and router failures all produce `unavailable`, never a fabricated label.

### 3.7 Privacy

- API keys are read from process env only; never accepted from the client; never echoed back.
- The `/api/config/public` endpoint returns only safe flags (e.g., which providers are *configured*, not their keys).
- Logs are structured and **do not** include raw transaction descriptions, business names, or monetary values.
- The privacy settings page reports provider health from a real `health_check()` call; it never shows a green check without a successful probe.
- No silent fallback from local to API. If the user selects local and local fails, they see an actionable error.

### 3.8 Persistence

SQLAlchemy 2.x with Alembic migrations. Default is SQLite (`./moneyplant.db`). Postgres works by setting `DATABASE_URL=postgresql+psycopg://...`. Each business has its own workspace; all queries are scoped by `business_id`. In MVP single-tenant mode, `business_id` comes from the request body's `business_id` field or a session cookie (not implemented yet — see `IMPLEMENTATION_STATUS.md`).

## 4. API surface (summary)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness, returns `{"status": "ok"}` |
| GET | `/api/config/public` | Public config flags (no secrets) |
| GET, POST | `/api/businesses` | List, create |
| GET, PATCH, DELETE | `/api/businesses/{id}` | Read, update, delete |
| POST | `/api/imports/preview` | Parse file, return headers, row preview, suggested mapping |
| POST | `/api/imports/validate` | Validate rows, return per-row issues |
| POST | `/api/imports/commit` | Persist imported rows + import job record |
| GET | `/api/imports` | List import jobs |
| GET | `/api/imports/{id}` | Read import job + validation summary |
| GET | `/api/transactions` | List transactions for a business |
| GET | `/api/financial-summary` | Computed metrics + warnings |
| POST | `/api/scenarios/simulate` | Run simulation; do not persist |
| POST | `/api/scenarios` | Save scenario + version |
| GET | `/api/scenarios` | List |
| GET | `/api/scenarios/{id}` | Read |
| PATCH | `/api/scenarios/{id}` | Update inputs (creates new version) |
| POST | `/api/scenarios/{id}/rerun` | Rerun same version, return updated result |
| POST | `/api/scenarios/compare` | Compare baseline + alternatives |
| POST | `/api/decisions/evaluate` | Run rules + Laya, return decision report |
| GET | `/api/decisions/{id}` | Read decision report |
| POST | `/api/decisions/{id}/explain` | Run LLM explanation on the report |
| GET | `/api/ai/providers` | List configured providers + capabilities |
| GET | `/api/ai/health` | Real health-check of selected provider |
| POST | `/api/assistant/chat` | Chat grounded in computed results |

## 5. Data model (selected entities)

- `Business` — workspace, industry, currency, fiscal year start, settings.
- `Transaction` — date, amount, currency, direction (`inflow|outflow`), category, payment status, cash-flow date, source provenance.
- `ImportJob` — file metadata, mapping, status, validation summary.
- `Scenario` — name, baseline reference, industry, status, list of versions.
- `ScenarioVersion` — immutable inputs, engine version, calculation timestamp.
- `ScenarioResult` — computed metrics + warnings + invariants check.
- `RuleConfig` — per-business thresholds.
- `DecisionReport` — context, baseline, proposed action, projected outcome, rule evaluations, Laya assessment, recommendation, caveats.
- `LayaAssessment` — question, answer label, probability, model id, raw response (debug only).
- `Explanation` — LLM-generated explanation with provider, model, validation status.

## 6. Deployment shape

- Backend: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` for dev. Gunicorn + Uvicorn workers behind a reverse proxy for prod.
- Web: `next dev` for dev. `next build && next start` for prod. Output is standalone; deployable to Vercel, Render, Fly, or a Node server.
- DB: SQLite for local dev; Postgres in any real deployment.
- CORS: dev allows `http://localhost:3000`; prod restricted to the configured `WEB_ORIGIN`.

## 7. Security posture

- File uploads: size limit (10 MB), extension allowlist, row count limit, encoding check, content sniffing. XLSX read with `data_only=True` (no formula evaluation).
- API inputs: Pydantic validation at every endpoint.
- Database: parameterized queries via SQLAlchemy ORM.
- Secrets: env-only, never returned in responses.
- Logging: structured JSON; financial fields redacted by default.
- Auth: not implemented in MVP. Trust boundary is documented: do not expose this build on the public internet without adding authentication.

## 8. What this architecture is not

- It is not a microservices platform. The boundaries are modular but the deployment is a single API service.
- It is not a real-time streaming system. Imports are batch; scenarios are request/response.
- It is not multi-tenant without further work. The data model supports it (every row is scoped by `business_id`), but the API does not yet enforce auth.