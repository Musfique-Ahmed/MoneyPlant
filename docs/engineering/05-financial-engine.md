# Chapter 05 — Financial Engine

> *The pure-Decimal core. Where every number on the dashboard is computed.*

This chapter is the math chapter. If you only have time to read one file in `app/services/finance/`,
read `money.py` (190 lines, the entire `Decimal` discipline in one place). The rest is
applied arithmetic on top of those primitives.

---

## 5.1 The six things the engine knows how to do

```
  ┌─────────────────────────────────────────────────────────────────┐
  │  L1: PURE DECIMAL ENGINE  (no I/O, no globals, no LLM)          │
  │                                                                 │
  │  1. money.py          ─ Decimal primitives + currency quantise │
  │  2. periods.py        ─ MonthlyPeriod + calendar arithmetic    │
  │  3. metrics.py        ─ compute_metrics + FinancialMetrics      │
  │  4. inventory.py      ─ manufacturing / inventory / service    │
  │  5. invariants.py     ─ assert_invariants(...)                 │
  │  6. profit_vs_cash.py ─ reconcile_profit_and_cash              │
  └─────────────────────────────────────────────────────────────────┘
                           │ inputs
                           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  L2: ORCHESTRATORS                                             │
  │  ─ simulation/runner.py   run_scenario(inputs)                  │
  │  ─ simulation/sensitivity  run_sensitivity(...)                  │
  │  ─ engine/alerts.py        evaluate_alerts(...)                  │
  │  ─ engine/financing.py     evaluate_financing_options(...)       │
  │  ─ insights/engine.py      build_dashboard_insights(...)         │
  └─────────────────────────────────────────────────────────────────┘
                           │ view-models
                           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  L4: UI  (chapter 12)                                           │
  │  Pre-formatted strings. No arithmetic.                          │
  └─────────────────────────────────────────────────────────────────┘
```

Every L1 function takes `Decimal` arguments (or `Transaction` / `*Inputs` dataclasses)
and returns `Decimal` (or dataclass of Decimals). The interfaces are sealed: there is no
way to pass a `float` through them.

---

## 5.2 `money.py` — the Decimal discipline

### Precision table

```python
PRECISION: dict[str, int] = {
    "USD": 2, "EUR": 2, "GBP": 2, "INR": 2, "CAD": 2, "AUD": 2,
    "JPY": 0,
}
```

> **Why these seven?** They cover the currencies of the seeded demo businesses
> (`scripts/seed_demo.py`). Adding a currency is a one-line addition; no other change.

### The five invariants the file enforces

```
  1. Floats become Decimals via str().
       to_decimal(0.1)        == "0.1" (Decimal("0.1"), not 0.100000…4)
  2. Every arithmetic result is quantised to currency precision.
       quantize(Decimal("1.235"), "USD")  == Decimal("1.24")   ROUND_HALF_UP
  3. Division by zero is ZERO, never an exception.
       div(Decimal(1), Decimal(0))  == ZERO
  4. safe_div_str returns None on divide-by-zero, with optional places override.
       safe_div_str(a, b, currency="USD", places=4)  # for ratios like margins
  5. parse_money_str rejects ambiguous input with a ValueError, not a silent 0.
       parse_money_str("$1,200.50")  == Decimal("1200.50")
       parse_money_str("garbage")   raises
```

The actual API:

```python
ZERO: Decimal = Decimal("0")

def to_decimal(value: float | int | str | Decimal) -> Decimal
def quantize(value: Decimal, currency: str) -> Decimal
def add(a: Decimal, b: Decimal, currency: str) -> Decimal
def sub(a: Decimal, b: Decimal, currency: str) -> Decimal
def mul(a: Decimal, b: Decimal, currency: str) -> Decimal
def div(a: Decimal, b: Decimal, currency: str) -> Decimal  # zero → ZERO
def safe_div_str(num: Decimal, den: Decimal, currency: str, places: int | None = None) -> str | None
def format_money(value: Decimal | None, currency: str) -> str
def parse_money_str(value: str, currency: str) -> Decimal
def same_currency(value: Decimal, currency: str) -> None  # raises CurrencyMismatch
```

`add/sub/mul` always go through `quantize` first, which means you cannot accidentally
drum up an un-banked trailing digit through arithmetic. This is the entire reason
`formatMoney()` in the UI just trusts the input.

