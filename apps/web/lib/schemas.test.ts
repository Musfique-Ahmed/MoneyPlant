import { describe, expect, it } from "vitest";
import {
  Alert,
  AlertsResponse,
  Business,
  DecisionReport,
  FinancialSummary,
  FinancingMatch,
  FinancingOptionsResponse,
  ImportPreview,
  Scenario,
} from "./schemas";

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
      latest_version_id: "v-1",
      latest_result: null,
    });
    expect(parsed.industry).toBe("manufacturing");
  });
});

describe("Alert schema", () => {
  it("accepts the three severities and preserves evidence", () => {
    for (const severity of ["Critical", "Warning", "Info"] as const) {
      const parsed = Alert.parse({
        code: "NEGATIVE_CASH",
        severity,
        month: 3,
        message: "Closing cash is negative",
        evidence: { closing_cash: "-100.00", currency: "USD" },
      });
      expect(parsed.severity).toBe(severity);
      expect(parsed.evidence.closing_cash).toBe("-100.00");
    }
  });

  it("accepts month=null for period-wide alerts", () => {
    const parsed = Alert.parse({
      code: "SHORT_RUNWAY",
      severity: "Warning",
      month: null,
      message: "Cash runway is short",
      evidence: { runway_months: "0.5" },
    });
    expect(parsed.month).toBeNull();
  });

  it("rejects unknown severity", () => {
    expect(() =>
      Alert.parse({
        code: "X",
        severity: "OMG",
        month: 1,
        message: "",
        evidence: {},
      })
    ).toThrow();
  });
});

describe("AlertsResponse schema", () => {
  it("accepts an empty alerts list (no triggers)", () => {
    const parsed = AlertsResponse.parse({
      business_id: "biz-1",
      currency: "USD",
      horizon_months: 3,
      runway_months: "4.5000",
      operating_profit: "3000.00",
      monthly_cash: [
        { month_index: 1, opening_cash: "0.00", net_cash_movement: "100.00", closing_cash: "100.00" },
      ],
      config: {
        low_buffer_months: "1",
        short_runway_warning_months: "3",
        short_runway_critical_months: "1",
        sharp_drop_pct: "0.25",
      },
      alerts: [],
      source: "transactions-derived",
      note: "All clear.",
    });
    expect(parsed.alerts).toHaveLength(0);
  });
});

describe("FinancingMatch schema", () => {
  it("accepts the three labels", () => {
    for (const label of ["recommended", "possible", "not_recommended"] as const) {
      const parsed = FinancingMatch.parse({
        product_id: "wc-line-001",
        product_name: "Working-capital line",
        product_type: "working_capital_line",
        label,
        fit_reasons: [],
        unmet_criteria: [],
        checks: [],
        indicative_annual_rate: "0.12",
        requested_amount: "10000.00",
        term_months: 12,
        monthly_repayment: "888.49",
        dscr: "1.5012",
        synthetic: true,
      });
      expect(parsed.label).toBe(label);
    }
  });

  it("rejects an unknown label", () => {
    expect(() =>
      FinancingMatch.parse({
        product_id: "x",
        product_name: "x",
        product_type: "x",
        label: "definitely_yes",
        fit_reasons: [],
        unmet_criteria: [],
        checks: [],
        indicative_annual_rate: "0.0",
        requested_amount: "0",
        term_months: 1,
        monthly_repayment: "0",
        dscr: "",
        synthetic: true,
      })
    ).toThrow();
  });
});

describe("FinancingOptionsResponse schema", () => {
  it("accepts the no_financing_needed sentinel", () => {
    const parsed = FinancingOptionsResponse.parse({
      business_id: "biz-1",
      currency: "USD",
      funding_need: "0",
      minimum_projected_cash: "1500.00",
      avg_monthly_revenue: "5000.00",
      monthly_operating_profit: "1500.00",
      months_operating: 12,
      catalog: {
        products: [],
        synthetic: true,
        disclaimer: "SYNTHETIC EXAMPLE DATA.",
      },
      matches: [],
      no_financing_needed: {
        reason: "No projected cash shortfall. Financing not required.",
        minimum_projected_cash: "1500.00",
        funding_need: "0",
      },
      note: "Not a credit decision.",
    });
    expect(parsed.no_financing_needed?.reason).toContain("No projected cash shortfall");
  });

  it("accepts a populated matches list", () => {
    const parsed = FinancingOptionsResponse.parse({
      business_id: "biz-1",
      currency: "USD",
      funding_need: "10000.00",
      minimum_projected_cash: "-500.00",
      avg_monthly_revenue: "3000.00",
      monthly_operating_profit: "500.00",
      months_operating: 12,
      catalog: {
        products: [
          {
            id: "wc-line-001",
            name: "WC line",
            type: "working_capital_line",
            min_amount: "1000",
            max_amount: "50000",
            min_months_operating: 6,
            min_avg_monthly_revenue: "3000",
            max_term_months: 12,
            indicative_annual_rate: "0.12",
            suitable_use_cases: ["cash_gap"],
            synthetic: true,
          },
        ],
        synthetic: true,
        disclaimer: "SYNTHETIC",
      },
      matches: [
        {
          product_id: "wc-line-001",
          product_name: "WC line",
          product_type: "working_capital_line",
          label: "possible",
          fit_reasons: ["funding_need_within_range"],
          unmet_criteria: [],
          checks: [
            {
              name: "funding_need_within_range",
              passed: true,
              requirement: "1000..50000",
              actual: "10000.00 USD",
            },
          ],
          indicative_annual_rate: "0.12",
          requested_amount: "10000.00",
          term_months: 12,
          monthly_repayment: "888.49",
          dscr: "0.5680",
          synthetic: true,
        },
      ],
      no_financing_needed: null,
      note: "Not a credit decision.",
    });
    expect(parsed.matches).toHaveLength(1);
    expect(parsed.matches[0]?.label).toBe("possible");
  });
});
