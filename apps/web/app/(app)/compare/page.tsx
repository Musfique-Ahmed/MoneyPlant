"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { z } from "zod";
import { apiGet, apiPost } from "@/lib/api";
import { Business, Scenario } from "@/lib/schemas";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { formatMoney, formatPercent } from "@/lib/format";
import { useWorkspace } from "@/components/WorkspaceContext";

const ComparisonRow = z.object({
  scenario_id: z.string(),
  scenario_name: z.string(),
  industry: z.string(),
  revenue: z.string(),
  direct_costs: z.string(),
  gross_profit: z.string(),
  operating_profit: z.string(),
  operating_margin: z.string().nullable(),
  closing_cash: z.string(),
  minimum_projected_cash: z.string(),
  unsold_inventory_value: z.string().nullable(),
  business_goal: z.string().nullable(),
});

const Comparison = z.object({
  rows: z.array(ComparisonRow),
  baseline_id: z.string(),
  diffs: z.array(z.record(z.string().nullable())),
  warnings: z.array(z.string()).default([]),
});

export default function ComparePage() {
  const { businessId } = useWorkspace();
  const [picks, setPicks] = useState<string[]>([]);

  const businesses = useQuery({
    queryKey: ["businesses"],
    queryFn: () => apiGet("/api/businesses", z.array(Business)),
  });
  const effectiveId = businessId ?? businesses.data?.[0]?.id ?? null;

  const scenarios = useQuery({
    enabled: !!effectiveId,
    queryKey: ["scenarios", effectiveId],
    queryFn: () => apiGet(`/api/scenarios?business_id=${effectiveId}`, z.array(Scenario)),
  });

  const compare = useMutation({
    mutationFn: () => {
      if (!effectiveId) throw new Error("No business");
      if (picks.length < 1) throw new Error("Pick at least one scenario");
      return apiPost(
        "/api/scenarios/compare",
        { business_id: effectiveId, scenario_ids: picks.slice(0, 5) },
        Comparison
      );
    },
  });

  const options = useMemo(() => scenarios.data ?? [], [scenarios.data]);

  return (
    <div className="space-y-4 px-6 py-6">
      <h1 className="text-xl font-semibold tracking-tight">Compare</h1>

      <Card>
        <CardHeader
          title="Pick scenarios"
          description="The first pick is the baseline. Differences are computed vs. baseline."
        />
        <CardBody>
          {scenarios.isLoading ? (
            <Skeleton className="h-12" />
          ) : options.length === 0 ? (
            <EmptyState title="No saved scenarios" description="Save scenarios in the Simulator to compare them." />
          ) : (
            <div className="space-y-2">
              {[0, 1, 2, 3, 4].map((i) => (
                <Select
                  key={i}
                  label={i === 0 ? "Baseline" : `Scenario ${i + 1}`}
                  value={picks[i] ?? ""}
                  onChange={(e) => {
                    const next = [...picks];
                    next[i] = e.target.value;
                    setPicks(next.filter(Boolean));
                  }}
                >
                  <option value="">— None —</option>
                  {options.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.industry})
                    </option>
                  ))}
                </Select>
              ))}
              <div className="flex justify-end pt-2">
                <Button onClick={() => compare.mutate()} loading={compare.isPending} disabled={picks.length === 0}>
                  Compare
                </Button>
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      {compare.isError && <ErrorState title="Comparison failed" description={(compare.error as Error).message} />}
      {compare.data && <CompareTable data={compare.data} />}
    </div>
  );
}

function CompareTable({ data }: { data: z.infer<typeof Comparison> }) {
  const baseline = data.rows[0];
  return (
    <Card>
      <CardHeader title="Side by side" description={`Baseline: ${baseline?.scenario_name ?? "—"}`} />
      <CardBody>
        <Table>
          <THead>
            <TR>
              <TH>Metric</TH>
              {data.rows.map((r) => (
                <TH key={r.scenario_id} align="right">
                  {r.scenario_name}
                </TH>
              ))}
            </TR>
          </THead>
          <TBody>
            <TR>
              <TD>Industry</TD>
              {data.rows.map((r) => (
                <TD key={r.scenario_id} align="right">{r.industry}</TD>
              ))}
            </TR>
            <TR>
              <TD>Revenue</TD>
              {data.rows.map((r) => (
                <TD key={r.scenario_id} align="right">{formatMoney(r.revenue, "USD")}</TD>
              ))}
            </TR>
            <TR>
              <TD>Direct costs</TD>
              {data.rows.map((r) => (
                <TD key={r.scenario_id} align="right">{formatMoney(r.direct_costs, "USD")}</TD>
              ))}
            </TR>
            <TR>
              <TD>Gross profit</TD>
              {data.rows.map((r) => (
                <TD key={r.scenario_id} align="right">{formatMoney(r.gross_profit, "USD")}</TD>
              ))}
            </TR>
            <TR>
              <TD>Operating profit</TD>
              {data.rows.map((r) => (
                <TD key={r.scenario_id} align="right">{formatMoney(r.operating_profit, "USD")}</TD>
              ))}
            </TR>
            <TR>
              <TD>Operating margin</TD>
              {data.rows.map((r) => (
                <TD key={r.scenario_id} align="right">{r.operating_margin ? formatPercent(r.operating_margin) : "—"}</TD>
              ))}
            </TR>
            <TR>
              <TD>Closing cash</TD>
              {data.rows.map((r) => (
                <TD key={r.scenario_id} align="right">{formatMoney(r.closing_cash, "USD")}</TD>
              ))}
            </TR>
            <TR>
              <TD>Min projected cash</TD>
              {data.rows.map((r) => (
                <TD key={r.scenario_id} align="right">{formatMoney(r.minimum_projected_cash, "USD")}</TD>
              ))}
            </TR>
          </TBody>
        </Table>

        {data.diffs.length > 0 && (
          <div className="mt-4 text-sm">
            <h3 className="mb-2 text-md font-semibold">Differences vs. baseline</h3>
            <Table>
              <THead>
                <TR>
                  <TH>Scenario</TH>
                  <TH align="right">Revenue Δ</TH>
                  <TH align="right">Operating profit Δ</TH>
                  <TH align="right">Closing cash Δ</TH>
                </TR>
              </THead>
              <TBody>
                {data.diffs.map((d) => {
                  const sid = (d.scenario_id as string) ?? "";
                  const name = data.rows.find((r) => r.scenario_id === sid)?.scenario_name ?? sid;
                  return (
                    <TR key={sid}>
                      <TD>{name}</TD>
                      <TD align="right">
                        {d.revenue_delta ?? "—"}{" "}
                        <span className="text-xs text-ink-subtle">
                          ({d.revenue_delta_pct ? formatPercent(d.revenue_delta_pct as string) : "—"})
                        </span>
                      </TD>
                      <TD align="right">
                        {d.operating_profit_delta ?? "—"}{" "}
                        <span className="text-xs text-ink-subtle">
                          ({d.operating_profit_delta_pct ? formatPercent(d.operating_profit_delta_pct as string) : "—"})
                        </span>
                      </TD>
                      <TD align="right">
                        {d.closing_cash_delta ?? "—"}{" "}
                        <span className="text-xs text-ink-subtle">
                          ({d.closing_cash_delta_pct ? formatPercent(d.closing_cash_delta_pct as string) : "—"})
                        </span>
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          </div>
        )}

        {data.warnings.length > 0 && (
          <ul className="mt-2 text-sm text-warn">
            {data.warnings.map((w, i) => (
              <li key={i}>· {w}</li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}