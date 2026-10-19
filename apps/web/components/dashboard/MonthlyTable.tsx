"use client";

import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { formatMoney } from "@/lib/format";

export interface MonthlyTableRow {
  month_label: string;
  revenue: string;
  total_costs: string;
  operating_profit: string;
  opening_cash: string;
  net_cash_movement: string;
  closing_cash: string;
}

export function MonthlyTable({
  rows,
  currency,
}: {
  rows: MonthlyTableRow[];
  currency: string;
}) {
  return (
    <Table>
      <THead>
        <TR>
          <TH>Month</TH>
          <TH align="right">Revenue</TH>
          <TH align="right">Total costs</TH>
          <TH align="right">Operating profit</TH>
          <TH align="right">Net cash movement</TH>
          <TH align="right">Closing cash</TH>
        </TR>
      </THead>
      <TBody>
        {rows.map((r) => (
          <TR key={r.month_label}>
            <TD>{r.month_label}</TD>
            <TD align="right">{formatMoney(r.revenue, currency)}</TD>
            <TD align="right">{formatMoney(r.total_costs, currency)}</TD>
            <TD align="right">{formatMoney(r.operating_profit, currency)}</TD>
            <TD align="right">{formatMoney(r.net_cash_movement, currency)}</TD>
            <TD align="right">{formatMoney(r.closing_cash, currency)}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}