/**
 * Money and number formatting helpers. The backend is authoritative for
 * math; the frontend only formats.
 */

import { z } from "zod";

export const DecimalString = z.string().regex(/^-?\d+(\.\d+)?$/, "Expected decimal string");
export const NonEmptyString = z.string().min(1);

export const Money = z.object({
  amount: DecimalString,
  currency: z.enum(["USD", "EUR", "GBP", "JPY", "INR", "CAD", "AUD"]).default("USD"),
});
export type MoneyT = z.infer<typeof Money>;

const CURRENCY_FRACTION_DIGITS: Record<string, number> = {
  USD: 2,
  EUR: 2,
  GBP: 2,
  JPY: 0,
  INR: 2,
  CAD: 2,
  AUD: 2,
};

export function formatMoney(value: string | number | null | undefined, currency = "USD"): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  const digits = CURRENCY_FRACTION_DIGITS[currency] ?? 2;
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  return `${sign}${currency} ${abs.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function formatPercent(value: string | number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

export function formatNumber(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

export function formatDateISO(d: string | Date | null | undefined): string {
  if (!d) return "—";
  const date = typeof d === "string" ? new Date(d) : d;
  if (Number.isNaN(date.getTime())) return "—";
  return date.toISOString().slice(0, 10);
}
