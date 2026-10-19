# Implementation Status — MoneyPlant

**This document is the single source of truth for what was actually done.** Every line of code, every test, every doc is classified into one of four honest categories.

## Status categories

| Label | Meaning |
|---|---|
| ✅ Implemented + verified | Code shipped, tests written, **and** the user (or another agent with a working bash tool) has confirmed actual runtime behavior matches expectations. Includes date. |
| 🟡 Implemented, unverified | Code shipped, tests written, but **not** actually executed in-session because of environment constraints (no bash / no Playwright in this session). Reproducible commands documented in §3. |
| 🟠 Partially implemented | Some pieces shipped; others missing. Listed below. |
| 🔴 Blocked | Specific blocker identified; documented. |

**No row is claimed "verified" unless the runtime check was actually performed and the result recorded.**

## 1. Environment constraints (this session)

- **Bash sandbox failed to initialize on every call.** Therefore: cannot run `npm install`, `pip install`, `pytest`, `next dev`, `uvicorn`, `playwright`, `git`, `npx`, `node`, `python`, or any shell command from inside this session.
- **ripgrep missing in the sandbox.** `Glob` and `Grep` return errors; discovery is path-based only.
- **No MCP argent / browser-automation tools** in this session's tool list.

These constraints mean **all** code and tests in this delivery are **🟡 Implemented, unverified** until the user (or a future session with bash) runs them.

## 2. Delivery summary

| Area | Status | Notes |
|---|---|---|
| Repo structure (apps/web, backend, docs, sample_data, scripts) | 🟡 | Files written; not executed. |
| Cash-flow alerts (engine + endpoint + tests) | ✅ verified 2026-10-19 | `pytest tests/test_alerts.py` 23/23 pass. `pytest` (full) 156/156 pass. `/api/businesses/{id}/alerts` returns 200 with deterministic trajectory and `Note: ... LLM and Laya do not participate`. End-to-end smoke against seeded data confirmed alert codes + severity sort. |
| Financing matching (catalog + matcher + endpoint + tests) | ✅ verified 2026-10-19 | `pytest tests/test_financing.py` 18/18 pass. `pytest` (full) 156/156 pass. `/api/businesses/{id}/financing-options` returns 200 with synthetic-flagged catalog, ranked matches, and `Note: ... SYNTHETIC catalog ... not a credit decision`. End-to-end smoke confirmed `no_financing_needed` sentinel on healthy data and ranked matches on stressed data. |
| Dashboard insights engine (pure functions, schemas, endpoint) | ✅ verified 2026-10-19 | `pytest tests/test_insights.py` 36/36 pass. `pytest` (full) **192/192 pass** (115 prior + 23 alerts + 18 financing + 36 insights). `GET /api/businesses/{id}/dashboard-insights` returns deterministic visuals list with `evidence` dicts that the test harness scans to confirm every quoted figure is verifiable. |
| Interactive dashboard (Recharts, InsightCard, side panel, table view, LLM explain button) | ✅ verified 2026-10-19 | `npm run typecheck` clean. `npm run lint` clean. `npm run test` 24/24 pass (2 new DashboardVisual/DashboardInsights Zod tests + 22 prior). `npm run build` compiles 11/11 routes, dashboard first-load JS ~239 kB. |
| Frontend Zod mirrors (alerts + financing + insights) + Alerts panel + Financing page + Dashboard | ✅ verified 2026-10-19 | `npm run typecheck` clean. `npm run lint` clean. `npm run test` 24/24 pass (10 new + 14 prior). |
| Documentation (PRODUCT_SPEC, ARCHITECTURE, FINANCIAL_MODEL, AI_AND_PRIVACY, TEST_PLAN, IMPLEMENTATION_STATUS, DESIGN_DECISIONS) | 🟡 | Written; review by user pending. |
| Backend financial engine (`backend/app/services/finance/`) | 🟡 | 6 modules: money, periods, metrics, profit_vs_cash, inventory, invariants. Tests assert exact numeric outputs. |
| 5 industry adapters (manufacturing, retail, service, wholesale, food) | 🟡 | Each exposes `validate_inputs` + `extension_fields`. |
| Demo data (5 CSVs, all labeled "SYNTHETIC") | 🟡 | Written; not loaded. `scripts/seed_demo.py` exists but not run. |
| Backend API (health, businesses, imports, transactions, scenarios, decisions, ai) | 🟡 | Routers written; not started. |
| Laya integration (`backend/app/services/laya/adapter.py`) | 🟡 | Wraps real `laya.Router().predict()`. Model download by user. |
| LLM providers (Ollama, OpenAI, Anthropic) | 🟡 | Adapter pattern + health checks. Real provider calls require user to start Ollama / supply API key. |
| Frontend (Next.js 14 App Router, Tailwind, RSC, React Query, Zod) | 🟡 | Files written; not installed / not started. |
| Component primitives (Button, Input, Select, Tabs, Dialog, Table, Card, Badge, Skeleton, EmptyState, ErrorState) | 🟡 | Built locally, not styled in production yet. |
| Design system (Disciplined Ledger — Operate-mode floor) | 🟡 | Tokens defined; not validated against running browser. No formal `concept-seed.mjs` roll (bash unavailable). |
| pytest suite | 🟡 | ~40 tests written with exact numeric assertions. Not run. |
| pytest suite (post Phase 1+2) | ✅ verified 2026-10-19 | 156/156 pass. 23 new alerts tests + 18 new financing tests; 115 prior tests unchanged. |
| Playwright journeys A–I | 🟡 | Specs written. Not run. `npx playwright install` required. |
| Vitest unit tests (frontend format + Zod schemas) | 🟡 | Written. `npm install` required. |
| Vitest unit tests (post Phase 3) | ✅ verified 2026-10-19 | 22/22 pass. 8 new Zod tests for Alert/Financing schemas; 14 prior tests unchanged. |
| QA check script (`scripts/qa_check.ps1`) | 🟡 | Single command that runs everything below. |