---

## 5.3 `periods.py` — calendar arithmetic, the right way

`MonthlyPeriod` represents `[YYYY-MM-01, YYYY-MM-01_next)` inclusive. Date math with
month-boundary correctness is a notorious source of off-by-one bugs; this module stops
that.

```python
MonthlyPeriod.from_year_month(2026, 2).previous()       # → (2026, 1)
MonthlyPeriod.from_year_month(2026, 1).next()           # → (2026, 2)
MonthlyPeriod.containing(date(2026, 2, 14)).label()     # → "2026-02"
shift_months(date(2026, 1, 31), 1)                      # → 2026-02-28 (not 03-03!)
months_between(date(2026, 1, 1), date(2026, 7, 1))      # → 6
```

`_add_month` (line 48) handles Feb-29 to Feb-28, end-of-month → end-of-next-month, and
all the edge cases a `_add_month` template usually gets wrong.

### Why this matters

The cash-projection code uses `shift_months(supplier_delay_days, 30 * multiplier)`
for sensitivity analysis. Getting 30-day month arithmetic subtly wrong is exactly the
kind of bug that produces a one-day-off revenue date and a one-day-off customer
payment — and those get amplified across a 12-month projection. This module is the
single source of truth for that arithmetic.

---

## 5.4 `metrics.py` — the heart of the historical view

### The `Transaction` dataclass (line 28)

```python
@dataclass(frozen=True)
class Transaction:
    tx_date: date
    cash_flow_date: date | None       # when cash actually moved
    amount: Decimal                   # always positive
    currency: str
    direction: Literal["inflow", "outflow"]
    category: str
    payment_status: str | None = None
```

Note `amount` is always positive; direction encodes the sign. Categories are classified
by membership in three closed sets:

```
   REVENUE_CATEGORIES       (line 45)
   DIRECT_COST_CATEGORIES   (line 48)
   OPEX_CATEGORIES          (line 51)

   e.g.  "sales"            → REVENUE
         "cogs"             → DIRECT_COST
         "rent"             → OPEX
         "uncategorised"    → not in any set  → counts toward neither
                              (deliberately, so missing data surfaces)
```

### The financial summary (`compute_metrics`, line 97)

Signature:

```python
def compute_metrics(
    transactions: list[Transaction],
    opening_cash: Decimal,
    currency: str,
    period_start: date,
    period_end_exclusive: date,
) -> FinancialMetrics:
```

It returns a single `FinancialMetrics` containing:

| Field | Method | What it is |
|---|---|---|
| `revenue` | — | Σ revenue rows in window |
| `cogs` | — | Σ direct-cost rows in window |
| `opex` | — | Σ opex rows in window |
| `gross_profit` | — | `revenue − cogs` |
| `operating_profit` | — | `revenue − cogs − opex` |
| `contribution_margin` | `gross_margin()` | `(revenue − cogs) / revenue` (4dp) |
| `operating_margin` | `operating_margin()` | `operating_profit / revenue` (4dp) |
| `cash_runway_months` | `cash_runway_months(monthly_outflow=None)` | `opening_cash + cumulative_net_cash` ... |
| `cash_inflection_month` | — | First month where cumulative cash ≤ 0; `None` if it never happens |

**Currency guard:** if `any(t.currency != currency for t in transactions)`, the call
raises `CurrencyMismatch`. This is the one boundary a developer is most likely to
forget; it is loud by design.

**Empty input** returns a `FinancialMetrics` with `is_empty=True` and an empty
`warnings` list — never a `ZeroDivisionError`, never a `None` slip-through.

### Why all the methods return `str | None`

`gross_margin()` returns `None` if revenue is zero (a `0/0` boundary), otherwise a
string formatted to 4dp like `"0.1234"`. The reason is downstream: the dashboard
view-model in `insights/engine.py` looks for `None` to render `—` or omit the KPI
without conditional code at every layer.

---

## 5.5 `inventory.py` — three industry runners

Each runner takes a typed `*Inputs` dataclass and returns a `*Result` with a
precomputed cash schedule and a list of `warnings`. **All three return Pre-Quantised
Decimals** — the caller may add them, but cannot subdivide them, without going through
`quantize`.

### Manufacturing (`run_manufacturing`, line 63)

