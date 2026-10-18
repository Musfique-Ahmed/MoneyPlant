import { test, expect } from "@playwright/test";

/**
 * Journey C — run a scenario and see the result.
 * Pick an industry, change one input, click Simulate, see the
 * result panel update with numbers.
 */
test("C: simulator renders a result", async ({ page }) => {
  await page.goto("/simulator");

  // Industry select + Scenario name + the dynamic field grid render.
  await expect(page.getByLabel("Industry")).toBeVisible();
  await page.getByLabel("Industry").selectOption("retail");
  await page.getByLabel("Scenario name").fill("Playwright retail");

  // Run.
  await page.getByRole("button", { name: /^Simulate$/ }).click();

  // The result panel updates with Revenue row.
  await expect(page.getByText("Revenue")).toBeVisible();
  await expect(page.getByText("Direct costs")).toBeVisible();
  await expect(page.getByText("Operating profit")).toBeVisible();
});
