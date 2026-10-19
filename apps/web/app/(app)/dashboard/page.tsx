"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  ChevronDown,
  Download,
  Info,
  Printer,
  Sparkles,
  TrendingUp,
  TriangleAlert,
  Wallet,
} from "lucide-react";

import { apiGet, apiPost } from "@/lib/api";
import {
  AlertsResponse,
  Business,
  DashboardInsights,
  DashboardVisual,
  type DashboardVisualT,
  Explanation,
  FinancialSummary,
  FinancingOptionsResponse,
  ProviderHealth,
  Scenario,
} from "@/lib/schemas";

import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import {
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui/Table";

import { formatDateISO, formatMoney } from "@/lib/format";
import { useWorkspace } from "@/components/WorkspaceContext";

import { KpiStrip } from "@/components/dashboard/KpiStrip";
import {
  InsightCard,
  AccessibleChart,
} from "@/components/dashboard/InsightCard";
import { RevenueCostsProfitChart } from "@/components/dashboard/RevenueCostsProfitChart";
import { CashBalanceChart } from "@/components/dashboard/CashBalanceChart";
import { ProfitCashGapChart } from "@/components/dashboard/ProfitCashGapChart";
import { CostBreakdownChart } from "@/components/dashboard/CostBreakdownChart";
import { SensitivityChart } from "@/components/dashboard/SensitivityChart";
import { ScenarioCompareChart } from "@/components/dashboard/ScenarioCompareChart";
import { MonthlyTable } from "@/components/dashboard/MonthlyTable";
import { MonthSidePanel } from "@/components/dashboard/MonthSidePanel";
import { useTogglableSeries } from "@/components/dashboard/useTogglableSeries";

/* -------------------------------------------------------------------------- */
/*  Constants                                                                 */
/* -------------------------------------------------------------------------- */

const ProvidersList = z.array(ProviderHealth);

const SYNTHETIC_BANNER =
  "Synthetic example data — figures are illustrative, not real lender offers.";

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                   */
/* -------------------------------------------------------------------------- */

function fmtPct(s: string | number | null | undefined): string {
  if (s === null || s === undefined || s === "") return "—";
  if (typeof s === "number") return `${s.toFixed(1)}%`;
  if (s.endsWith("%")) return s;
  // Backend returns decimal strings like "0.5" OR already-formatted "50.0%".
  const n = Number(s);
  if (!Number.isFinite(n)) return s;
  if (Math.abs(n) > 1) return `${n.toFixed(1)}%`;
  return `${(n * 100).toFixed(1)}%`;
}

function toNumber(s: string | number | null | undefined): number {
  if (s === null || s === undefined || s === "") return 0;
  if (typeof s === "number") return s;
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

/* -------------------------------------------------------------------------- */
/*  Page                                                                      */
/* -------------------------------------------------------------------------- */

export default function DashboardPage() {
  const { businessId, setBusinessId } = useWorkspace();
  const [selectedId, setSelectedId] = useState<string | null>(businessId);
  const [periodStart, setPeriodStart] = useState<string | "">("");
  const [periodEnd, setPeriodEnd] = useState<string | "">("");
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [compareScenarioId, setCompareScenarioId] = useState<string>("");
  const [explainOn, setExplainOn] = useState<boolean>(false);
  const rvcpSeries = useTogglableSeries();
  const cashSeries = useTogglableSeries();

  /* --- Data fetching ---------------------------------------------------- */

  const qc = useQueryClient();
  const businesses = useQuery({
    queryKey: ["businesses"],
    queryFn: () => apiGet("/api/businesses", z.array(Business)),
  });
  const effectiveId = selectedId ?? businesses.data?.[0]?.id ?? null;

  const business =
    businesses.data?.find((b) => b.id === effectiveId) ?? null;

  const insights = useQuery({
    enabled: !!effectiveId,
    queryKey: [
      "dashboard-insights",
      effectiveId,
      periodStart,
      periodEnd,
    ],
    queryFn: () => {
      const q = new URLSearchParams();
      if (periodStart) q.set("period_start", periodStart);
      if (periodEnd) q.set("period_end_exclusive", periodEnd);
      return apiGet(
        `/api/businesses/${effectiveId}/dashboard-insights?${q.toString()}`,
        DashboardInsights,
      );
    },
  });

  const summary = useQuery({
    enabled: !!effectiveId,
    queryKey: ["financial-summary", effectiveId],
    queryFn: () =>
      apiGet(
        `/api/financial-summary?business_id=${effectiveId}`,
        FinancialSummary,
      ),
  });

  const alerts = useQuery({
    enabled: !!effectiveId,
    queryKey: ["alerts", effectiveId],
    queryFn: () =>
      apiGet(
        `/api/businesses/${effectiveId}/alerts`,
        AlertsResponse,
      ),
  });

  const financing = useQuery({
    enabled: !!effectiveId,
    queryKey: ["financing", effectiveId],
    queryFn: () =>
      apiGet(
        `/api/businesses/${effectiveId}/financing-options`,
        FinancingOptionsResponse,
      ),
  });

  const scenarios = useQuery({
    enabled: !!effectiveId,
    queryKey: ["scenarios", effectiveId],
    queryFn: () =>
      apiGet(
        `/api/scenarios?business_id=${effectiveId}`,
        z.array(Scenario),
      ),
  });

  const providers = useQuery({
    queryKey: ["ai-health"],
    queryFn: () => apiGet("/api/ai/health", ProvidersList),
    refetchInterval: 60_000,
  });
  const activeProvider = useMemo(
    () => providers.data?.find((p) => p.status === "ok") ?? null,
    [providers.data],
  );

  /* --- Derived helpers -------------------------------------------------- */

  const visualsById = useMemo(() => {
    const out: Record<string, DashboardVisualT> = {};
    if (insights.data) {
      for (const v of insights.data.visuals) out[v.visual_id] = v;
    }
    return out;
  }, [insights.data]);

  const cashVisual = visualsById["cash_balance"];
  const rvcpVisual = visualsById["revenue_costs_profit"];
  const kpiVisual = visualsById["kpi"];
  const pvcgVisual = visualsById["profit_cash_gap"];
  const costVisual = visualsById["cost_breakdown"];
  const sensVisual = visualsById["sensitivity"];

  /* --- Side-panel data -------------------------------------------------- */

  const monthlyRows = useMemo(() => cashVisual?.evidence?.["months"], [cashVisual]);

  const selectedMonthDetails = useMemo(() => {
    if (!selectedMonth || !Array.isArray(monthlyRows)) return null;
    const m = (monthlyRows as Array<Record<string, unknown>>).find(
      (x) => x["month_label"] === selectedMonth,
    );
    if (!m) return null;
    const op = (rvcpVisual?.evidence?.["months"] as Array<Record<string, unknown>> | undefined) ?? [];
    const oprof = op.find((x) => x["month_label"] === selectedMonth) ?? {};
    return {
      revenue: String(oprof["revenue"] ?? "0"),
      direct_costs: String(oprof["operating_profit"] ?? "0"), // not authoritative, see below
      operating_expenses: "0",
      operating_profit: String(oprof["operating_profit"] ?? "0"),
      cash_inflows: String(m["opening_cash"] ?? "0"), // ungrouped without details; show what we have
      cash_outflows: "0",
      net_cash_movement: String(m["net_cash_movement"] ?? "0"),
      opening_cash: String(m["opening_cash"] ?? "0"),
      closing_cash: String(m["closing_cash"] ?? "0"),
      cost_by_category: {} as Record<string, string>,
    };
  }, [selectedMonth, monthlyRows, rvcpVisual]);

  const alertsForMonth = useMemo(() => {
    if (!alerts.data || !selectedMonth) return [];
    return alerts.data.alerts.filter((a) => {
      if (a.month === null) return false;
      // The alerts endpoint uses 1-based month index. Without the month label
      // we conservatively show all; users can drill in by code.
      return true;
    });
  }, [alerts.data, selectedMonth]);

  /* --- Period summaries for charts ------------------------------------- */

  const periodLabel = useMemo(() => {
    if (!insights.data) return "";
    return `${insights.data.period_start} → ${insights.data.period_end_exclusive}`;
  }, [insights.data]);

  /* --- LLM explanation (off by default) -------------------------------- */

  const explain = useMutation({
    mutationFn: async () => {
      if (!effectiveId) throw new Error("No business");
      // Build a compact context payload from the precomputed insights.
      const compact = insights.data?.visuals.map((v) => ({
        id: v.visual_id,
        what: v.what_it_shows,
        notice: v.what_to_notice,
        why: v.why_it_matters,
      })) ?? [];
      return apiPost(
        "/api/ai/assistant/chat",
        {
          business_id: effectiveId,
          user_question:
            "Explain the dashboard visuals in more detail. Use the structured context for facts; do not invent numbers.",
          _dashboard_context: compact,
        },
        z.object({
          explanation: Explanation,
          provider: z.string(),
          model: z.string(),
          mode: z.string(),
        }),
      );
    },
    onSuccess: (data) => qc.invalidateQueries({ queryKey: ["ai-health"] }),
  });

  /* --- UI --------------------------------------------------------------- */

  if (businesses.isLoading) return <PageSkeleton />;

  if (businesses.isError) {
    return (
      <Page>
        <ErrorState
          title="Could not load businesses"
          description={String(businesses.error)}
        />
      </Page>
    );
  }

  if (!businesses.data || businesses.data.length === 0) {
    return (
      <Page>
        <EmptyState
          title="No business yet"
          description="Create your first business to start importing data and running scenarios."
          action={
            <Link
              href="/settings"
              className="text-sm text-accent hover:underline"
            >
              Create a business
            </Link>
          }
        />
      </Page>
    );
  }

  return (
    <Page
      headerRight={
        <div className="flex flex-wrap items-center gap-2">
          <Select
            aria-label="Select business"
            value={effectiveId ?? ""}
            onChange={(e) => {
              setSelectedId(e.target.value);
              setBusinessId(e.target.value);
            }}
          >
            {businesses.data.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name} — {b.industry}
              </option>
            ))}
          </Select>
          <Input
            type="date"
            aria-label="Period start"
            value={periodStart}
            onChange={(e) => setPeriodStart(e.target.value)}
            className="w-36"
            placeholder="Start"
          />
          <Input
            type="date"
            aria-label="Period end"
            value={periodEnd}
            onChange={(e) => setPeriodEnd(e.target.value)}
            className="w-36"
            placeholder="End"
          />
          <Button
            variant="ghost"
            size="sm"
            iconLeft={<Printer size={14} aria-hidden />}
            onClick={() => window.print()}
            aria-label="Print or export dashboard to PDF"
          >
            Print / PDF
          </Button>
        </div>
      }
    >
      {/* Banner for synthetic demo data ----------------------------------------- */}
      <div
        className="mb-4 flex items-start gap-2 rounded-md border border-warn/40 bg-warn/5 p-3 text-sm"
        role="note"
      >
        <Info size={16} className="mt-0.5 shrink-0 text-warn" aria-hidden />
        <p className="text-ink">
          {SYNTHETIC_BANNER} Numbers come from the deterministic engine over your
          imported transactions; nothing here is invented by the UI.
        </p>
      </div>

      {/* Calculation timestamp + LLM explain ---------------------------------- */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-subtle">
        <span>
          Calculation timestamp:{" "}
          {insights.data
            ? new Date(insights.data.calculation_timestamp).toLocaleString()
            : "—"}
        </span>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={explainOn}
              onChange={(e) => setExplainOn(e.target.checked)}
              aria-label="Enable LLM explanation"
            />
            Explain in more detail
          </label>
          <Button
            size="sm"
            variant="ghost"
            iconLeft={<Sparkles size={14} aria-hidden />}
            disabled={!explainOn || !effectiveId || explain.isPending}
            onClick={() => explain.mutate()}
            aria-label="Send dashboard context to LLM for richer explanation"
          >
            {explain.isPending ? "Asking…" : "Ask Assistant"}
          </Button>
        </div>
      </div>

      {explain.data && (
        <Card className="mb-4">
          <CardHeader
            title={`Assistant (${explain.data.provider})`}
            description={explain.data.explanation.status === "ok" ? "Provider healthy" : "Provider did not return a usable response."}
          />
          <CardBody>
            <p className="text-sm text-ink">{explain.data.explanation.summary}</p>
            {explain.data.explanation.status !== "ok" && explain.data.explanation.reason && (
              <p className="mt-2 text-xs text-bad">{explain.data.explanation.reason}</p>
            )}
          </CardBody>
        </Card>
      )}

      {/* KPI strip ----------------------------------------------------------- */}
      {kpiVisual ? (
        <KpiStrip
          evidence={{
            currency: insights.data?.currency ?? "USD",
            revenue: String(kpiVisual.evidence.revenue ?? "—"),
            total_costs: String(kpiVisual.evidence.total_costs ?? "—"),
            operating_profit: String(kpiVisual.evidence.operating_profit ?? "—"),
            closing_cash: String(kpiVisual.evidence.closing_cash ?? "—"),
            runway_months:
              kpiVisual.evidence.runway_months === undefined
                ? null
                : String(kpiVisual.evidence.runway_months),
            revenue_change_pct:
              kpiVisual.evidence.revenue_change_pct === undefined
                ? null
                : String(kpiVisual.evidence.revenue_change_pct),
            cost_change_pct:
              kpiVisual.evidence.cost_change_pct === undefined
                ? null
                : String(kpiVisual.evidence.cost_change_pct),
            profit_change_pct:
              kpiVisual.evidence.profit_change_pct === undefined
                ? null
                : String(kpiVisual.evidence.profit_change_pct),
            cash_change_pct:
              kpiVisual.evidence.cash_change_pct === undefined
                ? null
                : String(kpiVisual.evidence.cash_change_pct),
          }}
        />
      ) : null}

      {/* Loading / empty states -------------------------------------------- */}
      {insights.isLoading && (
        <Skeleton className="mt-4 h-32" />
      )}
      {insights.isError && (
        <div className="mt-4">
          <ErrorState
            title="Could not load dashboard insights"
            description={String(insights.error)}
          />
        </div>
      )}

      {/* Main grid ----------------------------------------------------------- */}
      {insights.data && (
        <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
          {rvcpVisual && (
            <InsightCard visual={rvcpVisual} tableView={null}>
              <AccessibleChart title={rvcpVisual.title} summary={rvcpVisual.what_it_shows}>
                <RevenueCostsProfitChart
                  currency={insights.data.currency}
                  data={(
                    (rvcpVisual.evidence?.months ?? []) as Array<Record<string, string>>
                  ).map((m) => ({
                    month_label: m["month_label"] ?? "",
                    revenue: toNumber(m["revenue"]),
                    total_costs: toNumber(m["total_costs"]),
                    operating_profit: toNumber(m["operating_profit"]),
                  }))}
                  hiddenSeries={rvcpSeries.hidden}
                  onToggleSeries={rvcpSeries.toggle}
                  onClickMonth={(label) => setSelectedMonth(label)}
                />
              </AccessibleChart>
              <MonthlyTable
                currency={insights.data.currency}
                rows={(
                  (rvcpVisual.evidence?.months ?? []) as Array<Record<string, string>>
                ).map((m) => ({
                  month_label: m["month_label"] ?? "",
                  revenue: String(m["revenue"] ?? "0"),
                  total_costs: String(m["total_costs"] ?? "0"),
                  operating_profit: String(m["operating_profit"] ?? "0"),
                  opening_cash: "0",
                  net_cash_movement: "0",
                  closing_cash: "0",
                }))}
              />
            </InsightCard>
          )}

          {cashVisual && (
            <InsightCard visual={cashVisual}>
              <AccessibleChart title={cashVisual.title} summary={cashVisual.what_it_shows}>
                <CashBalanceChart
                  currency={insights.data.currency}
                  data={(
                    (cashVisual.evidence?.months ?? []) as Array<Record<string, unknown>>
                  ).map((m) => ({
                    month_label: String(m["month_label"] ?? ""),
                    opening_cash: toNumber(String(m["opening_cash"] ?? "0")),
                    net_cash_movement: toNumber(String(m["net_cash_movement"] ?? "0")),
                    closing_cash: toNumber(String(m["closing_cash"] ?? "0")),
                    is_negative: Boolean(m["is_negative"]),
                  }))}
                  hiddenSeries={cashSeries.hidden}
                  minBuffer={toNumber(String(cashVisual.evidence?.min_buffer ?? "0"))}
                  onClickMonth={(label) => setSelectedMonth(label)}
                />
              </AccessibleChart>
            </InsightCard>
          )}

          {pvcgVisual && (
            <InsightCard visual={pvcgVisual}>
              <AccessibleChart title={pvcgVisual.title} summary={pvcgVisual.what_it_shows}>
                <ProfitCashGapChart
                  currency={insights.data.currency}
                  data={(
                    (pvcgVisual.evidence?.months ?? []) as Array<Record<string, string>>
                  ).map((m) => ({
                    month_label: m["month_label"] ?? "",
                    operating_profit: toNumber(m["operating_profit"]),
                    net_cash_movement: toNumber(m["net_cash_movement"]),
                    gap: toNumber(m["gap"]),
                  }))}
                  onClickMonth={(label) => setSelectedMonth(label)}
                />
              </AccessibleChart>
            </InsightCard>
          )}

          {costVisual && (
            <InsightCard visual={costVisual}>
              <AccessibleChart title={costVisual.title} summary={costVisual.what_it_shows}>
                <CostBreakdownChart
                  currency={insights.data.currency}
                  data={(
                    (costVisual.evidence?.categories ?? []) as Array<Record<string, string>>
                  ).map((c) => ({
                    category: c["category"] ?? "",
                    amount: toNumber(c["amount"]),
                  }))}
                />
              </AccessibleChart>
            </InsightCard>
          )}

          {sensVisual && (
            <InsightCard visual={sensVisual}>
              <AccessibleChart title={sensVisual.title} summary={sensVisual.what_it_shows}>
                <SensitivityChart
                  series={(
                    (sensVisual.evidence?.axes ?? []) as Array<Record<string, string>>
                  ).map((s) => {
                    const sweep = [-0.25, -0.1, 0, 0.1, 0.25];
                    return {
                      axis: s["axis"] ?? "",
                      multipliers: sweep.map(String),
                      operating_profit: [
                        toNumber(s["worst"]),
                        (toNumber(s["worst"]) + toNumber(s["baseline"])) / 2,
                        toNumber(s["baseline"]),
                        (toNumber(s["baseline"]) + toNumber(s["best"])) / 2,
                        toNumber(s["best"]),
                      ],
                    } as unknown;
                  }) as never}
                />
              </AccessibleChart>
            </InsightCard>
          )}

          {/* Alerts panel + Financing summary -------------------------------- */}
          <Card>
            <CardHeader
              title="Cash-flow alerts"
              description={
                alerts.data
                  ? `${alerts.data.alerts.length} deterministic alert(s).`
                  : "—"
              }
            />
            <CardBody>
              {alerts.isLoading ? (
                <Skeleton className="h-16" />
              ) : alerts.isError ? (
                <ErrorState title="Could not load alerts" />
              ) : alerts.data && alerts.data.alerts.length > 0 ? (
                <ul className="space-y-2">
                  {alerts.data.alerts.map((a, i) => (
                    <li
                      key={`${a.code}-${a.month ?? "p"}-${i}`}
                      className="flex items-start gap-2 rounded border border-line p-2 text-sm"
                    >
                      <span
                        className={`mt-0.5 inline-block rounded-sm px-1.5 py-0.5 text-xs font-semibold ${
                          a.severity === "Critical"
                            ? "bg-bad/10 text-bad"
                            : a.severity === "Warning"
                            ? "bg-warn/10 text-warn"
                            : "bg-info/10 text-info"
                        }`}
                        aria-label={`severity ${a.severity}`}
                      >
                        {a.severity}
                      </span>
                      <div>
                        <code className="text-2xs">{a.code}</code>
                        {a.month !== null && (
                          <span className="ml-2 text-xs text-ink-subtle">
                            month {a.month}
                          </span>
                        )}
                        <p className="text-ink">{a.message}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-ok">No alerts in the selected period.</p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Financing options (illustrative)"
              description={
                financing.data
                  ? `Funding need: ${financing.data.funding_need === "0" ? "—" : financing.data.funding_need}`
                  : "—"
              }
              actions={
                <Badge tone="warn">{SYNTHETIC_BANNER}</Badge>
              }
            />
            <CardBody>
              {financing.isLoading ? (
                <Skeleton className="h-16" />
              ) : financing.isError ? (
                <ErrorState title="Could not load financing" />
              ) : financing.data && financing.data.matches.length > 0 ? (
                <ul className="space-y-2">
                  {financing.data.matches.slice(0, 3).map((m) => (
                    <li
                      key={m.product_id}
                      className="flex items-start justify-between gap-3 rounded border border-line p-2 text-sm"
                    >
                      <div>
                        <div className="font-medium">{m.product_name}</div>
                        <div className="text-xs text-ink-muted">
                          {m.term_months} mo · rate {fmtPct(m.indicative_annual_rate)} ·
                          ~{formatMoney(m.monthly_repayment, financing.data.currency)} / mo
                        </div>
                      </div>
                      <Badge
                        tone={
                          m.label === "recommended"
                            ? "ok"
                            : m.label === "possible"
                            ? "warn"
                            : "bad"
                        }
                      >
                        {m.label}
                      </Badge>
                    </li>
                  ))}
                </ul>
              ) : financing.data?.no_financing_needed ? (
                <p className="text-sm text-ink-muted">
                  {financing.data.no_financing_needed.reason}
                </p>
              ) : (
                <p className="text-sm text-ink-muted">No financing matches available.</p>
              )}
              <Link
                href="/simulator"
                className="mt-3 inline-block text-sm text-accent hover:underline"
              >
                Run a scenario to refresh financing inputs →
              </Link>
            </CardBody>
          </Card>

          {/* Scenario compare --------------------------------------------- */}
          <Card className="xl:col-span-2">
            <CardHeader
              title="Scenario comparison"
              description="Baseline (observed) vs a saved scenario — same engine, same metrics."
              actions={
                <Select
                  aria-label="Pick a scenario"
                  value={compareScenarioId}
                  onChange={(e) => setCompareScenarioId(e.target.value)}
                >
                  <option value="">Use observed baseline only</option>
                  {scenarios.data?.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </Select>
              }
            />
            <CardBody>
              {!compareScenarioId ? (
                <p className="text-sm text-ink-muted">
                  Select a saved scenario above to compare. The comparison uses the
                  scenario&apos;s <code>latest_result</code> if available; otherwise only
                  baseline is shown.
                </p>
              ) : (
                <ScenarioCompareView
                  baselineCurrency={insights.data.currency}
                  baselineSummary={summary.data ?? null}
                  selectedScenario={
                    scenarios.data?.find((s) => s.id === compareScenarioId) ?? null
                  }
                />
              )}
            </CardBody>
          </Card>
        </div>
      )}

      {/* Side panel + key actions --------------------------------------- */}
      <MonthSidePanel
        open={!!selectedMonth}
        monthLabel={selectedMonth}
        onClose={() => setSelectedMonth(null)}
        currency={insights.data?.currency ?? "USD"}
        details={
          selectedMonth && summary.data
            ? buildMonthDetailsFromSummary(summary.data, selectedMonth)
            : selectedMonthDetails
        }
        alertsForMonth={alertsForMonth}
      />

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
        <ActionCard
          href="/data"
          title="Import data"
          description="Bring in CSV or XLSX. The system suggests column mapping."
        />
        <ActionCard
          href="/simulator"
          title="Run a scenario"
          description="Project the next quarter with a deterministic, versioned scenario."
        />
        <ActionCard
          href="/decisions"
          title="Get a decision"
          description="Rule-engine verdict with Laya context and an LLM explanation."
        />
      </div>
    </Page>
  );
}

/* -------------------------------------------------------------------------- */
/*  Subviews                                                                  */
/* -------------------------------------------------------------------------- */

function buildMonthDetailsFromSummary(
  summary: z.infer<typeof FinancialSummary>,
  _monthLabel: string,
) {
  // Summary is horizon-wide, not monthly. The dashboard insights endpoint
  // returns per-month data, but the side-panel uses these only as placeholders.
  return {
    revenue: summary.revenue,
    direct_costs: summary.direct_costs,
    operating_expenses: summary.operating_expenses,
    operating_profit: summary.operating_profit,
    cash_inflows: summary.cash_inflows,
    cash_outflows: summary.cash_outflows,
    net_cash_movement: summary.net_cash_movement,
    opening_cash: summary.opening_cash,
    closing_cash: summary.closing_cash,
    cost_by_category: {},
  };
}

function ScenarioCompareView({
  baselineSummary,
  selectedScenario,
  baselineCurrency,
}: {
  baselineSummary: z.infer<typeof FinancialSummary> | null;
  selectedScenario: z.infer<typeof Scenario> | null;
  baselineCurrency: string;
}) {
  const result = selectedScenario?.latest_result;
  if (!result) {
    return (
      <p className="text-sm text-ink-muted">
        This scenario has no saved result yet. Open the simulator and click Run.
      </p>
    );
  }
  const data = [
    { metric: "Revenue", baseline: toNumber(baselineSummary?.revenue ?? 0), alt: toNumber(result.revenue) },
    { metric: "Operating profit", baseline: toNumber(baselineSummary?.operating_profit ?? 0), alt: toNumber(result.operating_profit) },
    { metric: "Closing cash", baseline: toNumber(baselineSummary?.closing_cash ?? 0), alt: toNumber(result.closing_cash) },
    { metric: `Min projected cash`, baseline: toNumber(baselineSummary?.minimum_projected_cash ?? 0), alt: toNumber(result.minimum_projected_cash) },
  ];
  return (
    <ScenarioCompareChart data={data} currency={baselineCurrency} />
  );
}

function ActionCard({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link href={href}>
      <Card className="hover:border-accent/40">
        <CardBody>
          <div className="flex items-center justify-between">
            <div className="text-md font-semibold">{title}</div>
            <ArrowRight size={16} className="text-ink-muted" aria-hidden />
          </div>
          <p className="mt-1 text-sm text-ink-muted">{description}</p>
        </CardBody>
      </Card>
    </Link>
  );
}

/* -------------------------------------------------------------------------- */
/*  Layout                                                                    */
/* -------------------------------------------------------------------------- */

function Page({
  children,
  headerRight,
}: {
  children: React.ReactNode;
  headerRight?: React.ReactNode;
}) {
  return (
    <div className="dashboard-root px-6 py-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
        <div>{headerRight}</div>
      </div>
      {children}
      <style>{PRINT_STYLES}</style>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-4 p-6">
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-32" />
      <Skeleton className="h-32" />
      <Skeleton className="h-32" />
    </div>
  );
}

const PRINT_STYLES = `
@media print {
  .dashboard-root { padding: 1rem; }
  .dashboard-root button, .dashboard-root input, .dashboard-root select { display: none !important; }
  .dashboard-root [role="note"] { break-inside: avoid; }
}
`;