```
feasible_production = min(
    planned_production,
    production_capacity,
    floor(available_material / (material_per_unit × (1 + waste_pct)))
)

cogs_per_unit = (material_per_unit × raw_material_cost) + labor_per_unit + other_per_unit
cogs_at_full = cogs_per_unit × units_sold   (capped at feasible_production)

cash schedule:
   supplier_paid at   min(supplier_delay_days, horizon-1)
   customer_paid at  min(customer_delay_days, horizon-1)
```

The "feasible production" line is critical: it binds production to *material*,
*capacity*, and *plan*. A scenario that asks for more than any of them flattens
to the binding constraint with a `warning` recorded.

### Inventory-based (`run_inventory`, line 258)

The retail/wholesale/food runner. Same shape as manufacturing but
`raw_material_*` is replaced with `purchases` and `shrinkage_pct` adjusts
units available:

```
    units_available = units_purchased × (1 − shrinkage_pct)
    units_sold     = min(demand, units_available)
    cogs           = units_sold × cost_per_unit
    ending_inventory= (units_purchased − units_sold) × cost_per_unit
```

### Service (`run_service`, line 356)

```
revenue = max(billable_hours × hourly_rate, project_revenue)

expenses (all paid at period 0):
   labor         = hours × rate × (1 + benefits_load_pct)
   contractors   = contractor_spend
   overhead      = software + other_recurring
```

There is no inventory dimension here; the runner's job is mostly to project cash
timing.

### Common contract

Every `*Result` provides:

| Field | What it is |
|---|---|
| `cash_inflows: list[Decimal]` | length == horizon, indexed by month offset 0..N-1 |
| `cash_outflows: list[Decimal]` | same |
| `closing_cash_by_month: list[Decimal]` | running balance |
| `revenue: Decimal` | sum for the period |
| `operating_profit: Decimal` | revenue − cogs − opex (where applicable) |
| `warnings: list[str]` | human-readable binding constraints (e.g. `"Capacity exceeded: asked 150, capacity 120"`) |
| `invariants_ok: bool` | result of `assert_invariants(...)` |
| `invariants_failures: list[str]` | per-invariant failure description |

---

## 5.6 `invariants.py` — the assertion backbone

`assert_invariants(...)` is called at the *end* of every runner (see
`inventory.py:121`, `:193`, `:251`). It returns a list of `InvariantCheck` records,
never raises.

The five invariants:

```
  mandatory:
    closing_cash_equals_opening_plus_net_cash
       expected = opening + inflows − outflows   (quantised)
       passed   = expected == closing_cash

  optional (kw-only):
    units_sold_le_units_produced
       passed = units_sold ≤ units_produced
    material_used_le_available
       passed = material_used ≤ available_material
    feasible_production_le_capacity
       passed = feasible ≤ capacity
    revenue_equals_units_sold_times_price
       expected = units_sold × selling_price
       passed   = expected == revenue
```

Optional invariants are activated by passing the relevant keyword arguments. Each
runner knows which ones apply and passes them. **A scenario with a broken invariant
is never labelled `proceed`** — the `MISSING_CRITICAL_DATA` rule
(`engine.py:376`) and the dashboard `INVARIANTS` panel surface the failure
explicitly.

Why this matters: invariants are the safety net for arithmetic bugs in the engine. If
someone refactors `run_manufacturing` and accidentally allows `units_sold > units_produced`,
the test suite catches it; if the test suite somehow doesn't, the `PROCEED` verdict is
structurally prevented from appearing in the UI.

---

## 5.7 `profit_vs_cash.py` — the reconciliation

This is the function that powers the "Profitable but cash-poor" alert
(`engine/alerts.py:284`).

```python
class ProfitCashReconciliation:
    operating_profit: Decimal   # over period
    net_cash_movement: Decimal
    delta: Decimal              # profit − cash
    drivers: dict[str, Decimal] # e.g. {"receivables_change": -3000,
                                #       "inventory_change": -1200,
                                #       "payables_change": +500}

def reconcile_profit_and_cash(
    transactions: list[Transaction],
    opening_cash: Decimal,
    currency: str,
    period_start: date,
    period_end_exclusive: date,
) -> ProfitCashReconciliation
```

It decomposes the gap between reported profit and movement of cash into three driver
buckets:

