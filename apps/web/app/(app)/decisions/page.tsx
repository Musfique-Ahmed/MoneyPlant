"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import Link from "next/link";
import { apiGet, apiPost } from "@/lib/api";
import { Business, DecisionReport, Scenario } from "@/lib/schemas";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { useWorkspace } from "@/components/WorkspaceContext";
import { Gavel, Sparkles, ScrollText } from "lucide-react";
import { formatDateISO } from "@/lib/format";

const DecisionsList = z.array(DecisionReport);

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

export default function DecisionsPage() {
  const { businessId } = useWorkspace();
  const qc = useQueryClient();
  const [selectedScenario, setSelectedScenario] = useState<string>("");
  const [question, setQuestion] = useState<string>(
    "Should we proceed with this scenario as planned?"
  );
  const [goal, setGoal] = useState<string>("");

  const businesses = useQuery({
    queryKey: ["businesses"],
    queryFn: () => apiGet("/api/businesses", z.array(Business)),
  });
  const effectiveId = businessId ?? businesses.data?.[0]?.id ?? null;

  const decisions = useQuery({
    enabled: !!effectiveId,
    queryKey: ["decisions", effectiveId],
    queryFn: () => apiGet(`/api/decisions?business_id=${effectiveId}`, DecisionsList),
  });

  const scenarios = useQuery({
    enabled: !!effectiveId,
    queryKey: ["scenarios", effectiveId],
    queryFn: () => apiGet(`/api/scenarios?business_id=${effectiveId}`, z.array(Scenario)),
  });

  const evaluate = useMutation({
    mutationFn: () => {
      if (!effectiveId) throw new Error("No business");
      if (!selectedScenario) throw new Error("Pick a scenario to evaluate");
      // Resolve the latest version id for the selected scenario so the
      // backend can load its inputs. `latest_version_id` is mirrored in
      // the Zod Schema.
      const sc = scenarios.data?.find((s) => s.id === selectedScenario);
      if (!sc?.latest_version_id) {
        throw new Error("Selected scenario has no version yet");
      }
      return apiPost(
        "/api/decisions/evaluate",
        {
          business_id: effectiveId,
          scenario_version_id: sc.latest_version_id,
          question: question.trim(),
          context: goal.trim() ? { business_goal: goal.trim() } : {},
        },
        DecisionReport
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["decisions", effectiveId] });
    },
  });

  if (businesses.isLoading) {
    return <Skeleton className="m-6 h-32" />;
  }

  if (!businesses.data || businesses.data.length === 0) {
    return (
      <div className="p-6">
        <EmptyState title="No business yet" description="Create a business before evaluating decisions." />
      </div>
    );
  }

  return (
    <div className="space-y-4 px-6 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Decisions</h1>
        <Badge tone="neutral">
          <ScrollText size={12} /> Rule-first evaluation
        </Badge>
      </div>

      <Card>
        <CardHeader
          title="Evaluate a scenario"
          description="Rules are authoritative. Laya is advisory. The LLM only explains — it does not change the verdict."
        />
        <CardBody>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Select
              label="Scenario"
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
              hint={scenarios.data?.length ? `${scenarios.data.length} saved` : "Save a scenario in the Simulator first"}
            >
              <option value="">— Select a saved scenario —</option>
              {(scenarios.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.industry})
                </option>
              ))}
            </Select>
            <Input
              label="Business goal (optional)"
              placeholder="e.g. keep operating margin above 10%"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            />
            <div className="md:col-span-2">
              <Input
                label="Question for the decision engine"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                hint="Be specific. The engine does not invent context."
              />
            </div>
          </div>

          <div className="mt-3 flex justify-end">
            <Button
              onClick={() => evaluate.mutate()}
              loading={evaluate.isPending}
              disabled={!selectedScenario || !question.trim()}
              iconLeft={<Gavel size={14} />}
            >
              Evaluate
            </Button>
          </div>

          {evaluate.isError && (
            <div className="mt-3">
              <ErrorState title="Evaluation failed" description={String((evaluate.error as Error).message)} />
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Decision history" description="Newest first. Click a row to open the report." />
        <CardBody>
          {decisions.isLoading ? (
            <Skeleton className="h-24" />
          ) : decisions.isError ? (
            <ErrorState title="Could not load decisions" />
          ) : !decisions.data || decisions.data.length === 0 ? (
            <EmptyState
              title="No decisions yet"
              description="Evaluate a scenario to produce your first decision report."
            />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Date</TH>
                  <TH>Question</TH>
                  <TH>Verdict</TH>
                  <TH>Rules</TH>
                  <TH align="right">Recommendation</TH>
                </TR>
              </THead>
              <TBody>
                {decisions.data.map((d) => (
                  <Link key={d.id} href={`/decisions/${d.id}`} className="contents">
                    <TR>
                      <TD className="whitespace-nowrap">{formatDateISO(d.calculation_timestamp)}</TD>
                      <TD className="max-w-md truncate">{d.question}</TD>
                      <TD>
                        <Badge tone={STATUS_TONES[d.overall_status] ?? "neutral"}>
                          {STATUS_LABELS[d.overall_status] ?? d.overall_status}
                        </Badge>
                      </TD>
                      <TD className="text-ink-muted">
                        {d.rule_evaluations.length} eval · {d.binding_constraints.length} binding
                      </TD>
                      <TD align="right" className="max-w-md truncate text-ink-muted">
                        {d.recommendation}
                      </TD>
                    </TR>
                  </Link>
                ))}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
