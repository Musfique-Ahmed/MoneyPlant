import { describe, expect, it } from "vitest";
import { Business, DecisionReport, FinancialSummary, ImportPreview, Scenario } from "./schemas";

describe("Business schema", () => {
  it("accepts a valid business", () => {
    const parsed = Business.parse({
      id: "biz-1",
      name: "Acme",
      industry: "manufacturing",
      currency: "USD",
      fiscal_year_start_month: 1,
      locale: "en-US",
      min_cash_reserve: "0",
      target_operating_margin: "0.10",
      max_unsold_inventory_exposure_pct: "0.20",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    expect(parsed.industry).toBe("manufacturing");
  });

  it("rejects unknown industry", () => {
    expect(() =>
      Business.parse({
        id: "biz-1",
        name: "Acme",
        industry: "mining",
        currency: "USD",
        fiscal_year_start_month: 1,
        locale: "en-US",
        min_cash_reserve: "0",
        target_operating_margin: "0.10",
        max_unsold_inventory_exposure_pct: "0.20",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })
    ).toThrow();
  });
});

describe("FinancialSummary schema", () => {
  it("accepts a populated summary", () => {
    const parsed = FinancialSummary.parse({
      business_id: "biz-1",
      currency: "USD",
      period_start: "2026-01-01",
      period_end_exclusive: "2026-02-01",
      revenue: "1000.00",
      direct_costs: "400.00",
      gross_profit: "600.00",
      gross_margin: "0.6000",
      operating_expenses: "200.00",
      operating_profit: "400.00",
      operating_margin: "0.4000",
      cash_inflows: "1000.00",
      cash_outflows: "600.00",
      net_cash_movement: "400.00",
      opening_cash: "0.00",
      closing_cash: "400.00",
      minimum_projected_cash: "0.00",
      cash_runway_months: null,
      transaction_count: 10,
      data_coverage: { revenue: true, direct_costs: true },
      warnings: [],
      is_empty: false,
    });
    expect(parsed.currency).toBe("USD");
  });
});

describe("DecisionReport schema", () => {
  it("accepts all five overall statuses", () => {
    const base = {
      id: "d-1",
      business_id: "biz-1",
      scenario_version_id: null,
      question: "Q?",
      laya_status: "not_used",
      rule_evaluations: [],
      laya_assessments: [],
      binding_constraints: [],
      key_risks: [],
      recommendation: "go",
      missing_information: [],
      assumptions: [],
      caveats: [],
      business_goal: null,
      calculation_timestamp: new Date().toISOString(),
    };
    for (const status of ["proceed", "proceed_with_caution", "revise", "insufficient_data", "reject"] as const) {
      const parsed = DecisionReport.parse({ ...base, overall_status: status });
      expect(parsed.overall_status).toBe(status);
    }
  });
});

describe("ImportPreview schema", () => {
  it("accepts a minimal preview", () => {
    const parsed = ImportPreview.parse({
      filename: "test.csv",
      file_extension: ".csv",
      file_size_bytes: 100,
      encoding: "utf-8",
      sheet_name: null,
      headers: ["date", "amount"],
      sample_rows: [{ date: "2026-01-05", amount: "100" }],
      row_count: 1,
      suggested_mapping: { date: "tx_date", amount: "amount" },
      issues: [],
    });
    expect(parsed.headers).toHaveLength(2);
  });
});

describe("Scenario schema", () => {
  it("accepts a scenario with a result", () => {
    const parsed = Scenario.parse({
      id: "s-1",
      business_id: "biz-1",
      name: "Q1",
      industry: "manufacturing",
      description: "",
      status: "saved",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      latest_version_number: 1,
      latest_result: null,
    });
    expect(parsed.industry).toBe("manufacturing");
  });
});
