import { describe, expect, it } from "vitest";
import {
  Alert,
  AlertsResponse,
  Business,
  DashboardInsights,
  DashboardVisual,
  DataSource,
  DataSourceTestResult,
  DecisionReport,
  FinancialSummary,
  FinancingMatch,
  FinancingOptionsResponse,
  Freshness,
  ImportPreview,
  Scenario,
  SyncRun,
  SyncRunList,
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

describe("DashboardInsights schema", () => {
  const sampleVisual = {
    visual_id: "kpi",
    title: "Key metrics",
    what_it_shows: "Top-line numbers.",
    what_to_notice: ["Revenue grew 12%."],
    why_it_matters: "It matters.",
    evidence: {},
  };

  it("accepts a minimal insights payload", () => {
    const parsed = DashboardInsights.parse({
      business_id: "biz-1",
      currency: "USD",
      period_start: "2026-01-01",
      period_end_exclusive: "2026-02-01",
      calculation_timestamp: "2026-01-15T10:00:00Z",
      note: "Deterministic.",
      visuals: [sampleVisual],
      alerts_count: 0,
      financing_counts: { recommended: 0, possible: 0, not_recommended: 0 },
      summary: { is_empty: false },
    });
    expect(parsed.visuals[0]?.visual_id).toBe("kpi");
  });

  it("rejects a visual with missing fields", () => {
    expect(() =>
      DashboardVisual.parse({ visual_id: "kpi", title: "x", what_it_shows: "x", why_it_matters: "x", what_to_notice: [] }),
    ).toThrow();
  });
});

/* ------------------------------------------------------------------------- */
/* Data sources + sync runs                                                   */
/* ------------------------------------------------------------------------- */

describe("DataSource schema", () => {
  const baseSource = {
    id: "src-1",
    business_id: "biz-1",
    type: "file",
    name: "Daily POS exports",
    config: { path: "daily_transactions.xlsx" },
    column_mapping: { tx_date: "tx_date", amount: "amount" },
    incremental_key: null,
    incremental_value: null,
    file_content_sha256: "abc123",
    schedule: "daily",
    enabled: true,
    last_sync_at: new Date().toISOString(),
    last_status: "ok",
    last_error_summary: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  it("accepts a valid file source", () => {
    const parsed = DataSource.parse(baseSource);
    expect(parsed.type).toBe("file");
    expect(parsed.schedule).toBe("daily");
    expect(parsed.last_status).toBe("ok");
  });

  it("accepts a sql source with an incremental key", () => {
    const parsed = DataSource.parse({
      ...baseSource,
      type: "sql",
      incremental_key: "updated_at",
      incremental_value: "2026-03-01T00:00:00",
    });
    expect(parsed.type).toBe("sql");
    expect(parsed.incremental_key).toBe("updated_at");
  });

  it("rejects an unknown source type", () => {
    expect(() => DataSource.parse({ ...baseSource, type: "sftp" })).toThrow();
  });

  it("rejects an unknown schedule", () => {
    expect(() => DataSource.parse({ ...baseSource, schedule: "weekly" })).toThrow();
  });

  it("rejects an unknown last_status", () => {
    expect(() => DataSource.parse({ ...baseSource, last_status: "maybe" })).toThrow();
  });

  /**
   * The security guarantee: the backend must never return the credential
   * env-var name. Even if a payload somehow carried one, the parsed result
   * must not surface it, so nothing downstream can read or display it.
   */
  it("never surfaces secret_ref from a payload that contains one", () => {
    const parsed = DataSource.parse({ ...baseSource, secret_ref: "MY_DB_URL" });
    expect(parsed).not.toHaveProperty("secret_ref");
    expect(JSON.stringify(parsed)).not.toContain("MY_DB_URL");
  });

  it("tolerates a never-synced source", () => {
    const parsed = DataSource.parse({
      ...baseSource,
      last_sync_at: null,
      last_status: "never_run",
      incremental_value: null,
      file_content_sha256: null,
    });
    expect(parsed.last_sync_at).toBeNull();
    expect(parsed.last_status).toBe("never_run");
  });
});

describe("DataSourceTestResult schema", () => {
  it("accepts a successful probe", () => {
    const parsed = DataSourceTestResult.parse({
      status: "ok",
      last_message: null,
      sample_rows: ["{'tx_date': '2026-01-05'}"],
      headers: ["tx_date", "amount"],
      row_count_preview: 5,
    });
    expect(parsed.status).toBe("ok");
    expect(parsed.headers).toEqual(["tx_date", "amount"]);
  });

  it("accepts a failed probe with a safe message", () => {
    const parsed = DataSourceTestResult.parse({
      status: "failed",
      last_message: "path_outside_allowed_root",
      sample_rows: [],
      headers: [],
      row_count_preview: 0,
    });
    expect(parsed.status).toBe("failed");
    expect(parsed.last_message).toBe("path_outside_allowed_root");
  });
});

describe("SyncRun schema", () => {
  const baseRun = {
    id: "run-1",
    source_id: "src-1",
    started_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    status: "ok",
    rows_read: 12,
    rows_added: 8,
    rows_skipped_duplicate: 4,
    rows_rejected: 0,
    error_summary: null,
    trigger: "manual",
  };

  it("accepts a successful run and defaults validation_issues to []", () => {
    const parsed = SyncRun.parse(baseRun);
    expect(parsed.rows_added).toBe(8);
    expect(parsed.rows_skipped_duplicate).toBe(4);
    expect(parsed.validation_issues).toEqual([]);
  });

  it("accepts a partial run with rejected rows", () => {
    const parsed = SyncRun.parse({
      ...baseRun,
      status: "partial",
      rows_rejected: 2,
      validation_issues: [
        { row: 4, field: "amount", severity: "error", message: "Invalid amount" },
      ],
    });
    expect(parsed.status).toBe("partial");
    expect(parsed.rows_rejected).toBe(2);
    expect(parsed.validation_issues).toHaveLength(1);
  });

  it("accepts a failed run with an error summary", () => {
    const parsed = SyncRun.parse({
      ...baseRun,
      status: "failed",
      rows_added: 0,
      error_summary: "read_failed:file_not_found",
    });
    expect(parsed.status).toBe("failed");
    expect(parsed.error_summary).toBe("read_failed:file_not_found");
  });

  it("rejects a negative counter", () => {
    expect(() => SyncRun.parse({ ...baseRun, rows_added: -1 })).toThrow();
  });

  it("rejects an unknown trigger", () => {
    expect(() => SyncRun.parse({ ...baseRun, trigger: "webhook" })).toThrow();
  });

  it("wraps runs in the list envelope", () => {
    const parsed = SyncRunList.parse({ items: [baseRun] });
    expect(parsed.items).toHaveLength(1);
    expect(parsed.items[0]?.rows_read).toBe(12);
  });
});

describe("Freshness schema", () => {
  const baseFresh = {
    business_id: "biz-1",
    source_count: 1,
    last_sync_at: new Date().toISOString(),
    last_status: "ok",
    any_stale: false,
    headline: "Up to date.",
    last_sync_text: "2 h ago",
    sources: [
      {
        id: "src-1",
        name: "Daily POS exports",
        type: "file",
        schedule: "daily",
        enabled: true,
        last_sync_at: new Date().toISOString(),
        last_status: "ok",
        last_error_summary: null,
        is_stale: false,
        last_sync_text: "2 h ago",
      },
    ],
  };

  it("accepts an up-to-date strip", () => {
    const parsed = Freshness.parse(baseFresh);
    expect(parsed.source_count).toBe(1);
    expect(parsed.any_stale).toBe(false);
    expect(parsed.sources[0]?.is_stale).toBe(false);
  });

  it("accepts a stale source flagged in the headline", () => {
    const parsed = Freshness.parse({
      ...baseFresh,
      any_stale: true,
      last_status: "never_run",
      last_sync_at: null,
      last_sync_text: "Never",
      headline: "No sync yet — connect a source to start pulling data.",
      sources: [{ ...baseFresh.sources[0], is_stale: true, last_sync_at: null, last_status: "never_run" }],
    });
    expect(parsed.any_stale).toBe(true);
    expect(parsed.headline).toContain("No sync yet");
    expect(parsed.sources[0]?.is_stale).toBe(true);
  });

  it("accepts a strip with zero sources", () => {
    const parsed = Freshness.parse({
      ...baseFresh,
      source_count: 0,
      sources: [],
    });
    expect(parsed.source_count).toBe(0);
    expect(parsed.sources).toEqual([]);
  });
});