| Driver | What it represents | Example |
|---|---|---|
| `receivables_change` | Unbilled / unpaid customer revenue | Invoice issued on day 1, paid on day 30 |
| `inventory_change` | Cash tied up in unsold units | Made 100, sold 60 → 40 in storage |
| `payables_change` | Bills received but not paid yet | Vendor invoice due in 30 days |

The reconciliation is *descriptive*, not a numeric claim: `drivers` are populated
opportunistically from the transaction stream (invoices, payments, supplier bills). The
UI renders the gap as "₹X made on paper, ₹Y in the bank" with the drivers broken out —
not as a forecast.

---

## 5.8 What's in `engine/` (the view-model builders)

```
   engine/alerts.py
   ─ evaluate_alerts(points, runway_months, operating_profit, currency, config=None)
     → list[Alert]
        ↓ sees chapter 06 for the rule table
   engine/financing.py
   ─ evaluate_financing_options(business, runway_months, monthly_outflow, funding_need, catalog)
     → FinancingOptionsResponse
        ↓ annuity in Decimal, DSCR ranking, see §5.9 below
```

### 5.9 Financing

A synthetic catalog (`backend/app/engine/financing.py`) of illustrative lender products
plus engine metrics produces a ranked list of financing matches:

```
   Hard rules (always first):
     funding_need = 0             → no_financing_needed sentinel
     fails eligibility            → not_recommended
     DSCR < min_dscr (default 1.2) → not_recommended

   Ranking within "possible" or "recommended":
     1. highest DSCR
     2. closest mid-point of amount range to funding_need

   Math:
     monthly_payment = (P × r × (1+r)^n) / ((1+r)^n − 1)
                        where r = apr_monthly, n = term_months
     DSCR           = operating_profit / (monthly_payment × 12)
```

The catalog *is not a real product* — it ships with placeholder products and a banner in
the UI reads *"Illustrative products. Not a credit decision. SYNTHETIC catalog — not real
lender offers."* (`apps/web/components/FinancingPanel.tsx:29`).

---

## 5.10 The simulation runners

### `simulation/runner.py:73 run_scenario`

```python
def run_scenario(inputs: dict, currency: str) -> ScenarioResult:
    industry = inputs["industry"]
    if industry in {"manufacturing"}:
        return run_manufacturing(ManufacturingInputs.from_dict(inputs))
    elif industry in {"service"}:
        return run_service(ServiceInputs.from_dict(inputs))
    else:  # retail / wholesale / food
        return run_inventory(InventoryInputs.from_dict(inputs))
```

Dispatches on `industry`. Each branch calls the corresponding `run_*` from
`finance/inventory.py` and wraps the result in a `ScenarioResult` with the dispatch-
specific `Inv-` fields flattened.

`ScenarioResult` carries `engine_version = "0.1.0"` (`runner.py:48`) so cached
results can be invalidated when the engine changes.

### `simulation/sensitivity.py:77 run_sensitivity`

```
   default multipliers:  -0.25, -0.10, 0, +0.10, +0.25
   default axes:         SALES_VOLUME, SELLING_PRICE, OPEX (varies by industry)
   optional:             COLLECTION_DELAY (shifts customer_delay by 30×multiplier, ≥0)

   for each (axis, multiplier):
       inputs = _shift(inputs, axis, multiplier)
       rerun run_scenario(inputs)
       collect SensitivitySlice(axis, multiplier, …kpis…)
```

The `_shift` function (`sensitivity.py:27`) operates on Decimal; `_delay_shift`
(`sensitivity.py:70`) is a special case that clamps delay to ≥0.

The Sensitivity chart in the UI renders the resulting one-axis-at-a-time ellipses — the
fan-shaped curves show "if volume ±25%, what does operating profit become?".

---

## 5.11 The view-model builders in `insights/engine.py`

This module sits *just above* L1 and *just below* the API edge. It takes domain shapes
and produces the `Visual[]` array the dashboard consumes.

```
   DashboardInputs:
       business, transactions, monthly_aggregate,
       category_totals, sensitivity, financing_match, alerts,
       scenarios
       │
       ▼
   Visual[] = [
     kpi_visual                # headline KPIs
     revenue_costs_profit_visual
     cash_balance_visual
     profit_vs_cash_gap_visual
     cost_breakdown_visual
     scenario_compare_visual
     sensitivity_visual
     alerts_summary_visual
     financing_summary_visual
   ]
       │
       ▼
   build_dashboard_insights(inputs)  → DashboardInsightsResponse
```

