import { describe, expect, it } from "vitest";
import { formatMoney, formatPercent, formatDateISO, formatNumber } from "./format";

describe("formatMoney", () => {
  it("formats USD with two decimals", () => {
    expect(formatMoney("1234.5", "USD")).toBe("USD 1,234.50");
    expect(formatMoney("0", "USD")).toBe("USD 0.00");
    expect(formatMoney("-12.5", "USD")).toBe("-USD 12.50");
  });

  it("formats JPY with zero decimals", () => {
    expect(formatMoney("1234", "JPY")).toBe("JPY 1,234");
    expect(formatMoney("1234.7", "JPY")).toBe("JPY 1,235");
  });

  it("returns em-dash for null/empty/non-finite", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(undefined)).toBe("—");
    expect(formatMoney("")).toBe("—");
    expect(formatMoney("not a number")).toBe("—");
  });
});

describe("formatPercent", () => {
  it("formats a decimal ratio as percent", () => {
    expect(formatPercent("0.1234", 1)).toBe("12.3%");
    expect(formatPercent("0.5")).toBe("50.0%");
    expect(formatPercent("1")).toBe("100.0%");
  });

  it("returns em-dash for null/empty", () => {
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
  });
});

describe("formatDateISO", () => {
  it("returns YYYY-MM-DD", () => {
    expect(formatDateISO("2026-01-05T10:00:00Z")).toBe("2026-01-05");
    expect(formatDateISO(new Date("2026-12-31T00:00:00Z"))).toBe("2026-12-31");
  });

  it("returns em-dash for invalid", () => {
    expect(formatDateISO(null)).toBe("—");
    expect(formatDateISO("not a date")).toBe("—");
  });
});

describe("formatNumber", () => {
  it("formats with thousands separators", () => {
    expect(formatNumber("1234.5678")).toBe("1,234.5678");
  });
});
