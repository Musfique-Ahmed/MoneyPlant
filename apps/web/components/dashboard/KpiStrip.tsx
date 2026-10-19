"use client";

import { Banknote, TrendingUp, Wallet, Timer, Receipt } from "lucide-react";
import { Card, CardBody } from "@/components/ui/Card";
import { formatMoney } from "@/lib/format";

type KpiEvidence = {
  currency: string;
  revenue: string;
  total_costs: string;
  operating_profit: string;
  closing_cash: string;
  runway_months: string | null;
  revenue_change_pct: string | null;
  cost_change_pct: string | null;
  profit_change_pct: string | null;
  cash_change_pct: string | null;
};

interface KpiStripProps {
  evidence: KpiEvidence;
}

function _trendTone(value: string | null): "ok" | "bad" | "neutral" {
  if (value === null) return "neutral";
  if (value.startsWith("-")) return "bad";
  return "ok";
}

function _toneClass(tone: "ok" | "bad" | "neutral"): string {
  return tone === "ok" ? "text-ok" : tone === "bad" ? "text-bad" : "text-ink-muted";
}

function _stat({
  label,
  value,
  icon,
  changePct,
  tone,
  sub,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  changePct?: string | null;
  tone: "ok" | "bad" | "neutral";
  sub?: string;
}) {
  const toneText =
    label === "Operating profit" || label === "Closing cash"
      ? tone
      : "neutral";
  return (
    <Card>
      <CardBody>
        <div className="flex items-center justify-between text-sm text-ink-muted">
          <span>{label}</span>
          <span className={_toneClass("neutral")}>{icon}</span>
        </div>
        <div
          className={`mt-2 text-2xl font-semibold tabular-nums ${_toneClass(toneText)}`}
        >
          {value}
        </div>
        <div className="mt-1 flex items-center gap-2 text-xs text-ink-subtle">
          {changePct !== undefined && (
            <span aria-label={`Change ${changePct ?? "0"} percent`}>
              {changePct === null ? "No prior period" : `${changePct} vs prior`}
            </span>
          )}
          {sub && <span>{sub}</span>}
        </div>
      </CardBody>
    </Card>
  );
}

export function KpiStrip({ evidence }: KpiStripProps) {
  const c = evidence.currency;
  const profitTone =
    evidence.operating_profit.trim().startsWith("-") ? "bad" : "ok";
  const cashTone =
    evidence.closing_cash.trim().startsWith("-") ? "bad" : "neutral";
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
      {_stat({
        label: "Revenue",
        value: formatMoney(evidence.revenue, c),
        icon: <TrendingUp size={16} />,
        changePct: evidence.revenue_change_pct,
        tone: _trendTone(evidence.revenue_change_pct),
      })}
      {_stat({
        label: "Operating profit",
        value: formatMoney(evidence.operating_profit, c),
        icon: <Banknote size={16} />,
        changePct: evidence.profit_change_pct,
        tone: profitTone,
      })}
      {_stat({
        label: "Closing cash",
        value: formatMoney(evidence.closing_cash, c),
        icon: <Wallet size={16} />,
        changePct: evidence.cash_change_pct,
        tone: cashTone,
        sub:
          evidence.runway_months === null
            ? "Runway: —"
            : `Runway: ~${evidence.runway_months} mo`,
      })}
      {_stat({
        label: "Total costs",
        value: formatMoney(evidence.total_costs, c),
        icon: <Receipt size={16} />,
        changePct: evidence.cost_change_pct,
        tone: _trendTone(evidence.cost_change_pct),
      })}
    </div>
  );
}
