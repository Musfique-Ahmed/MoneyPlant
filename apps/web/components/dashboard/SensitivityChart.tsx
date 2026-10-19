"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface SensitivitySeries {
  axis: string;
  multipliers: string[];   // e.g. ["-0.25", "-0.10", "0", "0.10", "0.25"]
  operating_profit: number[];
}

/**
 * One-at-a-time deterministic sensitivity. The same multiplier must be on the X-axis
 * for every line so visual comparison is meaningful.
 */
export function SensitivityChart({ series }: { series: SensitivitySeries[] }) {
  if (series.length === 0) return null;
  const multipliers = series[0]!.multipliers;
  const data = multipliers.map((m, i) => {
    const row: Record<string, number | string> = { multiplier: m };
    for (const s of series) {
      row[s.axis] = s.operating_profit[i] ?? 0;
    }
    return row;
  });
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid stroke="rgb(var(--color-line))" strokeDasharray="3 3" />
        <XAxis dataKey="multiplier" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s) => (
          <Line
            key={s.axis}
            type="monotone"
            dataKey={s.axis}
            stroke="rgb(var(--color-accent))"
            dot={{ r: 3 }}
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

const tooltipStyle = {
  background: "rgb(var(--color-surface-raised))",
  border: "1px solid rgb(var(--color-line))",
  borderRadius: 6,
  fontSize: 12,
};