"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface CompareMetric {
  metric: string;
  baseline: number;
  alt: number;
}

export function ScenarioCompareChart({
  data,
  currency,
}: {
  data: CompareMetric[];
  currency: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid stroke="rgb(var(--color-line))" strokeDasharray="3 3" />
        <XAxis dataKey="metric" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip
          formatter={(v: number) => tooltip(v, currency)}
          contentStyle={tooltipStyle}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="baseline" name="Baseline">
          {data.map((d, i) => (
            <Cell key={i} fill="rgb(var(--color-info))" />
          ))}
        </Bar>
        <Bar dataKey="alt" name="Alt">
          {data.map((d, i) => (
            <Cell key={i} fill="rgb(var(--color-accent))" />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

const tooltipStyle = {
  background: "rgb(var(--color-surface-raised))",
  border: "1px solid rgb(var(--color-line))",
  borderRadius: 6,
  fontSize: 12,
};

function tooltip(value: number, currency: string): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  return `${sign}${currency} ${abs.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}