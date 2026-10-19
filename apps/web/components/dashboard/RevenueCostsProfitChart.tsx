"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface RevenueCostsProfitPoint {
  month_label: string;
  revenue: number;       // number, NOT string. The frontend parses; the backend stays Decimal.
  total_costs: number;
  operating_profit: number;
}

export function RevenueCostsProfitChart({
  data,
  currency,
  hiddenSeries,
  onClickMonth,
  onToggleSeries,
}: {
  data: RevenueCostsProfitPoint[];
  currency: string;
  hiddenSeries?: Set<string>;
  onClickMonth?: (month: string) => void;
  onToggleSeries?: (name: string) => void;
}) {
  const seriesVisible = (name: string) => !hiddenSeries?.has(name);
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart
        data={data}
        margin={{ top: 10, right: 16, left: 0, bottom: 8 }}
        onClick={(e) => {
          if (e && e.activeLabel && onClickMonth) onClickMonth(String(e.activeLabel));
        }}
      >
        <CartesianGrid stroke="rgb(var(--color-line))" strokeDasharray="3 3" />
        <XAxis dataKey="month_label" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip
          formatter={(v: number) => formatTooltip(v, currency)}
          contentStyle={tooltipStyle}
          labelStyle={tooltipLabelStyle}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} onClick={(o) => onToggleSeries?.(String(o.value ?? ""))} />
        {seriesVisible("Revenue") && (
          <Bar dataKey="revenue" name="Revenue" fill="rgb(var(--color-ok))" />
        )}
        {seriesVisible("Total costs") && (
          <Bar dataKey="total_costs" name="Total costs" fill="rgb(var(--color-warn))" />
        )}
        {seriesVisible("Operating profit") && (
          <Line
            type="monotone"
            dataKey="operating_profit"
            name="Operating profit"
            stroke="rgb(var(--color-accent))"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

const tooltipStyle = {
  background: "rgb(var(--color-surface-raised))",
  border: "1px solid rgb(var(--color-line))",
  borderRadius: 6,
  fontSize: 12,
};

const tooltipLabelStyle = {
  color: "rgb(var(--color-ink))",
  fontWeight: 600 as const,
};

function formatTooltip(value: number, currency: string): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  return `${sign}${currency} ${abs.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}
