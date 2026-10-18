# Financial Model — MoneyPlant

This document defines every formula the engine computes, the sign conventions, the rounding rules, the data prerequisites, and the deliberate gaps. The code lives in `backend/app/services/finance/`. Tests in `backend/tests/test_*.py` assert exact numeric outputs.

## 1. Money and rounding

- **Type:** `decimal.Decimal` everywhere in the engine.
- **Rounding:** `ROUND_HALF_UP` by default. Currency-aware precision: 2 decimal places for `USD`, `EUR`, `GBP`; 0 for `JPY`; extensible.
- **Currency mixing:** A scenario's `currency` is set at the top. Inputs in other currencies are rejected unless an explicit conversion is provided; the engine does **not** silently FX-convert. The frontend displays the warning.
- **Display:** the frontend formats numbers using `Intl.NumberFormat(locale, { style: 'currency', currency })`. Tabular numerals via CSS.

## 2. Periods

- **Period type:** monthly by default. The engine supports daily or weekly periods but the UI exposes monthly.
- **Period bounds:** half-open `[start, end)` where `start` is the first instant of the period and `end` is the first instant of the next period. Cash flows on `end` belong to the next period.
- **Opening roll-forward:** `opening_t = closing_{t-1}`.

## 3. Core metrics

Given a set of in-period transactions:

| Metric | Definition | Sign |
|---|---|---|
| Total revenue | Σ amounts where `direction = inflow` and category is revenue-like | + |
| Direct costs | Σ amounts where `direction = outflow` and category is direct-cost-like (materials, freight, supplier payments tied to sales) | + |
| Gross profit | `revenue − direct_costs` | + |
| Gross margin | `gross_profit / revenue` if `revenue > 0`, else undefined (UI shows "—") | ratio |
| Operating expenses | Σ amounts where `direction = outflow` and category is operating-expense-like (rent, salaries, utilities, marketing) | + |
| Operating profit | `gross_profit − operating_expenses` | + |
| Net profit | `operating_profit + other_income − other_expenses` (only when those categories exist in the dataset) | + |
| Operating margin | `operating_profit / revenue` if `revenue > 0`, else undefined | ratio |
| Cash inflows | Σ amounts where `cash_flow_date ∈ period` and `direction = inflow` | + |
| Cash outflows | Σ amounts where `cash_flow_date ∈ period` and `direction = outflow` | + |
| Net cash movement | `inflows − outflows` | + |
| Closing cash | `opening + net_cash_movement` | + |
| Minimum projected cash | `min(closing_t)` over the projection horizon | + |
| Cash runway (months) | `closing_cash / avg_monthly_outflow` if `avg_monthly_outflow > 0`, else undefined | ratio |

**Important:** profit and cash are distinct. A sale on credit increases revenue before cash arrives; a supplier purchase decreases cash before inventory is consumed.

## 4. Profit vs cash adjustments

| Event | Profit impact | Cash impact |
|---|---|---|
| Credit sale (payment_status = pending) | Revenue recognized at sale date | Cash inflow at `cash_flow_date` |
| Supplier purchase (inventory) | Not expense until consumed (manufacturing); see §5 | Cash outflow at `cash_flow_date` |
| Material consumption | Recognized at production; cost = `material_used * unit_cost` | Already paid (supplier cash) |
| Unsold finished goods | Carried in inventory, not counted as sold | Already paid (material + labor cash) |
| Loan principal repayment | Not an expense | Cash outflow |
| Loan interest | Expense | Cash outflow |
| Depreciation | Not modelled in MVP | n/a |
| Taxes | Not modelled in MVP | n/a |

If the dataset cannot support an accrual adjustment (e.g., no `payment_status`), the engine falls back to cash-basis for the affected metric and surfaces a `data_quality_warning`.

## 5. Inventory and production (manufacturing)

Inputs:
- `material_unit_cost` (Money per unit of material)
- `material_per_unit` (units of material per finished unit)
- `material_waste_pct` (0.0 to 0.5 typical)
- `opening_raw_material_qty`
- `planned_raw_material_purchase_qty`
- `planned_production_qty`
- `production_capacity_qty` (max per period)
- `labor_cost_per_unit` (Money per finished unit)
- `other_variable_cost_per_unit` (Money per finished unit)
- `selling_price` (Money per finished unit)
- `expected_units_sold`
- `customer_payment_delay_periods`
- `supplier_payment_delay_periods`
- `opening_cash`

Derived (in order):

