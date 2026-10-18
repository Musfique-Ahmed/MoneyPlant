import { test, expect } from "@playwright/test";

/**
 * Journey F — evaluate a decision.
 * Save a scenario, evaluate it, see the report.
 */
test("F: evaluate a decision and open the report", async ({ page }) => {
  // Save a scenario first.
  await page.goto("/simulator");
  await page.getByLabel("Industry").selectOption("retail");
  await page.getByLabel("Scenario name").fill("Decision target");
  await page.getByRole("button", { name: /^Simulate$/ }).click();
  await page.getByRole("button", { name: /^Save$/ }).click();
  await expect(page.getByText("Decision target")).toBeVisible({ timeout: 10_000 });

  // Decisions page
  await page.goto("/decisions");
  await expect(page.getByText("Evaluate a scenario")).toBeVisible();

  await page.getByLabel("Scenario").selectOption({ label: /Decision target/ });
  await page.getByRole("button", { name: /^Evaluate$/ }).click();

  // Report row appears in history.
  await expect(page.getByText("Decision history")).toBeVisible();
  await expect(page.getByText("Should we proceed with this scenario as planned?")).toBeVisible({
    timeout: 10_000,
  });

  // Open the report.
  await page.getByText("Should we proceed with this scenario as planned?").click();
  await expect(page.getByText("Rule evaluations")).toBeVisible();
  await expect(page.getByText("Binding constraints")).toBeVisible();
});
