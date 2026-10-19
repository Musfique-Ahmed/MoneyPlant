"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import { apiGet } from "@/lib/api";
import { Business, FinancialSummary } from "@/lib/schemas";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Skeleton, EmptyState, ErrorState } from "@/components/ui/States";
import { formatMoney, formatPercent } from "@/lib/format";
import { useWorkspace } from "@/components/WorkspaceContext";
import { AlertsPanel } from "@/components/AlertsPanel";
import { ArrowRight, TrendingUp, Wallet, Banknote, AlertTriangle } from "lucide-react";
import Link from "next/link";

export default function DashboardPage() {
  const { businessId, setBusinessId } = useWorkspace();
  const [selectedId, setSelectedId] = useState<string | null>(businessId);

  const businesses = useQuery({
    queryKey: ["businesses"],
    queryFn: () => apiGet("/api/businesses", z.array(Business)),
  });

  const effectiveId = selectedId ?? businesses.data?.[0]?.id ?? null;
  const summary = useQuery({
    enabled: !!effectiveId,
    queryKey: ["financial-summary", effectiveId],
    queryFn: () => apiGet(`/api/financial-summary?business_id=${effectiveId}`, FinancialSummary),
  });

  if (businesses.isLoading) return <PageSkeleton />;

  if (businesses.isError) {
    return (
      <Page>
        <ErrorState
          title="Could not load businesses"
          description={String((businesses.error as Error)?.message ?? "Unknown error")}
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
            <Link href="/settings" className="text-sm text-accent hover:underline">
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
      }
    >
      {summary.isLoading || !summary.data ? (
        <Skeleton className="h-48" />
      ) : summary.isError ? (
        <ErrorState title="Could not load summary" description={String((summary.error as Error)?.message ?? "")} />
      ) : (
        <SummaryView summary={summary.data} />
      )}

      {summary.data && (
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
      )}
      <div className="mt-4">
        <AlertsPanel />
      </div>
    </Page>
  );
}

function SummaryView({ summary }: { summary: z.infer<typeof FinancialSummary> }) {
  if (summary.is_empty) {
    return (
      <EmptyState
        title="No transactions yet"
        description="Import a CSV to see your revenue, costs, and runway."
        action={
          <Link href="/data" className="text-sm text-accent hover:underline">
            Go to Data
          </Link>
        }
      />
    );
  }
  const c = summary.currency;
  const coverage = summary.data_coverage;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Revenue"
          value={formatMoney(summary.revenue, c)}
          sub={summary.gross_margin ? `${formatPercent(summary.gross_margin)} gross margin` : undefined}
          icon={<TrendingUp size={16} />}
          tone="ok"
        />
        <Stat
          label="Operating profit"
          value={formatMoney(summary.operating_profit, c)}
          sub={summary.operating_margin ? `${formatPercent(summary.operating_margin)} margin` : undefined}
          icon={<Banknote size={16} />}
          tone={Number(summary.operating_profit) < 0 ? "bad" : "ok"}
        />
        <Stat
          label="Closing cash"
          value={formatMoney(summary.closing_cash, c)}
          sub={summary.cash_runway_months ? `~${summary.cash_runway_months} mo runway` : "Runway needs a scenario"}
          icon={<Wallet size={16} />}
          tone={Number(summary.closing_cash) < 0 ? "bad" : "neutral"}
        />
        <Stat
          label="Transactions"
          value={String(summary.transaction_count)}
          sub={`Period ${summary.period_start} → ${summary.period_end_exclusive}`}
          icon={<ArrowRight size={16} />}
          tone="info"
        />
      </div>

      {summary.warnings.length > 0 && (
        <Card>
          <CardHeader title="Warnings" />
          <CardBody>
            <ul className="space-y-1 text-sm text-ink-muted">
              {summary.warnings.map((w, i) => (
                <li key={i} className="flex items-start gap-2">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0 text-warn" />
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader
          title="Data coverage"
          description="What the dashboard could compute from your imported transactions."
        />
        <CardBody>
          <div className="flex flex-wrap gap-2">
            {Object.entries(coverage).map(([k, v]) => (
              <Badge key={k} tone={v ? "ok" : "neutral"}>
                {k}: {v ? "yes" : "no"}
              </Badge>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
  tone?: "ok" | "bad" | "info" | "neutral";
}) {
  const toneColor =
    tone === "ok" ? "text-ok" : tone === "bad" ? "text-bad" : tone === "info" ? "text-info" : "text-ink";
  return (
    <Card>
      <CardBody>
        <div className="flex items-center justify-between text-sm text-ink-muted">
          <span>{label}</span>
          <span className={toneColor}>{icon}</span>
        </div>
        <div className={`mt-2 text-2xl font-semibold tabular-nums ${toneColor}`}>{value}</div>
        {sub && <div className="mt-1 text-xs text-ink-subtle">{sub}</div>}
      </CardBody>
    </Card>
  );
}

function ActionCard({ href, title, description }: { href: string; title: string; description: string }) {
  return (
    <Link href={href}>
      <Card className="hover:border-accent/40">
        <CardBody>
          <div className="flex items-center justify-between">
            <div className="text-md font-semibold">{title}</div>
            <ArrowRight size={16} className="text-ink-muted" />
          </div>
          <p className="mt-1 text-sm text-ink-muted">{description}</p>
        </CardBody>
      </Card>
    </Link>
  );
}

function Page({ children, headerRight }: { children: React.ReactNode; headerRight?: React.ReactNode }) {
  return (
    <div className="px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
        <div>{headerRight}</div>
      </div>
      {children}
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-4 p-6">
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-32" />
      <Skeleton className="h-32" />
    </div>
  );
}