1. `available_raw_material = opening_raw_material_qty + planned_raw_material_purchase_qty`
2. `material_required = planned_production_qty * material_per_unit * (1 + material_waste_pct)`
3. `material_shortage = max(0, material_required − available_raw_material)`
4. `feasible_production = min(planned_production_qty, production_capacity_qty, floor(available_raw_material / material_per_unit / (1 + material_waste_pct)))`
5. `material_used = feasible_production * material_per_unit * (1 + material_waste_pct)`
6. `material_unused = available_raw_material − material_used`
7. `units_produced = feasible_production`
8. `units_sold = min(expected_units_sold, units_produced)`
9. `units_unsold = units_produced − units_sold`
10. `revenue = units_sold * selling_price`
11. `cost_of_goods_sold = units_sold * (material_per_unit * (1 + material_waste_pct) * material_unit_cost + labor_cost_per_unit + other_variable_cost_per_unit)`
12. `unsold_inventory_value = units_unsold * (same unit cost as COGS)` (FIFO by default)
13. `gross_profit = revenue − cost_of_goods_sold`
14. `operating_profit = gross_profit − operating_expenses − labor_cost_for_unsold_production` (unsold production's labor is still incurred)
15. `cash_outflow_for_materials = planned_raw_material_purchase_qty * material_unit_cost` (paid at `cash_flow_date`)
16. `cash_inflow_from_sales = units_sold * selling_price` (received at sale_date + customer_payment_delay_periods)
17. `closing_cash = opening_cash + cash_inflow_from_sales − cash_outflow_for_materials − labor_cash − opex_cash`

**Invariants:**
- `material_used ≤ available_raw_material` always.
- `feasible_production ≤ production_capacity_qty` always.
- `units_sold ≤ units_produced`.
- `closing_cash` matches `opening + all_period_inflows − all_period_outflows` for the same period (single-period test in `test_invariants.py`).

## 6. Service-business formulas

Inputs:
- `billable_hours_capacity` (per period)
- `planned_billable_utilization_pct` (0–1)
- `hourly_price` (Money)
- `project_revenue` (optional flat-fee alternative)
- `labor_cost_per_hour` (Money)
- `contractor_cost` (Money, optional)
- `project_expenses` (Money, optional)
- `invoice_payment_delay_periods`
- `opening_cash`

Derived:
- `billable_hours = billable_hours_capacity * planned_billable_utilization_pct`
- `revenue = max(project_revenue, billable_hours * hourly_price)` — explicit choice if both are set
- `labor_cost = billable_hours * labor_cost_per_hour`
- `contribution_margin = revenue − labor_cost − contractor_cost − project_expenses`
- `cash_inflow = revenue` received at `invoice_date + invoice_payment_delay_periods`
- `closing_cash = opening + cash_inflow − labor_cash − contractor_cash − project_expense_cash`

## 7. Retail / wholesale formulas

Inputs:
- `opening_inventory_units`
- `planned_purchase_units`
- `purchase_unit_cost`
- `selling_price`
- `expected_units_sold`
- `shrinkage_pct` (0–0.2 typical)
- `supplier_payment_delay_periods`
- `customer_payment_delay_periods`
- `opening_cash`

Derived:
- `available_units = opening_inventory_units + planned_purchase_units * (1 − shrinkage_pct)` (shrinkage hits purchased units before they reach inventory)
- `units_sold = min(expected_units_sold, available_units)`
- `cogs = units_sold * purchase_unit_cost`
- `revenue = units_sold * selling_price`
- `closing_inventory_units = available_units − units_sold`
- `closing_inventory_value = closing_inventory_units * purchase_unit_cost`
- `cash_outflow_for_purchases = planned_purchase_units * purchase_unit_cost`
- `cash_inflow_from_sales = units_sold * selling_price` at customer delay

## 8. Food-service formulas

Same as retail with the addition of:
- `recipe_cost_per_serving` (MaterialPerServing × Cost + Labor per serving + Overhead allocation)
- `expected_covers` (customers per period)
- `food_cost_pct_target` (default 0.30)
- `food_cost_pct = recipe_cost_per_serving * expected_covers / revenue`

## 9. Sensitivity

One-at-a-time, around the user's baseline values, for: sales volume (±10%, ±25%), price (±10%), material cost (±10%, ±25%), labor cost (±10%), customer payment delay (0, +30, +60 days), supplier payment delay (−15, 0, +15 days), waste (±50% relative), opex (±10%).

Output per assumption: baseline value, stressed value, delta profit, delta closing cash, delta minimum cash. Labelled as "deterministic sensitivity — not a statistical forecast".

## 10. Decision rules

Each rule evaluates a computed metric and returns a `RuleEvaluation` with severity, status, threshold, actual value, unit, explanation, evidence, and corrective action.

| Rule ID | Severity | Status when violated |
|---|---|---|
| `NEGATIVE_CLOSING_CASH` | **hard** | `breached` |
| `MIN_CASH_RESERVE` | hard when threshold ≥ 0 | `breached` if `closing_cash < threshold` |
| `CAPACITY_EXCEEDED` | hard | `breached` if `feasible_production > production_capacity` |
| `MATERIAL_SHORTAGE` | hard when shortage > 0 | `breached` |
| `MIN_PROFIT_MARGIN` | soft | `warning` if `operating_margin < target` |
| `NEGATIVE_CONTRIBUTION_MARGIN` | soft | `warning` if contribution < 0 |
| `UNSOLD_INVENTORY_EXPOSURE` | soft | `warning` if `unsold_inventory_value / revenue > threshold` |
| `MISSING_CRITICAL_DATA` | info | `not_evaluable` |

**Aggregation precedence:** any `breached` rule with severity `hard` forces overall status to `reject`. Soft `warning` rules downgrade `proceed` to `proceed_with_caution`. Missing data → `insufficient_data`.

## 11. Deliberate gaps (what is NOT modelled)

- **Depreciation.** No fixed-asset register. Capex is treated as a single-period expense unless explicitly categorized as inventory.
- **Tax.** Not modelled. Every tax line in a dataset is preserved as a `tax` category transaction but not rolled into a net-of-tax figure.
- **Multi-currency conversion.** A scenario has one currency. Mixed-currency imports are rejected or quarantined.
- **FX exposure.** Not modelled.
- **Inventory valuation methods.** FIFO only. LIFO and weighted-average are out of scope.
- **Statistical forecasting.** ARIMA, exponential smoothing, ML — not in MVP.
- **Loan amortization schedules.** Only principal and interest as separate categories.

These gaps are documented in the UI ("Data coverage: 6 of 9 categories present") and in every decision report.