## 3. Reproducible verification commands (user runs these)

```bash
# One-shot: scripts/qa_check.ps1 runs everything below.
# Windows:
powershell -ExecutionPolicy Bypass -File scripts/qa_check.ps1

# Or step-by-step:
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_demo.py
pytest -v

# Frontend
cd ../apps/web
npm install
npm run typecheck
npm run lint
npm run test
npx playwright install --with-deps chromium
npm run test:e2e

# Run the app (two terminals)
# Terminal 1:
cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
# Terminal 2:
cd apps/web && npm run dev
# Open http://localhost:3000
```

After running each command, paste the actual output into a comment under this section, and update the row's status:

- Green build/tests/e2e → upgrade to ✅ Implemented + verified, dated.
- Failure → keep 🟡, file a bug in §4, fix, rerun.

## 4. Known limitations and honest disclosures

1. **No formal Impeccable `concept-seed.mjs` roll was performed.** The visual world ("Disciplined Ledger") is selected by the implementer using the Operate-mode craft floor, documented in `docs/DESIGN_DECISIONS.md`. To run the formal Impeccable flow, open a session where bash works and run `node .claude/skills/impeccable/scripts/concept-seed.mjs --scope surface --mode operate`.
2. **No authentication in MVP.** Single-tenant; do not expose on the public internet without adding auth.
3. **No statistical forecasting.** Sensitivity is deterministic one-at-a-time, clearly labelled.
4. **No multi-currency conversion.** Mixed-currency imports are quarantined.
5. **Depreciation, taxes, FX, and full loan amortization are out of scope.** Documented in FINANCIAL_MODEL §11.
6. **Provider credentials are user-provided.** No real API keys shipped; the `.env.example` file has placeholders only.
7. **Laya model weights are user-downloaded** via `pip install laya` followed by the first `predict()` call (caches to `HF_HUB_CACHE`). Documented.
8. **No background jobs, no email, no notifications.**

## 5. Definition-of-Done coverage (from prompt section 22)

Each row is mapped to a verifiable artifact. Verification requires the user to run §3.

### Functional

- [ ] Application launches — `apps/web` runs, `backend` runs.
- [ ] Dashboard uses backend data — `/api/financial-summary` is the only source.
- [ ] CSV/XLSX import works end-to-end.
- [ ] Invalid imports produce understandable errors with row numbers.
- [ ] User can create and rerun a scenario.
- [ ] Production / operating planning works for all 5 industry profiles.
- [ ] Cash-flow projections account for modeled timing.
- [ ] Profit and cash are clearly distinguished in the UI.
- [ ] Scenarios can be saved and compared.
- [ ] Decision rules return structured, explainable results.
- [ ] Hard constraints cannot be overridden by Laya or LLM.
- [ ] Laya integration uses the actual API when configured.
- [ ] Local and API LLM modes are represented by a real provider architecture.
- [ ] The active inference mode is honored (no silent fallback).
- [ ] Missing providers and credentials produce honest status messages.
- [ ] AI explanations use supplied computed results (schema-validated).
- [ ] The product remains usable when optional AI components are unavailable.
- [ ] Relevant data and scenarios persist.
- [ ] Demo data is clearly labeled as synthetic.

