"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleDollarSign, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { z } from "zod";
import { apiGet } from "@/lib/api";
import { FinancingOptionsResponse } from "@/lib/schemas";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Skeleton, EmptyState, ErrorState } from "@/components/ui/States";
import { formatMoney, formatPercent } from "@/lib/format";
import { useWorkspace } from "@/components/WorkspaceContext";

type Match = z.infer<typeof FinancingOptionsResponse>["matches"][number];

const TONE_BY_LABEL: Record<Match["label"], "ok" | "warn" | "bad"> = {
  recommended: "ok",
  possible: "warn",
  not_recommended: "bad",
};

const ICON_BY_LABEL: Record<Match["label"], JSX.Element> = {
  recommended: <ShieldCheck size={14} className="shrink-0 text-ok" aria-hidden />,
  possible: <TriangleAlert size={14} className="shrink-0 text-warn" aria-hidden />,
  not_recommended: <ShieldAlert size={14} className="shrink-0 text-bad" aria-hidden />,
};

const DISCLAIMER =
  "Illustrative products. Not a credit decision. SYNTHETIC catalog — not real lender offers.";

export function FinancingPanel() {
  const { businessId } = useWorkspace();
  const enabled = !!businessId;
  const q = useQuery({
    enabled,
    queryKey: ["financing", businessId],
    queryFn: () =>
      apiGet(`/api/businesses/${businessId}/financing-options`, FinancingOptionsResponse),
  });

  if (!enabled) {
    return (
      <Card>
        <CardHeader title="Financing options" description="Pick a business to see financing matches." />
        <CardBody>
          <EmptyState title="No business selected" />
        </CardBody>
      </Card>
    );
  }
  if (q.isLoading || !q.data) {
    return (
      <Card>
        <CardHeader title="Financing options" />
        <CardBody>
          <Skeleton className="h-32" />
        </CardBody>
      </Card>
    );
  }
  if (q.isError) {
    return (
      <Card>
        <CardHeader title="Financing options" />
        <CardBody>
          <ErrorState
            title="Could not load financing options"
            description={String(q.error)}
          />
        </CardBody>
      </Card>
    );
  }

  const data = q.data;
  const c = data.currency;
  const nfn = data.no_financing_needed;

  return (
    <div className="space-y-4" data-testid="financing-panel">
      <Card>
        <CardHeader
          title="Financing options"
          description={
            nfn
              ? "No financing needed at this time."
              : `${data.matches.length} match(es) against a synthetic catalog.`
          }
          actions={
            <Badge tone="accent" aria-label="Synthetic catalog">
              <CircleDollarSign size={12} />
              <span className="ml-1">SYNTHETIC catalog</span>
            </Badge>
          }
        />
        <CardBody>
          <p className="mb-3 text-2xs text-warn" role="note" aria-label="Disclaimer">
            {DISCLAIMER}
          </p>
          <div className="mb-3 grid grid-cols-1 gap-2 text-sm md:grid-cols-3">
            <Field
              label="Funding need"
              value={formatMoney(data.funding_need, c)}
            />
            <Field
              label="Minimum projected cash"
              value={formatMoney(data.minimum_projected_cash, c)}
            />
            <Field
              label="Avg monthly revenue"
              value={formatMoney(data.avg_monthly_revenue, c)}
            />
          </div>

          {nfn ? (
            <div className="rounded-md border border-line bg-surface-sunken p-3 text-sm">
              <Badge tone="ok">No financing needed</Badge>
              <p className="mt-2 text-ink-muted">{nfn.reason}</p>
            </div>
          ) : (
            <ul className="space-y-3" aria-label="Financing matches">
              {data.matches.map((m) => (
                <li
                  key={m.product_id}
                  className="rounded-md border border-line p-3"
                  data-testid="financing-match"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {ICON_BY_LABEL[m.label]}
                    <Badge tone={TONE_BY_LABEL[m.label]}>{m.label.replace("_", " ")}</Badge>
                    <span className="font-semibold">{m.product_name}</span>
                    <span className="text-xs text-ink-subtle">({m.product_type})</span>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-ink-muted md:grid-cols-4">
                    <Field
                      label="Requested"
                      value={formatMoney(m.requested_amount, c)}
                    />
                    <Field
                      label="Term"
                      value={`${m.term_months} mo`}
                    />
                    <Field
                      label="Indicative APR"
                      value={formatPercent(m.indicative_annual_rate, 2)}
                    />
                    <Field
                      label="Monthly repayment"
                      value={formatMoney(m.monthly_repayment, c)}
                    />
                  </div>
                  {m.dscr && (
                    <p className="mt-1 text-xs text-ink-subtle">
                      DSCR: <span className="tabular-nums">{m.dscr}</span>
                    </p>
                  )}
                  {m.fit_reasons.length > 0 && (
                    <p className="mt-1 text-xs text-ink-muted">
                      Met: {m.fit_reasons.join(", ")}
                    </p>
                  )}
                  {m.unmet_criteria.length > 0 && (
                    <p className="mt-1 text-xs text-bad">
                      Not met: {m.unmet_criteria.join("; ")}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
      <p className="text-2xs text-ink-subtle">{data.note}</p>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-2xs uppercase tracking-wide text-ink-subtle">{label}</div>
      <div className="tabular-nums">{value}</div>
    </div>
  );
}
