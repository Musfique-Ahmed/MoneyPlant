"use client";

import { X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { z } from "zod";
import { Alert as AlertSchema } from "@/lib/schemas";
import { formatMoney } from "@/lib/format";

interface MonthSidePanelProps {
  open: boolean;
  monthLabel: string | null;
  onClose: () => void;
  currency: string;
  details: {
    revenue: string;
    direct_costs: string;
    operating_expenses: string;
    operating_profit: string;
    cash_inflows: string;
    cash_outflows: string;
    net_cash_movement: string;
    opening_cash: string;
    closing_cash: string;
    cost_by_category: Record<string, string>;
  } | null;
  alertsForMonth: z.infer<typeof AlertSchema>[];
}

function toNumber(s: string | number | null | undefined): number {
  if (s === null || s === undefined || s === "") return 0;
  if (typeof s === "number") return s;
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

export function MonthSidePanel({
  open,
  monthLabel,
  onClose,
  currency,
  details,
  alertsForMonth,
}: MonthSidePanelProps) {
  if (!open) return null;
  return (
    <aside
      role="dialog"
      aria-modal="true"
      aria-label={`Detail for ${monthLabel ?? "selected month"}`}
      className="fixed right-0 top-0 z-40 h-full w-full max-w-md overflow-y-auto border-l border-line bg-surface-raised shadow-elev2"
    >
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <div className="text-md font-semibold text-ink">{monthLabel ?? "Month"}</div>
          <div className="text-xs text-ink-muted">
            Backend-computed metrics. Click any chart marker to drill down.
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          aria-label="Close month detail"
          iconLeft={<X size={14} />}
        >
          Close
        </Button>
      </header>
      <div className="space-y-3 p-4 text-sm">
        {!details ? (
          <p className="text-ink-muted">No breakdown available for this month.</p>
        ) : (
          <>
            <section>
              <h3 className="font-semibold">Money in / out</h3>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 pt-1 tabular-nums">
                <dt className="text-ink-muted">Cash inflows</dt>
                <dd className="text-right">{formatMoney(details.cash_inflows, currency)}</dd>
                <dt className="text-ink-muted">Cash outflows</dt>
                <dd className="text-right">{formatMoney(details.cash_outflows, currency)}</dd>
                <dt className="text-ink-muted">Net cash movement</dt>
                <dd className="text-right">{formatMoney(details.net_cash_movement, currency)}</dd>
                <dt className="text-ink-muted">Opening cash</dt>
                <dd className="text-right">{formatMoney(details.opening_cash, currency)}</dd>
                <dt className="text-ink-muted">Closing cash</dt>
                <dd className="text-right">{formatMoney(details.closing_cash, currency)}</dd>
              </dl>
            </section>
            <section>
              <h3 className="font-semibold">Profit</h3>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 pt-1 tabular-nums">
                <dt className="text-ink-muted">Revenue</dt>
                <dd className="text-right">{formatMoney(details.revenue, currency)}</dd>
                <dt className="text-ink-muted">Direct costs</dt>
                <dd className="text-right">{formatMoney(details.direct_costs, currency)}</dd>
                <dt className="text-ink-muted">Operating expenses</dt>
                <dd className="text-right">{formatMoney(details.operating_expenses, currency)}</dd>
                <dt className="text-ink-muted">Operating profit</dt>
                <dd className="text-right">{formatMoney(details.operating_profit, currency)}</dd>
              </dl>
            </section>
            <section>
              <h3 className="font-semibold">Cost categories</h3>
              <ul className="space-y-1 pt-1">
                {Object.entries(details.cost_by_category).length === 0 ? (
                  <li className="text-ink-muted">None</li>
                ) : (
                  Object.entries(details.cost_by_category)
                    .sort((a, b) => toNumber(b[1]) - toNumber(a[1]))
                    .map(([cat, amt]) => (
                      <li
                        key={cat}
                        className="flex items-center justify-between tabular-nums"
                      >
                        <span className="text-ink-muted">{cat}</span>
                        <span>{formatMoney(amt, currency)}</span>
                      </li>
                    ))
                )}
              </ul>
            </section>
            <section>
              <h3 className="font-semibold">Related alerts</h3>
              {alertsForMonth.length === 0 ? (
                <p className="pt-1 text-ink-muted">No alerts for this month.</p>
              ) : (
                <ul className="space-y-1 pt-1">
                  {alertsForMonth.map((a, i) => (
                    <li
                      key={`${a.code}-${i}`}
                      className="flex items-start gap-2 rounded border border-line p-2"
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
                      <span className="text-ink">{a.message}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </aside>
  );
}