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
| Data-source sync backend (DataSource + SyncRun models, Alembic 0002/0003, connectors, sync service) | ✅ verified 2026-10-20 | `pytest` (full) **207 passed, 1 skipped** — 13 new in `tests/test_sync.py`, 12 in `tests/test_sync_scheduler.py`, 6 in `tests/test_sync_cli.py`. The skip is `test_symlink_escape_is_rejected`, which needs Windows Developer Mode; the path-traversal siblings all pass. `alembic upgrade head` applied cleanly on a fresh DB and is idempotent on re-run. |
| Data-source automation (daemon-thread scheduler, `scripts/sync_sources.py` CLI, `scripts/simulate_daily_data.py`) | ✅ verified 2026-10-20 | 12 scheduler tests + 6 CLI tests pass. `sync_sources.py --help` and `--list` run; `simulate_daily_data.py` created `sample_data/ext_invoices.db` and `sample_data/daily_transactions.xlsx`. The scheduler thread itself was exercised via `run_due_sources` in tests, not via a long-running process. |
| Data-sources frontend (`/data` page, dashboard freshness strip, Zod mirrors) | ✅ verified 2026-10-20 | `npm run typecheck` clean. `npm run lint` clean (`No ESLint warnings or errors`). `npm run test` **42/42 pass** — 18 new Zod cases for `DataSource` / `DataSourceTestResult` / `SyncRun` / `SyncRunList` / `Freshness`. |
| Playwright journey K (connect → sync → freshness) | 🟡 Implemented, unverified | `apps/web/e2e/k-data-sources.spec.ts` written but **not executed** — Playwright needs a running backend on `:8000` and the web server on `:3000`. Run with `npm run test:e2e`. |
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

## 4a. What the tests cover

Every claim of "verified" above is supported by an actual test whose name and (where it's not obvious) the property it asserts. Failures roll back the verification.

| Area | Tests | Notable assertions |
|---|---|---|
| Money arithmetic | `test_money.py` | Decimal precision, format stability, division-by-zero returns `None`. |
| Periods | `test_periods.py` | Half-open intervals, month shifts, `months_between` direction. |
| Metrics | `test_metrics.py` | Direct-cost vs opex classification, gross profit, runway. |
| Invariants | `test_invariants.py` | Cash ↔ profit gap classification. |
| Simulation | `test_simulation.py` | Cap-ex timing, depreciation-free modelling, sensitivity determinism. |
| Rules | `test_rules.py` | Hard-vs-soft precedence, `aggregate_status` order. |
| Ingestion | `test_ingestion.py` | Column-mapping round-trips, multi-date parsing, header normalisation. |
| API | `test_api.py` | Health, config endpoint, business CRUD, import commit, scenarios, decisions. |
| LLM & Laya | `test_llm.py`, `test_laya.py` | Schema-validated response; missing provider reports `unavailable`, never silently green. |
| Cash-flow alerts | `test_alerts.py` (23) | All five alert codes; boundary conditions (negative cash, runway <1 month; <3 months); sort by severity. |
| Financing options | `test_financing.py` (18) | Hand-calculated annuity; DSCR boundary 1.2/1.5; ineligible product routing; ranking; Decimal precision. |
| Dashboard insights | `test_insights.py` (36) | Pure-function output; every quoted figure in the interpretation block is verifiable in the matching evidence dict; malformed sources yield edge-case visuals, never fabricated values. |
| Sync service | `test_sync.py` (13) | Idempotent re-sync; appended rows only; replaced file; invalid rows quarantined; SQL on SQLite with watermark; **path-traversal rejected, symlink escapes rejected**; secrets never returned by API or logged; **failed sync leaves data intact**; recomputation reflects new rows (alerts endpoint sees them); **full API round-trip** (create → test → sync → re-sync → runs → freshness) with `rows_read`/`rows_added`/`rows_skipped_duplicate` asserted and no `secret_ref` anywhere in any response. |
| Sync scheduler | `test_sync_scheduler.py` (12) | Deterministic `is_due` predicate across schedules; manual sources never run automatically; naive timestamps treated as UTC. |
| Sync CLI | `test_sync_cli.py` (6) | Usage errors return code 2; `--list` prints names but never `secret_ref`; unknown id is rejected; `--all` with nothing due is a no-op. |
| Frontend Zod mirrors | `apps/web/lib/schemas.test.ts` (34) | Server-acceptance drift fails loudly; `secret_ref` never appears in a parsed payload; alert / financing / insights / sync schemas round-trip happy and reject bad payloads. |
| End-to-end | `apps/web/e2e/{a–j}.spec.ts` | CRU(S) the business, import a CSV, run a simulation, save it, compare two, evaluate a decision, ask for an LLM explanation, verify privacy/error states, verify the dashboard renders. |
| End-to-end (sync) | `apps/web/e2e/k-data-sources.spec.ts` | Add a file source, click Sync now, see OK + freshness strip update. **Not run in this session**; needs a running backend + browser. |

## 4. Known limitations and honest disclosures

1. **No formal Impeccable `concept-seed.mjs` roll was performed.** The visual world ("Disciplined Ledger") is selected by the implementer using the Operate-mode craft floor, documented in `docs/DESIGN_DECISIONS.md`. To run the formal Impeccable flow, open a session where bash works and run `node .claude/skills/impeccable/scripts/concept-seed.mjs --scope surface --mode operate`.
2. **No authentication in MVP.** Single-tenant; do not expose on the public internet without adding auth.
3. **No statistical forecasting.** Sensitivity is deterministic one-at-a-time, clearly labelled.
4. **No multi-currency conversion.** Mixed-currency imports are quarantined.
5. **Depreciation, taxes, FX, and full loan amortization are out of scope.** Documented in FINANCIAL_MODEL §11.
6. **Provider credentials are user-provided.** No real API keys shipped; the `.env.example` file has placeholders only.
7. **Laya model weights are user-downloaded** via `pip install laya` followed by the first `predict()` call (caches to `HF_HUB_CACHE`). Documented.
8. **No background jobs, no email, no notifications.**
9. **Data sources support CSV/XLSX and SQLite/Postgres only.** See README §"Connected data sources" for the security model (path traversal + symlink escape rejection; env-var credential pointers only). There is no cloud-object-store or OAuth-secured HTTP connector yet.
10. **Two transactions that are byte-identical across all canonical fields are treated as duplicates** (deliberate — see `uq_transactions_business_source_row_hash`). Edit a description by even one character to import a "real" new copy.

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