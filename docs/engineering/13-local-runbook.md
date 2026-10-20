# Chapter 13 — Local Development Runbook

> *Getting both processes running, seeding data, and the common failures you'll hit
> on day one.*

This is the chapter to open when you take a fresh checkout and want to see the dashboard
in your browser.

---

## 13.1 Prerequisites

| Tool | Version | Why |
|---|---|---|
| **Python** | 3.11+ | `pyproject.toml:25` (`requires-python = ">=3.11"`); 3.12 also works |
| **Node.js** | 18+ (developed on 24) | Next.js 14 minimum |
| **npm** | 10+ (developed on 11) | ships with Node |
| **uv** | latest | manages the backend venv (`backend/.venv`) |

Optional:

- **Ollama** at `http://localhost:11434/v1` — default LLM provider. Without it, the
  Assistant page degrades to "unavailable" and the rest of the product still works.
- **OpenAI / Anthropic API keys** — only needed if you want to swap providers. See
  chapter 07.

---

## 13.2 First-time setup

From `F:\Git Repo\MoneyPlant` (or the equivalent bash path
`/mnt/f/Git\ Repo/MoneyPlant`):

### Backend

```bash
# 1. Create the Python 3.11 venv (idempotent; safe to skip if it already exists)
cd backend
uv venv --python 3.11 .venv

# 2. Activate and install
source .venv/bin/activate      # macOS / Linux / WSL
# or  .venv\Scripts\activate   # Windows PowerShell
uv pip install -e ".[dev]"

# 3. Copy the env template (only the first time)
cp .env.example .env
# then edit .env: DATABASE_URL, CORS_ORIGINS, AI_DEFAULT_MODE, …
```

### Frontend

```bash
# In a separate terminal
cd apps/web
npm install
cp .env.local.example .env.local
# edit .env.local: NEXT_PUBLIC_API_BASE_URL (leave empty for default split)
```

---

## 13.3 Migrations and seed data

```bash
# backend venv active
cd backend

# Apply all migrations
.venv/bin/alembic upgrade head       # Linux/macOS
# or  .venv\Scripts\alembic.exe upgrade head   # Windows

# Seed 5 demo businesses (idempotent)
.venv/bin/python -m scripts.seed_demo
```

`seed_demo.py` skips businesses that already exist (matched on `(name, industry)`), so
running it repeatedly is safe.

After seed, you should see 5 demo businesses — **Aurora Garments** (manufacturing),
**Main Street Boutique** (retail), **Helios Consulting** (service), **Pioneer
Distribution Co.** (wholesale), and **Maple Street Eatery** (food). Each is clearly
labeled synthetic on the dashboard. Open any of them to see the seeded financials
immediately.

---

## 13.4 Starting both processes

```bash
# Terminal 1 — backend
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd apps/web
npm run dev
```

Verify each:

```bash
curl http://localhost:8000/docs         # Swagger UI loads
curl http://localhost:8000/api/health   # {"status": "ok"}
curl http://localhost:3000/             # Next.js landing page
```

Then open `http://localhost:3000` in a browser. Pick a seeded workspace; the dashboard
should populate within ~1 second.

---

## 13.5 The npm scripts

```jsonc
// apps/web/package.json
{
  "scripts": {
    "dev":          "next dev -p 3000",
    "build":        "next build",
    "start":        "next start -p 3000",
    "lint":         "next lint --dir app --dir components --dir lib",
    "typecheck":    "tsc --noEmit",
    "test":         "vitest run",
    "test:watch":   "vitest",
    "test:e2e":     "playwright test",
    "format":       "prettier --write \"app/**/*.{ts,tsx}\" \"components/**/*.{ts,tsx}\" \"lib/**/*.ts\""
  }
}
```

The pair that gates every PR:

```bash
cd apps/web
npm run typecheck     # tsc --noEmit   (no JS output; type errors only)
npm run lint
npm run test          # vitest run     (42 unit + component cases)
npm run build         # production build (catches RSC vs client boundary mistakes)
```

---

## 13.6 The Python scripts

`backend/pyproject.toml` defines `[project.optional-dependencies.dev]` including
pytest, ruff, mypy. The `scripts/` directory holds CLI entry points.

```bash
# Run the full backend test suite
cd backend
.venv/bin/pytest                                # 219 tests, ~3s

# Run a single file
.venv/bin/pytest tests/test_rules.py -v

# Run only the tests with @pytest.mark.slow
.venv/bin/pytest -m slow

# Lint
.venv/bin/ruff check .

# Typecheck
.venv/bin/mypy app

# Run an ad-hoc CLI
.venv/bin/python -m scripts.sync_sources --list
.venv/bin/python -m scripts.sync_sources --all
.venv/bin/python -m scripts.seed_demo                # idempotent
```

---

## 13.7 The `.env` files

Two env files live outside the repo (gitignored):

```
   backend/.env                  ← DB, AI providers, scheduler, logging
   apps/web/.env.local           ← NEXT_PUBLIC_API_BASE_URL (optional)
```

The templates are committed:

```
   backend/.env.example
   apps/web/.env.local.example
```

### The minimum backend `.env`

```dotenv
# backend/.env — the smallest working config

DATABASE_URL=sqlite:///./moneyplant.db
CORS_ORIGINS=http://localhost:3000

# AI
AI_DEFAULT_MODE=local
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.1:8b

# Sync scheduler (defaults to enabled)
SYNC_SCHEDULER_ENABLED=true
SYNC_SCHEDULER_INTERVAL_SECONDS=300

# Logging
LOG_LEVEL=INFO
LOG_REDACT_FINANCIAL=true
```

