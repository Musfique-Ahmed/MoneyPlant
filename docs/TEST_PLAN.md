# Test Plan — MoneyPlant

The product has four test layers. Each layer proves something the others cannot. All tests must assert real numeric outputs (no snapshots for financial calculations).

## 1. Backend unit tests — `backend/tests/`

### 1.1 `test_money.py`
- Currency-aware rounding (USD/EUR 2 dp; JPY 0 dp).
- Addition, subtraction, multiplication, division.
- Reject mixed-currency arithmetic.
- Decimal precision preserved through 10⁶.

### 1.2 `test_periods.py`
- Monthly period arithmetic.
- Opening roll-forward.
- Cash-flow date falls in the right period.

### 1.3 `test_metrics.py`
- Total revenue, direct costs, gross profit, gross margin.
- Operating profit.
- Net cash movement, opening/closing cash.
- Minimum projected cash.
- Cash runway.
- Zero revenue → "undefined" margin (not zero).
- Negative profit / negative cash.

### 1.4 `test_inventory.py`
- Material required with waste.
- Material shortage when `material_required > available`.
- Capacity-bounded production.
- Unsold inventory carrying value.
- Shrinkage (retail).

### 1.5 `test_profit_vs_cash.py`
- Credit sale: revenue at sale date, cash at cash_flow_date.
- Supplier purchase: cash out, no immediate expense.
- Unsold finished goods: cost recognized in inventory, not COGS.
- Loan principal: cash out, not expense.

### 1.6 `test_manufacturing_adapter.py`
- Full clothing scenario with realistic numbers; assert exact totals.
- Material shortage path.
- Capacity-exceeded path.
- 100% sold vs. partial sold vs. unsold.

### 1.7 `test_service_adapter.py`
- Billable hours * hourly price revenue.
- Flat project revenue override.
- Contribution margin.

### 1.8 `test_retail_adapter.py`
- Shrinkage applied.
- Inventory valuation.

### 1.9 `test_food_adapter.py` and `test_wholesale_adapter.py`
- Same shape as retail; one end-to-end case each.

### 1.10 `test_invariants.py`
- Closing cash equals opening + inflows − outflows (single period).
- Closing cash equals opening + Σ(inflows − outflows) (multi period).
- Production never exceeds capacity.
- Material used never exceeds available material.
- Units sold never exceed units produced.
- Revenue = units sold × selling price.
- Gross profit follows documented definition.
- Re-running same inputs produces identical results.

### 1.11 `test_rules_engine.py`
- Each rule returns the expected status for: pass, warning, breach, not_evaluable.
- Aggregation precedence: hard breach forces `reject`.
- Custom thresholds are honored.
- Missing data produces `not_evaluable`, not `passed`.

### 1.12 `test_laya_adapter.py`
- Mocked Laya `Router.predict` returns a canned answer → adapter normalizes correctly.
- Router import failure → `unavailable`.
- Empty / malformed answer → `unavailable`.
- Hard breach scenario: even with Laya saying "proceed", final status is `reject`.

### 1.13 `test_llm_providers.py`
- Mocked provider returns valid `Explanation` → returned as-is.
- Mocked provider returns invalid shape → `unavailable` with reason.
- Health check returns the right `ProviderStatus`.
- `OPENAI_API_KEY` is not echoed by `/api/ai/providers`.

### 1.14 `test_ingestion.py`
- Valid CSV parsed; row count matches.
- Missing required columns → per-row issues, no silent drop.
- Mixed-currency row → rejected with reason.
- Invalid date format → rejected with row number.
- XLSX with formula is read as the cached value, not evaluated.
- Oversized file → 413.
- Wrong extension → 415.

### 1.15 `test_api.py`
- `GET /api/health` → 200.
- `GET /api/config/public` → 200, no secrets.
- `POST /api/imports/preview` returns headers + preview rows.
- `POST /api/scenarios/simulate` returns deterministic result.
- `POST /api/scenarios/compare` returns diff with safe zero handling.
- `POST /api/decisions/evaluate` includes rule + Laya outputs.
- Provider errors return 503, not 500.

## 2. Backend integration tests — `backend/tests/integration/`

Use the FastAPI `TestClient` with a per-test SQLite database.

- Full import → financial summary flow.
- Full scenario save → rerun → compare flow.
- Decision evaluate → explain flow (mocked LLM).
- Cross-business isolation: a request for business A cannot read business B's data.
- Workspace switch.
- Empty workspace returns 200 with empty metrics and an empty-state flag.

## 3. Frontend tests — `apps/web/tests/`

Vitest + React Testing Library.

- Component renders for each primitive (Button, Input, Select, Table, Tabs, Dialog).
- Dashboard renders the empty state when API returns empty.
- Dashboard renders metrics when API returns data.
- Simulator form calls `/api/scenarios/simulate` on submit and shows the result.
- Column-mapping dropdown applies the user's choice to the preview.
- Comparison page handles zero-baseline percentage safely.
- Provider settings shows real health-check status.
- Error boundary catches API errors and shows a recoverable error.

## 4. End-to-end browser tests — `apps/web/e2e/`

Playwright. Each journey from prompt section 19.1 has its own spec.

| Journey | Spec file |
|---|---|
| A. First visit + dashboard | `e2e/journey-a-dashboard.spec.ts` |
| B. Data import | `e2e/journey-b-import.spec.ts` |
| C. Scenario simulation | `e2e/journey-c-simulation.spec.ts` |
| D. Scenario comparison | `e2e/journey-d-comparison.spec.ts` |
| E. Rule engine + Laya | `e2e/journey-e-decision.spec.ts` |
| F. LLM explanation | `e2e/journey-f-llm.spec.ts` |
| G. Decision report + assistant | `e2e/journey-g-report-assistant.spec.ts` |
| H. Persistence + recovery | `e2e/journey-h-persistence.spec.ts` |
| I. Responsive + a11y | `e2e/journey-i-responsive.spec.ts` |

Each spec uses accessible selectors (`getByRole`, `getByLabel`, `getByText`) — never derived coordinates. Each spec asserts the actual UI state, not the source code.

## 5. Bug-fix protocol

When a test fails:

1. Reproduce the failure by running the single failing test in isolation.
2. Classify: product bug, test bug, environment bug, or pre-existing.
3. If product bug, fix the code; if test bug, fix the test.
4. Rerun the failing test.
5. Rerun the related tests (regression sweep).
6. Update `IMPLEMENTATION_STATUS.md` with: the bug, the root cause, the fix, and the date.
7. Do **not** weaken an assertion to obtain a green suite.

## 6. What is intentionally not tested

- Laya model accuracy on arbitrary real-world data — only that the adapter normalizes its outputs correctly.
- External provider uptime — only that our adapter handles failures gracefully.
- The LLM's "quality" of explanation — only that the schema is valid.
- Visual regressions (no Percy / Chromatic) — manual visual review for now.