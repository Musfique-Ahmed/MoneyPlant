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

export interface CostCategory {
  category: string;
  amount: number;
}

export function CostBreakdownChart({
  data,
  currency,
}: {
  data: CostCategory[];
  currency: string;
}) {
  const total = data.reduce((acc, d) => acc + d.amount, 0);
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 28)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
      >
        <CartesianGrid stroke="rgb(var(--color-line))" strokeDasharray="3 3" />
        <XAxis type="number" tick={{ fontSize: 11 }} />
        <YAxis
          type="category"
          dataKey="category"
          tick={{ fontSize: 11 }}
          width={120}
        />
        <Tooltip
          formatter={(v: number) => tooltip(v, currency, total)}
          contentStyle={tooltipStyle}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="amount" name="Amount">
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

function tooltip(value: number, currency: string, total: number): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const pct = total > 0 ? ((value / total) * 100).toFixed(1) + "%" : "0%";
  return `${sign}${currency} ${abs.toLocaleString("en-US", { maximumFractionDigits: 2 })} · ${pct} of total`;
}