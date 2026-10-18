import { test, expect } from "@playwright/test";

/**
 * Journey A — first-run.
 * The user lands on the dashboard with no businesses, follows the
 * "create your first business" affordance, and ends with a populated dashboard.
 */
test("A: first-run creates a business and lands on dashboard", async ({ page }) => {
  await page.goto("/dashboard");
  // Empty state visible.
  await expect(page.getByText("No business yet")).toBeVisible();

  // Follow the empty-state link to /settings.
  await page.getByRole("link", { name: /create a business/i }).click();
  await expect(page).toHaveURL(/\/settings/);

  // Open the "New business" form and create a retail workspace.
  await page.getByRole("button", { name: /new business/i }).click();
  await page.getByLabel("Name").fill("Playwright Retail");
  await page.getByLabel("Industry").selectOption("retail");
  await page.getByLabel("Currency").selectOption("USD");
  await page.getByLabel("Minimum cash reserve").fill("0");
  await page.getByLabel("Target operating margin").fill("0.1");
  await page.getByRole("button", { name: "Create" }).click();

  // Return to dashboard — the new business is the active workspace.
  await page.goto("/dashboard");
  await expect(page.getByText("No business yet")).not.toBeVisible();
});
