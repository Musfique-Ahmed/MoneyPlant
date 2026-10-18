import { test, expect } from "@playwright/test";

/**
 * Journey D — save a scenario and see it in the saved list.
 * Run, then Save, then verify the saved list updates.
 */
test("D: save a scenario and see it in the list", async ({ page }) => {
  await page.goto("/simulator");
  await page.getByLabel("Industry").selectOption("manufacturing");
  await page.getByLabel("Scenario name").fill("Save me");

  await page.getByRole("button", { name: /^Simulate$/ }).click();
  await expect(page.getByText("Revenue")).toBeVisible();

  // Save becomes enabled only after a simulation has run.
  await page.getByRole("button", { name: /^Save$/ }).click();

  await expect(page.getByText("Save me")).toBeVisible({ timeout: 10_000 });
});
