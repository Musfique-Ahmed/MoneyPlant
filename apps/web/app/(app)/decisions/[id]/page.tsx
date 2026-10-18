"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import Link from "next/link";
import { use } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { DecisionReport, Explanation } from "@/lib/schemas";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { formatDateISO } from "@/lib/format";
import {
  ArrowLeft,
  Sparkles,
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Info,
  Lightbulb,
  Printer,
} from "lucide-react";

const STATUS_TONES: Record<string, "ok" | "warn" | "bad" | "info" | "neutral"> = {
  proceed: "ok",
  proceed_with_caution: "info",
  revise: "warn",
  insufficient_data: "neutral",
  reject: "bad",
};

const STATUS_LABELS: Record<string, string> = {
  proceed: "Proceed",
  proceed_with_caution: "Proceed with caution",
  revise: "Revise",
  insufficient_data: "Insufficient data",
  reject: "Reject",
};

const RULE_STATUS_TONES: Record<string, "ok" | "warn" | "bad" | "neutral"> = {
  passed: "ok",
  warning: "warn",
  breached: "bad",
  not_evaluable: "neutral",
};

const RULE_STATUS_LABELS: Record<string, string> = {
  passed: "Passed",
  warning: "Warning",
  breached: "Breached",
  not_evaluable: "Not evaluable",
};

