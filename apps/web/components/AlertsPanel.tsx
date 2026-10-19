"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { z } from "zod";
import { apiGet } from "@/lib/api";
import { AlertsResponse } from "@/lib/schemas";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Skeleton, EmptyState, ErrorState } from "@/components/ui/States";
import { formatMoney } from "@/lib/format";
import { useWorkspace } from "@/components/WorkspaceContext";

type AlertItem = z.infer<typeof AlertsResponse>["alerts"][number];
type Severity = AlertItem["severity"];

const TONE_BY_SEVERITY: Record<Severity, "bad" | "warn" | "info"> = {
  Critical: "bad",
  Warning: "warn",
  Info: "info",
};

const ICON_BY_SEVERITY: Record<Severity, JSX.Element> = {
  Critical: <AlertTriangle size={14} className="shrink-0 text-bad" aria-hidden />,
  Warning: <AlertTriangle size={14} className="shrink-0 text-warn" aria-hidden />,
  Info: <Info size={14} className="shrink-0 text-info" aria-hidden />,
};

export function AlertsPanel() {
  const { businessId } = useWorkspace();
  const enabled = !!businessId;
  const q = useQuery({
    enabled,
    queryKey: ["alerts", businessId],
    queryFn: () =>
      apiGet(`/api/businesses/${businessId}/alerts`, AlertsResponse),
  });

  if (!enabled) {
    return (
      <Card>
        <CardHeader title="Alerts" description="Pick a business to see alerts." />
        <CardBody>
          <EmptyState title="No business selected" />
        </CardBody>
      </Card>
    );
  }
  if (q.isLoading || !q.data) {
    return (
      <Card>
        <CardHeader title="Alerts" />
        <CardBody>
          <Skeleton className="h-16" />
        </CardBody>
      </Card>
    );
  }
  if (q.isError) {
    return (
      <Card>
        <CardHeader title="Alerts" />
        <CardBody>
          <ErrorState title="Could not load alerts" description={String(q.error)} />
        </CardBody>
      </Card>
    );
  }

  const data = q.data;
  const alerts = data.alerts;
  return (
    <Card>
      <CardHeader
        title="Alerts"
        description={
          alerts.length === 0
            ? `All clear over ${data.horizon_months} month(s). No thresholds broken.`
            : `${alerts.length} deterministic alert(s) over ${data.horizon_months} month(s).`
        }
      />
      <CardBody>
        {alerts.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-ok">
            <CheckCircle2 size={16} aria-hidden />
            <span>No alerts. Cash looks within normal bounds.</span>
          </div>
        ) : (
          <ul className="space-y-2" aria-label="Cash-flow alerts">
            {alerts.map((a, idx) => (
              <li
                key={`${a.code}-${a.month ?? "period"}-${idx}`}
                className="flex items-start gap-3 rounded-md border border-line p-3"
                data-testid="alert-item"
              >
                {ICON_BY_SEVERITY[a.severity]}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={TONE_BY_SEVERITY[a.severity]}>{a.severity}</Badge>
                    <code className="rounded bg-surface-sunken px-1 py-0.5 text-2xs">
                      {a.code}
                    </code>
                    {a.month !== null && (
                      <span className="text-xs text-ink-subtle">month {a.month}</span>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-ink">{a.message}</p>
                  <p className="mt-1 text-2xs text-ink-subtle">
                    Currency: {data.currency}
                    {typeof a.evidence?.closing_cash === "string"
                      ? ` · last closing: ${a.evidence.closing_cash}`
                      : null}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-2xs text-ink-subtle">{data.note}</p>
      </CardBody>
    </Card>
  );
}

// Re-exported for unit tests that don't need to navigate the workspace context.
export const _internals = { formatMoney };
