import { test, expect } from "@playwright/test";

/**
 * Journey I — privacy disclosure + error states.
 * The settings page must show the privacy copy and the live AI provider
 * status table.
 */
test("I: settings page surfaces privacy + provider status", async ({ page }) => {
  await page.goto("/settings");

  await expect(page.getByText("Privacy")).toBeVisible();
  await expect(page.getByText("Local-first by design")).toBeVisible();

  // AI provider status table renders with one row per mode.
  await expect(page.getByRole("columnheader", { name: "Mode" })).toBeVisible();
  await expect(page.getByText("Local (Ollama)")).toBeVisible();
  await expect(page.getByText("OpenAI")).toBeVisible();
  await expect(page.getByText("Anthropic")).toBeVisible();
});
