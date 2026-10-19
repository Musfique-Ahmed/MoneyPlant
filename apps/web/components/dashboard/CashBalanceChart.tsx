"use client";

import {
  CartesianGrid,
  Dot,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface CashBalancePoint {
  month_label: string;
  opening_cash: number;
  net_cash_movement: number;
  closing_cash: number;
  is_negative: boolean;
}

/**
 * Closing cash per month with a zero line and a 1-month operating buffer.
 * Months with negative cash get a hatched-pattern dot so the marker is
 * distinguishable in greyscale.
 */
export function CashBalanceChart({
  data,
  currency,
  minBuffer,
  onClickMonth,
  hiddenSeries,
}: {
  data: CashBalancePoint[];
  currency: string;
  minBuffer: number;
  onClickMonth?: (month: string) => void;
  hiddenSeries?: Set<string>;
  onToggleSeries?: (name: string) => void;
}) {
  const isVisible = (s: string) => !hiddenSeries?.has(s);
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart
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
        <ReferenceLine y={0} stroke="rgb(var(--color-line))" strokeWidth={1} />
        {minBuffer > 0 && (
          <ReferenceLine
            y={minBuffer}
            stroke="rgb(var(--color-warn))"
            strokeDasharray="4 4"
            label={{
              value: "1-month buffer",
              fontSize: 10,
              fill: "rgb(var(--color-warn))",
              position: "insideTopLeft",
            }}
          />
        )}
        {isVisible("Closing cash") && (
          <Line
            isAnimationActive={false}
            type="monotone"
            dataKey="closing_cash"
            name="Closing cash"
            stroke="rgb(var(--color-accent))"
            strokeWidth={2}
            dot={({ cx, cy, payload }: { cx?: number; cy?: number; payload?: CashBalancePoint }) => {
              const safeCx = cx ?? 0;
              const safeCy = cy ?? 0;
              if (payload && payload.is_negative) {
                return (
                  <g>
                    <circle
                      cx={safeCx}
                      cy={safeCy}
                      r={5}
                      fill="rgb(var(--color-bad))"
                      stroke="rgb(var(--color-ink))"
                    />
                    <line
                      x1={safeCx - 3}
                      y1={safeCy - 3}
                      x2={safeCx + 3}
                      y2={safeCy + 3}
                      stroke="rgb(var(--color-ink-inverse))"
                      strokeWidth={1}
                    />
                  </g>
                );
              }
              return <Dot cx={safeCx} cy={safeCy} r={3} fill="rgb(var(--color-accent))" />;
            }}
            onClick={(d) => {
              if (
                onClickMonth &&
                d &&
                typeof d === "object" &&
                "month_label" in d
              ) {
                onClickMonth(
                  String((d as { month_label: unknown }).month_label),
                );
              }
            }}
          />
        )}
        {isVisible("Net cash movement") && (
          <Line
            isAnimationActive={false}
            type="monotone"
            dataKey="net_cash_movement"
            name="Net cash movement"
            stroke="rgb(var(--color-info))"
            strokeDasharray="2 3"
            dot={{ r: 2 }}
          />
        )}
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

function tooltip(value: number, currency: string): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  return `${sign}${currency} ${abs.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}