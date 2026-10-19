/**
 * Client-side Zod schemas that mirror the FastAPI response models.
 * If the server contract drifts, parsing fails loudly.
 */

import { z } from "zod";

export const Currency = z.enum(["USD", "EUR", "GBP", "JPY", "INR", "CAD", "AUD"]);

export const Industry = z.enum([
  "manufacturing",
  "retail",
  "wholesale",
  "service",
  "food",
]);

export const Business = z.object({
  id: z.string(),
  name: z.string(),
  industry: Industry,
  currency: Currency,
  fiscal_year_start_month: z.number().int().min(1).max(12),
  locale: z.string(),
  min_cash_reserve: z.string(),
  target_operating_margin: z.string(),
  max_unsold_inventory_exposure_pct: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const FinancialSummary = z.object({
  business_id: z.string(),
  currency: Currency,
  period_start: z.string(),
  period_end_exclusive: z.string(),
  revenue: z.string(),
  direct_costs: z.string(),
  gross_profit: z.string(),
  gross_margin: z.string().nullable(),
  operating_expenses: z.string(),
  operating_profit: z.string(),
  operating_margin: z.string().nullable(),
  cash_inflows: z.string(),
  cash_outflows: z.string(),
  net_cash_movement: z.string(),
  opening_cash: z.string(),
  closing_cash: z.string(),
  minimum_projected_cash: z.string(),
  cash_runway_months: z.string().nullable(),
  transaction_count: z.number().int(),
  data_coverage: z.record(z.boolean()).default({}),
  warnings: z.array(z.string()).default([]),
  is_empty: z.boolean().default(false),
});

export const Direction = z.enum(["inflow", "outflow"]);
export const PaymentStatus = z.enum(["paid", "pending", "partial"]).nullable();

export const Transaction = z.object({
  id: z.string(),
  business_id: z.string(),
  tx_date: z.string(),
  cash_flow_date: z.string().nullable(),
  description: z.string(),
  amount: z.string(),
  currency: Currency,
  direction: Direction,
  category: z.string(),
  payment_status: PaymentStatus,
  customer_or_supplier: z.string().nullable(),
  source_file: z.string().nullable(),
  source_sheet: z.string().nullable(),
  source_row: z.number().int().nullable(),
  import_job_id: z.string().nullable(),
  created_at: z.string(),
});

export const TransactionList = z.object({
  items: z.array(Transaction),
  total: z.number().int(),
});

export const ImportRow = z.object({
  row: z.number().int(),
  field: z.string(),
  severity: z.enum(["error", "warning"]),
  message: z.string(),
});

export const ImportPreview = z.object({
  filename: z.string(),
  file_extension: z.string(),
  file_size_bytes: z.number().int(),
  encoding: z.string(),
  sheet_name: z.string().nullable().optional(),
  headers: z.array(z.string()),
  sample_rows: z.array(z.record(z.string())),
  row_count: z.number().int(),
  suggested_mapping: z.record(z.string()),
  issues: z.array(ImportRow),
});

export const ImportJob = z.object({
  id: z.string(),
  business_id: z.string(),
  filename: z.string(),
  file_extension: z.string(),
  file_size_bytes: z.number().int(),
  encoding: z.string().nullable(),
  sheet_name: z.string().nullable(),
  column_mapping: z.record(z.string()),
  row_count_total: z.number().int(),
  row_count_imported: z.number().int(),
  row_count_rejected: z.number().int(),
  validation_issues: z.array(z.record(z.unknown())),
  status: z.string(),
  created_at: z.string(),
});

export const ScenarioResult = z.object({
  engine_version: z.string(),
  calculation_timestamp: z.string(),
  currency: Currency,
  revenue: z.string(),
  direct_costs: z.string(),
  gross_profit: z.string(),
  gross_margin: z.string().nullable(),
  operating_expenses: z.string(),
  operating_profit: z.string(),
  operating_margin: z.string().nullable(),
  cash_inflows: z.string(),
  cash_outflows: z.string(),
  net_cash_movement: z.string(),
  opening_cash: z.string(),
  closing_cash: z.string(),
  minimum_projected_cash: z.string(),
  cash_runway_months: z.string().nullable(),
  contribution_margin: z.string().nullable(),
  units_sold: z.string().nullable(),
  units_produced: z.string().nullable(),
  unsold_inventory_units: z.string().nullable(),
  unsold_inventory_value: z.string().nullable(),
  material_shortage: z.string().nullable(),
  feasible_production: z.string().nullable(),
  warnings: z.array(z.string()).default([]),
  invariants_ok: z.boolean().default(true),
  invariants_failures: z.array(z.string()).default([]),
});

export const Scenario = z.object({
  id: z.string(),
  business_id: z.string(),
  name: z.string(),
  industry: Industry,
  description: z.string(),
  status: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  latest_version_number: z.number().int().nullable(),
  latest_version_id: z.string().nullable(),
  latest_result: ScenarioResult.nullable(),
});

export const SimulateResponse = z.object({
  result: ScenarioResult,
  sensitivity: z.unknown().nullable().optional(),
});

export const RuleEvaluation = z.object({
  rule_id: z.string(),
  rule_version: z.string(),
  name: z.string(),
  severity: z.enum(["hard", "soft", "info"]),
  status: z.enum(["passed", "warning", "breached", "not_evaluable"]),
  actual_value: z.string().nullable(),
  threshold: z.string().nullable(),
  unit: z.string().nullable(),
  explanation: z.string(),
  related_metric: z.string(),
  evidence: z.record(z.unknown()).default({}),
  corrective_action: z.string().nullable(),
});

export const LayaAssessment = z.object({
  status: z.enum(["ok", "unavailable"]),
  reason: z.string().nullable(),
  question_id: z.string(),
  answer_label: z.string(),
  answer_score: z.number().nullable(),
  answer_probability: z.number().nullable(),
  model_id: z.string(),
  raw_response: z.record(z.unknown()).default({}),
});

export const DecisionReport = z.object({
  id: z.string(),
  business_id: z.string(),
  scenario_version_id: z.string().nullable(),
  question: z.string(),
  overall_status: z.enum(["proceed", "proceed_with_caution", "revise", "insufficient_data", "reject"]),
  laya_status: z.string(),
  rule_evaluations: z.array(RuleEvaluation),
  laya_assessments: z.array(LayaAssessment),
  binding_constraints: z.array(z.string()),
  key_risks: z.array(z.string()),
  recommendation: z.string(),
  missing_information: z.array(z.string()),
  assumptions: z.array(z.string()),
  caveats: z.array(z.string()),
  business_goal: z.string().nullable(),
  calculation_timestamp: z.string(),
});

export const ProviderHealth = z.object({
  mode: z.enum(["local", "openai", "anthropic"]),
  status: z.enum(["ok", "unavailable", "misconfigured"]),
  model: z.string(),
  detail: z.string().nullable(),
  latency_ms: z.number().nullable(),
  checked_at: z.string(),
});

export const Explanation = z.object({
  status: z.enum(["ok", "unavailable"]),
  reason: z.string().nullable(),
  provider: z.string(),
  model: z.string(),
  mode: z.enum(["local", "openai", "anthropic"]),
  summary: z.string().nullable(),
  recommendation: z.string().nullable(),
  supporting_evidence: z.array(z.string()),
  key_risks: z.array(z.string()),
  assumptions: z.array(z.string()),
  missing_information: z.array(z.string()),
  alternatives: z.array(z.string()),
  next_actions: z.array(z.string()),
  limitations: z.array(z.string()),
  raw: z.record(z.unknown()).default({}),
});

// ---------------------------------------------------------------------------
// Alerts (mirrors backend/app/schemas/alerts.py)
// ---------------------------------------------------------------------------

export const AlertConfig = z.object({
  low_buffer_months: z.string(),
  short_runway_warning_months: z.string(),
  short_runway_critical_months: z.string(),
  sharp_drop_pct: z.string(),
});

export const Alert = z.object({
  code: z.string(),
  severity: z.enum(["Critical", "Warning", "Info"]),
  month: z.number().int().nullable(),
  message: z.string(),
  evidence: z.record(z.unknown()).default({}),
});

export const MonthlyCashPoint = z.object({
  month_index: z.number().int(),
  opening_cash: z.string(),
  net_cash_movement: z.string(),
  closing_cash: z.string(),
});

export const AlertsResponse = z.object({
  business_id: z.string(),
  currency: Currency,
  horizon_months: z.number().int(),
  runway_months: z.string().nullable(),
  operating_profit: z.string(),
  monthly_cash: z.array(MonthlyCashPoint),
  config: AlertConfig,
  alerts: z.array(Alert),
  source: z.string(),
  note: z.string(),
});

// ---------------------------------------------------------------------------
// Financing (mirrors backend/app/schemas/financing.py)
// ---------------------------------------------------------------------------

export const FinancingCatalogEntry = z.object({
  id: z.string(),
  name: z.string(),
  type: z.string(),
  min_amount: z.string(),
  max_amount: z.string(),
  min_months_operating: z.number().int(),
  min_avg_monthly_revenue: z.string(),
  max_term_months: z.number().int(),
  indicative_annual_rate: z.string(),
  suitable_use_cases: z.array(z.string()),
  synthetic: z.boolean(),
});

export const FinancingCatalog = z.object({
  products: z.array(FinancingCatalogEntry),
  synthetic: z.boolean(),
  disclaimer: z.string(),
});

export const EligibilityCheck = z.object({
  name: z.string(),
  passed: z.boolean(),
  requirement: z.string(),
  actual: z.string(),
});

export const FinancingMatch = z.object({
  product_id: z.string(),
  product_name: z.string(),
  product_type: z.string(),
  label: z.enum(["recommended", "possible", "not_recommended"]),
  fit_reasons: z.array(z.string()),
  unmet_criteria: z.array(z.string()),
  checks: z.array(EligibilityCheck),
  indicative_annual_rate: z.string(),
  requested_amount: z.string(),
  term_months: z.number().int(),
  monthly_repayment: z.string(),
  dscr: z.string(),
  synthetic: z.boolean(),
});

export const NoFinancingNeeded = z.object({
  reason: z.string(),
  minimum_projected_cash: z.string(),
  funding_need: z.string(),
});

export const FinancingOptionsResponse = z.object({
  business_id: z.string(),
  currency: Currency,
  funding_need: z.string(),
  minimum_projected_cash: z.string(),
  avg_monthly_revenue: z.string(),
  monthly_operating_profit: z.string(),
  months_operating: z.number().int(),
  catalog: FinancingCatalog,
  matches: z.array(FinancingMatch),
  no_financing_needed: NoFinancingNeeded.nullable(),
  note: z.string(),
});


// ---------------------------------------------------------------------------
// Dashboard insights (mirror of backend/app/schemas/insights.py)
// ---------------------------------------------------------------------------

export const DashboardVisual = z.object({
  visual_id: z.string(),
  title: z.string(),
  what_it_shows: z.string(),
  what_to_notice: z.array(z.string()),
  why_it_matters: z.string(),
  evidence: z.record(z.unknown()),
});
export type DashboardVisualT = z.infer<typeof DashboardVisual>;

export const DashboardInsights = z.object({
  business_id: z.string(),
  currency: z.string(),
  period_start: z.string(),
  period_end_exclusive: z.string(),
  calculation_timestamp: z.string(),
  note: z.string(),
  visuals: z.array(DashboardVisual),
  alerts_count: z.number().int().nonnegative(),
  financing_counts: z.record(z.number().int().nonnegative()),
  summary: z.record(z.unknown()),
});
export type DashboardInsightsT = z.infer<typeof DashboardInsights>;
