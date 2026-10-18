# PUKU.md

Guidance for puku-cli when working in this repository.

## Project

**MoneyPlant** is a finance copilot for small / mid-sized businesses. It is a two-process monorepo:

- `backend/` — FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2 service. Simulation, ingestion, rule engine, Laya soft-assessment, LLM explanation. Default DB is SQLite (`backend/moneyplant.db`).
- `apps/web/` — Next.js 14 (App Router) + React 18 + TanStack Query + Zod + Recharts. Talks to the backend at `http://localhost:8000` (configured via `NEXT_PUBLIC_API_BASE_URL`).

The repo is already scaffolded and runnable; PUKU is no longer a stub.

## Scripts

Use the project's package / project scripts. Do not invoke underlying binaries directly unless a script is missing.

### Backend (`backend/`)

- `uvicorn app.main:app --reload --port 8000` — dev server (no script wrapper; activate the venv first)
- `alembic upgrade head` — apply migrations
- `pytest` — full test suite (115 tests across simulation, rules, decisions, ingestion, llm, laya, finance, schemas)
- `python -m scripts.seed_demo` — seed 5 demo businesses (one per industry) + sample transactions + baseline scenarios

The backend uses a Python 3.11 venv at `backend/.venv`. Activate with `source backend/.venv/bin/activate` (or call binaries directly).

### Frontend (`apps/web/`)

- `npm run dev` — start the dev server (binds 3000)
- `npm run build` — production build
- `npm run start` — run the production build
- `npm run lint` — ESLint
- `npm run format` — Prettier
- `npm run typecheck` — `tsc --noEmit`
- `npm run test` — Vitest unit + component tests
- `npm run test:e2e` — Playwright

If a script is missing, ask before adding it.

## Architecture

- **Routing** — App Router (`apps/web/app`). Top-level layout at `apps/web/app/layout.tsx`. The authenticated app is in the `(app)` route group: `dashboard`, `data`, `simulator`, `decisions`, `compare`, `assistant`, `settings`. Each route page calls the backend via `lib/api.ts` (`apiGet` / `apiPost`) and validates the response with Zod schemas in `lib/schemas.ts`.
- **State** — TanStack Query for server state. The active business id is held in `components/WorkspaceContext`. There is no Redux / Zustand.
- **Data layer** — SQLite + SQLAlchemy 2 + Alembic. The backend owns all persistence. The frontend never talks to the DB directly.
- **AI** — Multi-provider abstraction (`app/services/llm/`): local Ollama (default), OpenAI, Anthropic. Provider selection is via `AI_DEFAULT_MODE` in `backend/.env`. The local provider returns `unavailable` (never silent green) when Ollama is not reachable.
- **Decision engine** — Rule-first. Hard rules in `backend/app/services/rules/engine.py` are authoritative; Laya is advisory; the LLM only **explains** the verdict (separate `/api/decisions/{id}/explain` request). `aggregate_status` precedence: hard breach → `reject`; ≥½ rules not evaluable → `insufficient_data`; any soft warning → `proceed_with_caution`; all pass → `proceed`.
- **Auth** — None at the moment. The frontend has a single workspace context; this is a local dev / pilot product.
- **Styling** — Tailwind. Tokens defined in `tailwind.config.ts` (`accent`, `surface-*`, `ink-*`, `line`, `ok`, `warn`, `bad`).
- **Folder layout** — Feature-sliced inside `apps/web/app/(app)/<feature>/page.tsx`. Reusable UI in `apps/web/components/ui/`.

## Backend layout

```
backend/
  app/
    api/        # FastAPI routers (businesses, scenarios, decisions, transactions, imports, ai, laya)
    core/       # config, logging, currency utils
    db/         # session, base
    models/     # SQLAlchemy ORM
    schemas/    # Pydantic request/response models
    services/
      decisions/   # orchestrator that calls rules + laya + llm
      finance/     # Decimal arithmetic, periods, money utils
      ingestion/   # CSV / Excel parsing + mapping
      laya/        # Laya adapter (soft assessment)
      llm/         # provider abstraction (Ollama / OpenAI / Anthropic)
      rules/       # deterministic rule engine + aggregator
      simulation/  # runner + sensitivity
    scripts/    # CLI tools (seed_demo lives in /scripts, imported here for sys.path)
  alembic/      # migrations
  tests/        # pytest suite
```

## Branching & PRs

**GitHub Flow.** All changes go through a pull request to `main`.

- `main` is always deployable
- Branch off `main`: `feat/<short-desc>`, `fix/<short-desc>`, `chore/<short-desc>`, `refactor/<short-desc>`, `docs/<short-desc>`
- One logical change per PR — keep PRs small and reviewable
- PR title = the eventual squash-merge commit message (imperative, ≤70 chars)
- Squash-merge by default; delete the branch on merge
- At least one approval before merge; CI must be green

## Testing

Both unit and E2E coverage is expected. Run from `apps/web/`:

- **Unit / component:** Vitest + React Testing Library. Test behavior, not implementation. Co-locate tests with the file under test (`Foo.tsx` → `Foo.test.tsx`).
- **E2E:** Playwright (`apps/web/e2e/`). Cover critical user paths — create business, import CSV, save scenario, evaluate decision, ask assistant.
- New features ship with tests for the happy path and the most likely failure modes. Bug fixes include a regression test.

Backend tests run from `backend/` with `pytest` (115 tests).

## Style

- **TypeScript everywhere** in `apps/web`. No `.js`/`.jsx` source files in `apps/web/src`. Use `import type` for type-only imports.
- **Prettier** owns formatting. `npm run format` (or rely on a future format-on-edit hook).
- **ESLint** with the Next.js config + TypeScript rules.
- **`tsc --noEmit` must pass** before a change is considered done.
- **Python:** Decimal arithmetic for money — never `float`.

## Gotchas

- **No live secrets in the repo.** `.env` / `.env.local` are gitignored. Backend has a `.env` template at `backend/.env.example`; frontend at `apps/web/.env.local.example`.
- **No pip on the host Python 3.14.** The backend uses an isolated Python 3.11 venv at `backend/.venv` created with `uv`. Re-create with `uv venv --python 3.11 .venv` then `uv pip install -e .[dev]`.
- **Local LLM is optional.** Without Ollama, `/api/ai/health` returns `unavailable` and the Assistant page shows the empty-state hint. The decision engine does not require the LLM.
- **Decision schema drift.** `ScenarioRead` exposes `latest_version_id`; the decisions page sends `scenario_version_id` (not `scenario_id`). The Zod mirror in `apps/web/lib/schemas.ts` must stay in sync with backend Pydantic models — parsing fails loudly if it drifts.
- **Demo data is idempotent.** `scripts/seed_demo.py` skips businesses that already exist (matched on `name` + `industry`). Safe to re-run.
- **Windows path.** The repo lives at `F:\Git Repo\MoneyPlant` (note the space). Quote the path in shell commands; the WSL view is `/mnt/f/Git Repo/MoneyPlant`.
- **No `ripgrep` in the puku-cli sandbox.** File search and content search tools are degraded. Read the specific file once you know its path, or ask the user to paste the path.

## Local run quickstart

From `F:\Git Repo\MoneyPlant` (or `/mnt/f/Git Repo/MoneyPlant` in WSL):

```
# Backend
cd backend
.venv/bin/alembic upgrade head         # apply migrations
.venv/bin/python -m scripts.seed_demo  # (idempotent) 5 demo businesses
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (new shell)
cd apps/web
npm run dev
```

The frontend will be at http://localhost:3000; the API at http://localhost:8000/docs.
