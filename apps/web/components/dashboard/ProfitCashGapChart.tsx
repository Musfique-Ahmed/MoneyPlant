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

export interface ProfitCashGapPoint {
  month_label: string;
  operating_profit: number;
  net_cash_movement: number;
  gap: number;
}

export function ProfitCashGapChart({
  data,
  currency,
  hiddenSeries,
  onClickMonth,
}: {
  data: ProfitCashGapPoint[];
  currency: string;
  hiddenSeries?: Set<string>;
  onClickMonth?: (m: string) => void;
}) {
  const isVisible = (s: string) => !hiddenSeries?.has(s);
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart
        data={data}
        margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
        onClick={(e) => {
          if (e && (e as { activeLabel?: unknown }).activeLabel && onClickMonth) {
            onClickMonth(String((e as { activeLabel?: unknown }).activeLabel));
          }
        }}
      >
        <CartesianGrid stroke="rgb(var(--color-line))" strokeDasharray="3 3" />
        <XAxis dataKey="month_label" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip
          formatter={(v: number) => tooltip(v, currency)}
          contentStyle={tooltipStyle}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {isVisible("Profit–cash gap") && (
          <Bar dataKey="gap" name="Profit–cash gap">
            {data.map((d, i) => (
              <Cell
                key={i}
                fill={
                  d.gap >= 0
                    ? "rgb(var(--color-warn))"
                    : "rgb(var(--color-info))"
                }
              />
            ))}
          </Bar>
        )}
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