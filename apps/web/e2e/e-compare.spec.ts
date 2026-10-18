import { test, expect } from "@playwright/test";

/**
 * Journey E — compare two saved scenarios.
 * Save two scenarios, open Compare, pick both, run.
 */
test("E: compare two scenarios", async ({ page }) => {
  // Save scenario #1
  await page.goto("/simulator");
  await page.getByLabel("Industry").selectOption("retail");
  await page.getByLabel("Scenario name").fill("Compare A");
  await page.getByRole("button", { name: /^Simulate$/ }).click();
  await page.getByRole("button", { name: /^Save$/ }).click();
  await expect(page.getByText("Compare A")).toBeVisible({ timeout: 10_000 });

  // Save scenario #2
  await page.getByLabel("Scenario name").fill("Compare B");
  // Bump expected_units_sold to make a different result
  const expectedSold = page.getByLabel("Expected units sold");
  await expectedSold.fill("999");
  await page.getByRole("button", { name: /^Simulate$/ }).click();
  await page.getByRole("button", { name: /^Save$/ }).click();
  await expect(page.getByText("Compare B")).toBeVisible({ timeout: 10_000 });

  // Compare page
  await page.goto("/compare");
  await expect(page.getByText("Pick scenarios")).toBeVisible();

  // The first two selectors are the baseline and scenario 2.
  const selects = page.locator("select");
  // First option in the dropdown is "— None —". The scenarios are after.
  // Pick the first non-empty option in each.
  const options1 = await selects.nth(0).locator("option").allTextContents();
  const aIndex = options1.findIndex((t) => t.startsWith("Compare A"));
  await selects.nth(0).selectOption({ index: aIndex });
  const options2 = await selects.nth(1).locator("option").allTextContents();
  const bIndex = options2.findIndex((t) => t.startsWith("Compare B"));
  await selects.nth(1).selectOption({ index: bIndex });

  await page.getByRole("button", { name: /^Compare$/ }).click();
  await expect(page.getByText("Side by side")).toBeVisible();
});