Every `Visual` is shaped like:

```python
@dataclass(frozen=True)
class Visual:
    visual_id: str           # stable id used by dashboard to map → chart
    title: str               # short
    what_it_shows: str       # plain-English prose (1 sentence)
    what_to_notice: str      # 1–2 sentences, the "where the inflection is"
    why_it_matters: str      # 1 sentence, action implication
    evidence: dict           # the data the chart binds to
```

Crucially: **the explanations are server-side strings** in the response. They are *not*
UI copy; they are *content*. The dashboard reads them with the React `node` prop on a
small text block and never has to invent or summarise anything. This is also how the
LLM explain endpoint knows what to anchor its summary to — see chapter 07.

---

## 5.12 Invariants — the safety net

For every scenario, the engine checks:

```
   opening_cash + Σ inflows − Σ outflows == closing_cash_at_each_month
   units_sold ≤ units_produced                  (manufacturing / inventory)
   material_used ≤ available_material          (manufacturing)
   feasible_production ≤ production_capacity    (manufacturing)
   revenue == units_sold × selling_price       (manufacturing / inventory)
```

The scenario result carries `invariants_ok` boolean and `invariants_failures` per-check
list. A scenario with broken invariants:

1. Has `invariants_ok: false` on the result
2. Triggers `MISSING_CRITICAL_DATA` rule (`engine.py:376`)
3. Shows up in the dashboard `INVARIANTS` panel with the per-check detail
4. Is structurally prevented from being labelled `proceed`

This is the final defence against an arithmetic bug in the engine that test coverage
didn't catch. The contract is enforced by `InvariantCheck.passed == False`.

---

## 5.13 Why every shape is a dataclass

Pure dataclasses with frozen semantics, mandatory fields, no dynamic attributes. The
reasons:

1. **Testability** — comparing `ManufacturingResult` instances works without
   `__eq__` boilerplate.
2. **Pydantic parity** — the Pydantic mirror in `app/schemas/finance.py` reproduces
   the same shapes for the wire.
3. **Compile-time enumerability** — editors autocomplete every field; reviewers can
   spot a new field at the type level.

The downside (verbosity at the call site) is real but accepted.

---

## 5.14 Where this stops being a pure function

`Simulation/runner.py:48 ENGINE_VERSION` is a module-level constant. That is the only
non-input state the engine carries. It exists so a cached `ScenarioResult` can know
which engine version produced it and be invalidated on upgrade.

Anything you write that needs `request`, `db`, `settings` — even indirectly — does not
belong in L1. If it crosses your mind to add `os.environ[...]` to `compute_metrics`,
that is the boundary and you have crossed it.

---

## 5.15 Extending this

| Adding | Files to touch |
|---|---|
| A new metric (e.g. `days_sales_outstanding`) | `app/services/finance/metrics.py` `FinancialMetrics` + `compute_metrics`; mirror in `app/schemas/finance.py`; UI consumer in `app/insights/engine.py` `kpi_visual` |
| A new industry (e.g. SaaS) | New `run_saas(SaasInputs)` in `inventory.py`; new `IndustryAdapter` under `services/industry_adapters/`; dispatch branch in `simulation/runner.py`; canonical fields in `services/ingestion/csv.py` (`CANONICAL_FIELDS` + `suggest_mapping`) |
| A new invariant (e.g. cogs sanity vs. revenue) | New `if` block in `assert_invariants`; new string returned in `InvariantCheck.detail` |
| A new currency | Add to `PRECISION`; add to `apps/web/lib/format.ts` `JPY`-style block |
| A new view-model visual | New `*_visual()` function in `app/insights/engine.py`; add to `build_dashboard_insights`; add a chart component in `apps/web/components/dashboard/`; map `visual_id` in `apps/web/app/(app)/dashboard/page.tsx` |

What you should *not* do:
- Add a service function that imports `fastapi`, `sqlalchemy`, or `httpx`.
- Compute money with `float`.
- Add an LLM call inside the engine layer.
- Persist results synchronously during `compute_metrics` (the engine returns values
  to L2; persistence is the orchestrator's job).

---

*Next: [Chapter 06 — Rule engine & decision aggregation](06-rules-and-decisions.md)*