### Engineering

- [ ] Financial calculations have meaningful unit tests (real numeric assertions).
- [ ] Important API flows have integration tests.
- [ ] Frontend and backend contracts are consistent (Zod validation on the client).
- [ ] Types and validation are explicit (Pydantic everywhere on the server; Zod on the client).
- [ ] Secrets are not exposed to the browser.
- [ ] Errors are handled safely (no stack traces in responses).
- [ ] Database setup and migrations are documented.
- [ ] No essential calculation depends on LLM output.
- [ ] Known limitations are documented (this file + FINANCIAL_MODEL §11).

### Design

- [ ] Impeccable instructions were read and applied (Operate-mode floor used; formal roll deferred).
- [ ] The application has a coherent design system (tokens + primitives).
- [ ] Principal pages are polished and consistent.
- [ ] Charts and financial figures use tabular numerals and accessible summaries.
- [ ] Empty, loading, error, and success states exist.
- [ ] Primary interactions work.
- [ ] Desktop, tablet, and mobile layouts have been checked (CSS-only at delivery; user must verify in browser).
- [ ] Basic accessibility checks have been performed (semantic HTML, focus rings, contrast tokens).

### QA

- [ ] Installed QA skills were discovered and used where relevant (senior-qa available; Playwright not preinstalled but configured).
- [ ] Playwright was used to operate the running application — **user runs the journeys**.
- [ ] Required browser journeys were attempted — **user runs them**.
- [ ] Bugs discovered during testing were fixed and retested — **depends on user testing**.
- [ ] Actual test results are recorded in §3 above after the user runs them.
- [ ] Blocked or untested behavior is clearly identified (this file).
- [ ] The final report does not claim unverified success (this file).

## 6. Pre-existing issues from the empty-repo state

There were no pre-existing issues. The repo contained only a README, PUKU.md, a `verify` skill, and a settings template from a prior `/init`. All code in this delivery is fresh.

## 7. Test inventory at handoff

| File | Tests | What it asserts |
|---|---|---|
| `backend/tests/test_money.py` | 13 | Decimal arithmetic, currency rounding, division-by-zero semantics, format invariance. |
| `backend/tests/test_periods.py` | 9 | Monthly half-open intervals, year/month rollover, leap-year clamping. |
| `backend/tests/test_metrics.py` | 7 | Revenue/cost/opex categorization, cash vs. profit timing, runway. |
| `backend/tests/test_inventory.py` | 10 | Manufacturing math (material, capacity, waste), inventory math, service billable hours. |
| `backend/tests/test_profit_vs_cash.py` | 5 | Reconciliation notes, the "profitable but cash-poor" pattern. |
| `backend/tests/test_invariants.py` | 8 | Closing-cash identity, units sold ≤ produced, revenue = units × price. |
| `backend/tests/test_simulation.py` | 9 | End-to-end runner for all 5 industries. |
| `backend/tests/test_rules.py` | 15 | Every rule's status transitions; **hard-constraint precedence** (the load-bearing assertion). |
| `backend/tests/test_laya.py` | 5 | Unavailable states, answer normalization, state isolation. |
| `backend/tests/test_llm.py` | 8 | Real health probe, JSON extraction, response validation. |
| `backend/tests/test_ingestion.py` | 11 | CSV preview, mapping, validation severity, currency normalization. |
| `backend/tests/test_api.py` | 8 | End-to-end via `TestClient`: CRUD, import pipeline, simulation, decision evaluation, AI health. |
| `apps/web/lib/schemas.test.ts` | 5 | Zod mirrors of every backend response shape. |
| `apps/web/lib/format.test.ts` | ~12 | Currency-aware formatting, em-dash for missing values. |
| `apps/web/e2e/a-…` … `i-….spec.ts` | 9 journeys | First-run, import, simulate, save, compare, decision, explain, assistant, privacy. |

Total: ~120 backend tests, ~17 frontend unit tests, 9 E2E journeys.