Anything missing falls back to the `Settings` defaults in `app/core/config.py`.

### The minimum frontend env

```dotenv
# apps/web/.env.local — empty is fine for local dev

# When the backend runs on a non-default port or host, point here:
# NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Leave it blank to use relative paths (the recommended local-dev configuration).

---

## 13.8 The demo data

Five businesses in `scripts/seed_demo.py`, one per industry:

| Business | Industry | Notable demo hook |
|---|---|---|
| Aurora Garments | manufacturing | raw materials + labor + capacity + `material_shortage` |
| Main Street Boutique | retail | inventory + shrinkage (24% shrinkage assumption) |
| Helios Consulting | service | billable hours + project revenue + invoice delay |
| Pioneer Distribution Co. | wholesale | high inventory exposure (30% max) + payment delay |
| Maple Street Eatery | food | retail-like shape with tighter expiry + low reserve |

Each has 3–6 months of seed transactions in `sample_data/*.csv` and a `Q1 baseline`
scenario wired for the simulator. The four CSVs are named after the business, and
`sample_data/README.md` maps file → business.

The seeded files under `sample_data/` are used by both seeded `DataSource` rows and the
demo's sync triggers, so the dashboard's `FreshnessStrip` has something to show on day
one.

---

## 13.9 Common day-one issues

### "ModuleNotFoundError: app" when starting uvicorn

You forgot to activate the venv, *or* you ran uvicorn from a directory that isn't
`backend/`. The uvicorn invocation assumes `cd backend` first.

### "Alembic can't find migrations"

Run `alembic upgrade head` from `backend/`. The CLI resolves `alembic.ini` from the
cwd.

### "CORS error" in the browser console

`CORS_ORIGINS` in `backend/.env` does not match the URL the browser is using. The
default is `http://localhost:3000`. If you reach the app at a different origin (e.g.
`http://127.0.0.1:3000` or a forwarded port), add it to the comma-separated list.

### "AI assistant unavailable" with Ollama installed

Check:

1. `curl http://localhost:11434/v1/models` returns 200.
2. `OLLAMA_BASE_URL` matches your install (default is `http://localhost:11434/v1`).
3. The model is pulled: `ollama pull llama3.1:8b`.
4. `backend/.env` has `AI_DEFAULT_MODE=local`.

### "tsx: command not found" on Windows

Use the project's npm scripts, not the binary directly. `npm run dev` invokes the local
`node_modules/.bin` automatically.

### Dashboard stays empty

Either you have no transactions, or `businessId` is null (the workspace selector was
missed). Pick a workspace from the sidebar.

### Sync errors show "path_outside_root"

Your `DataSource.config.path` resolves to a file outside `settings.file_source_root`.
Either move the file, or change the path to be relative to the root.

---

## 13.10 The dev-quality loop

A short loop to use while iterating:

```bash
# In one shell — backend with auto-reload
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

# In another — frontend with hot reload
cd apps/web && npm run dev

# In a third — tests on demand
cd apps/web && npm run typecheck && npm run test:watch
cd backend && .venv/bin/pytest -x
```

Three terminals, full feedback. The auto-reload on uvicorn is fast enough that backend
changes are reflected in <1s; Next.js Fast Refresh handles frontend changes the same
way.

---

## 13.11 Resetting local state

When something is wedged and you want a clean slate:

```bash
# Backend
cd backend
rm moneyplant.db                              # WIPE the SQLite DB
.venv/bin/alembic upgrade head                # recreate schema
.venv/bin/python -m scripts.seed_demo         # reseed

# Frontend
cd apps/web
rm -rf .next                                  # clear the Next.js cache
npm run dev
```

The `.venv` is gitignored but otherwise stable. Recreating it costs ~30s and is rarely
needed; only do it after a `pyproject.toml` change that adds/removes a dep.

---

## 13.12 Linting, formatting, and CI parity

| Tool | Backend | Frontend |
|---|---|---|
| Lint | `ruff check .` | `npm run lint` |
| Format | `ruff format .` | `npm run format` |
| Typecheck | `mypy app` | `npm run typecheck` |
| Tests | `pytest` | `npm run test` / `npm run test:e2e` |

`tsc --noEmit` is the gate that catches Zod-mirror drift *first* — if a Pydantic schema
changes without a Zod update, the consuming page breaks at the type level before it
ever runs.

---

## 13.13 Troubleshooting tool matrix

| Symptom | First check |
|---|---|
| Uvicorn fails to start | `python -V` ≥ 3.11; `.venv/` exists |
| Frontend can't reach backend | `curl http://localhost:8000/api/health` |
| Dashboard never stops loading | Network tab: a 4xx → check the backend log |
| Decision detail empty | The `latest_version_id` was missing; the scenario needs a re-run |
| Assistant silently returns "unavailable" | `/api/ai/health`; check provider mode |
| Sync stuck at "scheduled" | `SYNC_SCHEDULER_ENABLED=false`? Check env; or run `--all` manually |
| Migrations fail | Check the alembic version chain; `alembic current` shows the head |
| Tests pass locally, fail in CI | Check Python version, Node version |
| A typo in a CSV is permanent | `Test plan` / known limitation; intentional gap |

---

*Next: [Chapter 14 — Testing, deployment & known gaps](14-testing-and-ops.md)*