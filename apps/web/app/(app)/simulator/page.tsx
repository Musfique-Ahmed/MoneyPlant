"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { z } from "zod";
import { apiGet, apiPost } from "@/lib/api";
import { Business, Scenario, ScenarioResult, SimulateResponse } from "@/lib/schemas";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { formatMoney, formatPercent } from "@/lib/format";
import { Save, Play, RotateCw } from "lucide-react";
import { useWorkspace } from "@/components/WorkspaceContext";

export default function SimulatorPage() {
  const { businessId } = useWorkspace();
  const [scenarioName, setScenarioName] = useState("Q1 baseline");
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [industry, setIndustry] = useState<string>("manufacturing");

  const businesses = useQuery({
    queryKey: ["businesses"],
    queryFn: () => apiGet("/api/businesses", z.array(Business)),
  });
  const effectiveId = businessId ?? businesses.data?.[0]?.id ?? null;
  const business = businesses.data?.find((b) => b.id === effectiveId);

  const scenarios = useQuery({
    enabled: !!effectiveId,
    queryKey: ["scenarios", effectiveId],
    queryFn: () => apiGet(`/api/scenarios?business_id=${effectiveId}`, z.array(Scenario)),
  });

  const sim = useMutation({
    mutationFn: () => {
      if (!effectiveId) throw new Error("No business");
      const body = {
        business_id: effectiveId,
        inputs: { industry, ...inputs },
      };
      return apiPost("/api/scenarios/simulate", body, SimulateResponse);
    },
  });

  const save = useMutation({
    mutationFn: () => {
      if (!effectiveId) throw new Error("No business");
      return apiPost(
        "/api/scenarios",
        {
          business_id: effectiveId,
          name: scenarioName || "Untitled scenario",
          description: "",
          inputs: { industry, ...inputs },
        },
        Scenario
      );
    },
    onSuccess: () => {
      scenarios.refetch();
    },
  });

  const fields = useMemo(() => fieldsFor(industry), [industry]);

  if (businesses.isLoading) return <Skeleton className="m-6 h-48" />;
  if (!business) {
    return (
      <div className="p-6">
        <EmptyState title="No business selected" description="Create or select a business to run a scenario." />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 px-6 py-6 lg:grid-cols-[1fr_24rem]">
      <Card>
        <CardHeader
          title="Scenario"
          description={`Industry: ${business.industry}. Engine: 0.1.0 (deterministic).`}
          actions={
            <>
              <Button onClick={() => sim.mutate()} loading={sim.isPending} iconLeft={<Play size={14} />}>
                Simulate
              </Button>
              <Button
                variant="secondary"
                onClick={() => save.mutate()}
                loading={save.isPending}
                iconLeft={<Save size={14} />}
                disabled={!sim.data}
              >
                Save
              </Button>
            </>
          }
        />
        <CardBody>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Select
              label="Industry"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
            >
              <option value="manufacturing">Manufacturing</option>
              <option value="retail">Retail</option>
              <option value="wholesale">Wholesale</option>
              <option value="food">Food</option>
              <option value="service">Service</option>
            </Select>
            <Input
              label="Scenario name"
              value={scenarioName}
              onChange={(e) => setScenarioName(e.target.value)}
            />
            {fields.map((f) => (
              <Input
                key={f.key}
                label={f.label}
                hint={f.hint}
                value={inputs[f.key] ?? f.defaultValue}
                onChange={(e) => setInputs({ ...inputs, [f.key]: e.target.value })}
                prefix={f.prefix}
                suffix={f.suffix}
              />
            ))}
          </div>
        </CardBody>
      </Card>

      <div className="space-y-4">
        <ResultPanel result={sim.data?.result ?? null} error={sim.error as Error | null} loading={sim.isPending} />

        <Card>
          <CardHeader title="Saved scenarios" />
          <CardBody>
            {scenarios.isLoading ? (
              <Skeleton className="h-12" />
            ) : scenarios.isError ? (
              <ErrorState title="Could not load scenarios" />
            ) : !scenarios.data || scenarios.data.length === 0 ? (
              <div className="text-sm text-ink-muted">No saved scenarios yet.</div>
            ) : (
              <ul className="space-y-2 text-sm">
                {scenarios.data.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-center justify-between rounded border border-line p-2"
                  >
                    <div>
                      <div className="font-medium">{s.name}</div>
                      <div className="text-xs text-ink-muted">{s.industry} · v{s.latest_version_number ?? "—"}</div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      iconLeft={<RotateCw size={12} />}
                      onClick={() => setIndustry(s.industry)}
                    >
                      Use industry
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function ResultPanel({
  result,
  error,
  loading,
}: {
  result: z.infer<typeof ScenarioResult> | null;
  error: Error | null;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader title="Result" description="Authoritative output from the financial engine." />
      <CardBody>
        {!result && !error && (
          <div className="text-sm text-ink-muted">Run a simulation to see the projected revenue, profit, and cash.</div>
        )}
        {error && <ErrorState title="Simulation failed" description={error.message} />}
        {loading && <Skeleton className="h-24" />}
        {result && (
          <div className="space-y-2 text-sm">
            <Row label="Revenue" value={formatMoney(result.revenue, result.currency)} />
            <Row label="Direct costs" value={formatMoney(result.direct_costs, result.currency)} />
            <Row label="Gross profit" value={formatMoney(result.gross_profit, result.currency)} />
            <Row label="Operating expenses" value={formatMoney(result.operating_expenses, result.currency)} />
            <Row
              label="Operating profit"
              value={formatMoney(result.operating_profit, result.currency)}
              tone={tone(result.operating_profit)}
            />
            <Row
              label="Operating margin"
              value={result.operating_margin ? formatPercent(result.operating_margin) : "—"}
            />
            <Row
              label="Closing cash"
              value={formatMoney(result.closing_cash, result.currency)}
              tone={tone(result.closing_cash)}
            />
            <Row
              label="Min projected cash"
              value={formatMoney(result.minimum_projected_cash, result.currency)}
              tone={tone(result.minimum_projected_cash)}
            />
            {result.cash_runway_months && (
              <Row label="Runway (months)" value={result.cash_runway_months} />
            )}
            {result.warnings.length > 0 && (
              <ul className="mt-2 space-y-1 border-t border-line pt-2 text-xs text-warn">
                {result.warnings.map((w, i) => (
                  <li key={i}>· {w}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: "ok" | "bad" | "neutral" }) {
  const cls = tone === "bad" ? "text-bad" : tone === "ok" ? "text-ok" : "text-ink";
  return (
    <div className="flex items-center justify-between">
      <span className="text-ink-muted">{label}</span>
      <span className={`font-medium tabular-nums ${cls}`}>{value}</span>
    </div>
  );
}

function tone(value: string | null | undefined): "ok" | "bad" | "neutral" {
  if (!value) return "neutral";
  const n = Number(value);
  if (Number.isNaN(n)) return "neutral";
  return n < 0 ? "bad" : "ok";
}

type Field = { key: string; label: string; hint?: string; defaultValue: string; prefix?: string; suffix?: string };

function fieldsFor(industry: string): Field[] {
  const num = (key: string, label: string, hint?: string): Field => ({ key, label, hint, defaultValue: "0" });
  const usd = (key: string, label: string, hint?: string): Field => ({ key, label, hint, defaultValue: "0", suffix: "USD" });
  switch (industry) {
    case "manufacturing":
      return [
        num("opening_cash", "Opening cash"),
        num("opening_raw_material_qty", "Opening raw material (units)"),
        num("planned_raw_material_purchase_qty", "Planned raw-material purchase (units)"),
        usd("material_unit_cost", "Material unit cost", "Per unit of raw material"),
        num("material_per_unit", "Material per unit (raw units per finished unit)"),
        num("material_waste_pct", "Material waste % (e.g. 0.05 = 5%)"),
        num("planned_production_qty", "Planned production (units)"),
        num("production_capacity_qty", "Production capacity (units)"),
        usd("labor_cost_per_unit", "Labor cost per unit"),
        usd("other_variable_cost_per_unit", "Other variable cost per unit"),
        usd("selling_price", "Selling price"),
        num("expected_units_sold", "Expected units sold"),
        usd("operating_expenses", "Operating expenses (per horizon)"),
        num("customer_payment_delay_periods", "Customer payment delay (periods)"),
        num("supplier_payment_delay_periods", "Supplier payment delay (periods)"),
        num("horizon_months", "Horizon (months, 1–36)"),
      ];
    case "service":
      return [
        num("opening_cash", "Opening cash"),
        num("billable_hours_capacity", "Billable hours capacity"),
        num("planned_billable_utilization_pct", "Planned utilization (e.g. 0.75 = 75%)"),
        usd("hourly_price", "Hourly price"),
        usd("project_revenue", "Project revenue (optional)"),
        usd("labor_cost_per_hour", "Labor cost per hour"),
        usd("contractor_cost", "Contractor cost"),
        usd("project_expenses", "Project expenses"),
        usd("operating_expenses", "Operating expenses"),
        num("invoice_payment_delay_periods", "Invoice payment delay (periods)"),
        num("horizon_months", "Horizon (months)"),
      ];
    default:
      return [
        num("opening_cash", "Opening cash"),
        num("opening_inventory_units", "Opening inventory (units)"),
        num("planned_purchase_units", "Planned purchase (units)"),
        usd("purchase_unit_cost", "Purchase unit cost"),
        usd("selling_price", "Selling price"),
        num("expected_units_sold", "Expected units sold"),
        num("shrinkage_pct", "Shrinkage % (e.g. 0.02 = 2%)"),
        usd("operating_expenses", "Operating expenses"),
        num("customer_payment_delay_periods", "Customer payment delay (periods)"),
        num("supplier_payment_delay_periods", "Supplier payment delay (periods)"),
        num("horizon_months", "Horizon (months)"),
      ];
  }
}