export default function DecisionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [explanation, setExplanation] = useState<z.infer<typeof Explanation> | null>(null);

  const report = useQuery({
    queryKey: ["decision", id],
    queryFn: () => apiGet(`/api/decisions/${id}`, DecisionReport),
  });

  const explain = useMutation({
    mutationFn: () => apiPost(`/api/decisions/${id}/explain`, {}, Explanation),
    onSuccess: (data) => setExplanation(data),
  });

  if (report.isLoading) {
    return <Skeleton className="m-6 h-64" />;
  }
  if (report.isError || !report.data) {
    return (
      <div className="p-6">
        <ErrorState
          title="Could not load decision"
          description={String((report.error as Error)?.message ?? "Unknown error")}
        />
      </div>
    );
  }
  const d = report.data;

  return (
    <div className="space-y-4 px-6 py-6">
      <div className="no-print flex items-center justify-between">
        <Link href="/decisions" className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
          <ArrowLeft size={14} /> Back to decisions
        </Link>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            iconLeft={<Sparkles size={14} />}
            onClick={() => explain.mutate()}
            loading={explain.isPending}
          >
            Explain with LLM
          </Button>
          <Button
            variant="ghost"
            size="sm"
            iconLeft={<Printer size={14} />}
            onClick={() => window.print()}
          >
            Print
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader
          title={
            <div className="flex flex-wrap items-center gap-2">
              <span>{d.question}</span>
              <Badge tone={STATUS_TONES[d.overall_status] ?? "neutral"}>
                {STATUS_LABELS[d.overall_status] ?? d.overall_status}
              </Badge>
              <Badge tone="neutral">Laya: {d.laya_status}</Badge>
            </div>
          }
          description={`Calculated ${formatDateISO(d.calculation_timestamp)} · ${d.assumptions.length} assumption(s) · ${d.caveats.length} caveat(s)`}
        />
        <CardBody>
          <p className="text-base text-ink">{d.recommendation}</p>
        </CardBody>
      </Card>

      {explain.isError && (
        <ErrorState title="Explanation unavailable" description={String((explain.error as Error).message)} />
      )}
      {explanation && <ExplanationBlock explanation={explanation} />}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Binding constraints" description="Hard rules that the verdict rests on." />
          <CardBody>
            {d.binding_constraints.length === 0 ? (
              <p className="text-sm text-ink-muted">No hard rules are binding. This decision does not rest on a hard constraint.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {d.binding_constraints.map((c, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <ShieldAlert size={14} className="mt-0.5 shrink-0 text-bad" />
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Key risks" />
          <CardBody>
            {d.key_risks.length === 0 ? (
              <p className="text-sm text-ink-muted">No additional risks flagged beyond the binding constraints.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {d.key_risks.map((r, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0 text-warn" />
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Rule evaluations"
          description="Every rule the engine ran, with status, threshold, and corrective action when applicable."
        />
        <CardBody>
          {d.rule_evaluations.length === 0 ? (
            <p className="text-sm text-ink-muted">No rules ran. The decision is data-driven only.</p>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Rule</TH>
                  <TH>Severity</TH>
                  <TH>Status</TH>
                  <TH align="right">Actual</TH>
                  <TH align="right">Threshold</TH>
                  <TH>Explanation</TH>
                </TR>
              </THead>
              <TBody>
                {d.rule_evaluations.map((r) => (
                  <TR key={r.rule_id + r.rule_version}>
                    <TD>
                      <div className="font-medium">{r.name}</div>
                      <div className="text-xs text-ink-subtle">{r.rule_id} · v{r.rule_version}</div>
                    </TD>
                    <TD>
                      <Badge tone={r.severity === "hard" ? "bad" : r.severity === "soft" ? "warn" : "neutral"}>
                        {r.severity}
                      </Badge>
                    </TD>
                    <TD>
                      <Badge tone={RULE_STATUS_TONES[r.status] ?? "neutral"}>
                        {RULE_STATUS_LABELS[r.status] ?? r.status}
                      </Badge>
                    </TD>
                    <TD align="right">{r.actual_value ?? "—"}</TD>
                    <TD align="right">{r.threshold ?? "—"}</TD>
                    <TD className="max-w-md text-ink-muted">{r.explanation}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Laya assessments"
          description="Advisory structured assessments. They cannot override a hard rule breach."
        />
        <CardBody>
          {d.laya_assessments.length === 0 ? (
            <p className="text-sm text-ink-muted">Laya was not run for this decision.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {d.laya_assessments.map((a, i) => (
                <li
                  key={i}
                  className="flex items-start justify-between gap-3 rounded border border-line p-2"
                >
                  <div className="min-w-0">
                    <div className="font-medium">{a.question_id}</div>
                    <div className="text-ink-muted">{a.answer_label}</div>
                    <div className="text-xs text-ink-subtle">
                      {a.model_id}
                      {a.answer_score !== null && ` · score ${a.answer_score.toFixed(2)}`}
                      {a.answer_probability !== null && ` · p=${a.answer_probability.toFixed(2)}`}
                    </div>
                    {a.reason && <div className="mt-1 text-xs text-ink-subtle">{a.reason}</div>}
                  </div>
                  <Badge tone={a.status === "ok" ? "info" : "neutral"}>{a.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <InfoList title="Assumptions" items={d.assumptions} icon={<Info size={14} />} />
        <InfoList title="Caveats" items={d.caveats} icon={<AlertTriangle size={14} />} />
        <InfoList
          title="Missing information"
          items={d.missing_information}
          icon={<Lightbulb size={14} />}
        />
      </div>

      {d.business_goal && (
        <p className="text-xs text-ink-subtle">Stated business goal: {d.business_goal}</p>
      )}
    </div>
  );
}

function ExplanationBlock({ explanation }: { explanation: z.infer<typeof Explanation> }) {
  if (explanation.status !== "ok") {
    return (
      <Card>
        <CardHeader title="LLM explanation" />
        <CardBody>
          <ErrorState
            title="LLM explanation unavailable"
            description={explanation.reason ?? "The provider did not return a usable response."}
          />
        </CardBody>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader
        title="LLM explanation"
        description={`Provider: ${explanation.provider} · Model: ${explanation.model} · Mode: ${explanation.mode}`}
      />
      <CardBody>
        {explanation.summary && <p className="mb-3 text-base text-ink">{explanation.summary}</p>}
        {explanation.recommendation && (
          <div className="mb-3">
            <h4 className="text-sm font-semibold text-ink">Recommendation</h4>
            <p className="text-sm text-ink-muted">{explanation.recommendation}</p>
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <InfoList title="Supporting evidence" items={explanation.supporting_evidence} />
          <InfoList title="Key risks (LLM)" items={explanation.key_risks} />
          <InfoList title="Assumptions (LLM)" items={explanation.assumptions} />
          <InfoList title="Alternatives" items={explanation.alternatives} />
          <InfoList title="Next actions" items={explanation.next_actions} />
          <InfoList title="Limitations" items={explanation.limitations} />
          <InfoList title="Missing information (LLM)" items={explanation.missing_information} />
        </div>
        <p className="mt-3 text-xs text-ink-subtle">
          The LLM can only explain. Rule verdicts and binding constraints above are authoritative.
        </p>
      </CardBody>
    </Card>
  );
}

function InfoList({
  title,
  items,
  icon,
}: {
  title: string;
  items: string[];
  icon?: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader title={title} />
      <CardBody>
        {items.length === 0 ? (
          <p className="text-sm text-ink-muted">Nothing listed.</p>
        ) : (
          <ul className="space-y-1 text-sm text-ink-muted">
            {items.map((it, i) => (
              <li key={i} className="flex items-start gap-2">
                {icon ? <span className="mt-0.5 text-ink-subtle">{icon}</span> : null}
                <span>{it}</span>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
