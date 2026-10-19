"use client";

import { ReactNode } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import type { DashboardVisualT } from "@/lib/schemas";

/**
 * Visual card layout: title, visual, then a deterministic
 * interpretation block (what/why) following the engine's output exactly.
 *
 * The frontend never invents a number. Every figure you see in the
 * interpretation comes from the matching ``DashboardVisual`` payload.
 */

interface InsightCardProps {
  visual: DashboardVisualT;
  children: ReactNode;
  tableView?: ReactNode;
  actions?: ReactNode;
  defaultCollapsed?: boolean;
  a11ySummary?: string; // optional screen-reader summary
  onControlsToggle?: (next: boolean) => void;
}

export function InsightCard({
  visual,
  children,
  tableView,
  actions,
  a11ySummary,
  onControlsToggle,
}: InsightCardProps) {
  return (
    <Card className="data-[view=chart]:block" aria-labelledby={`visual-${visual.visual_id}-title`}>
      <CardHeader
        title={
          <span id={`visual-${visual.visual_id}-title`}>{visual.title}</span>
        }
        description={visual.what_it_shows}
        actions={actions}
      />
      <CardBody className="space-y-3">
        <div>{children}</div>
        <div
          className="rounded-md border border-line bg-surface-sunken p-3 text-sm"
          role="region"
          aria-label={`Interpretation for ${visual.title}`}
        >
          <div className="font-semibold text-ink">What to notice</div>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-ink-muted">
            {visual.what_to_notice.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
          <div className="mt-2 font-semibold text-ink">Why it matters</div>
          <p className="mt-1 text-ink-muted">{visual.why_it_matters}</p>
        </div>
        {tableView && (
          <details
            className="rounded-md border border-line bg-surface-sunken"
            onToggle={(e) => onControlsToggle?.((e.target as HTMLDetailsElement).open)}
          >
            <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium text-ink">
              <span className="mr-2 inline-flex items-center">
                <ChevronDown size={14} aria-hidden className="group-open:hidden" />
                <ChevronUp size={14} aria-hidden className="group-open:inline-flex hidden" />
              </span>
              Table view
            </summary>
            <div className="border-t border-line p-3">{tableView}</div>
          </details>
        )}
        {a11ySummary && (
          <p className="sr-only" aria-live="polite">
            {a11ySummary}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

interface AccessibleChartProps {
  children: ReactNode;
  title: string;
  summary: string;
}

export function AccessibleChart({ children, title, summary }: AccessibleChartProps) {
  return (
    <figure className="rounded-md border border-line" aria-label={title}>
      <figcaption className="sr-only">{summary}</figcaption>
      {children}
    </figure>
  );
}
