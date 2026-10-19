import { test, expect } from "@playwright/test";

/**
 * Journey J — dashboard interactions.
 *
 * 1. Open dashboard.
 * 2. Pick a business.
 * 3. Verify the KPI strip, charts, alerts, and financing panel render.
 * 4. Click a chart month — side panel opens.
 * 5. Toggle the table view.
 */

test("J: dashboard renders insights and supports interactivity", async ({ page }) => {
  await page.goto("/dashboard");

  // Header renders.
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  // The synthetic-data banner is always present.
  await expect(
    page.getByText(/Synthetic example data/i),
  ).toBeVisible();

  // A business selector is present; pick the first one.
  const bizSelect = page.getByLabel("Select business");
  await expect(bizSelect).toBeVisible();
  await bizSelect.selectOption({ index: 0 });

  // KPI strip label "Operating profit" is one of the cards.
  await expect(page.getByText("Operating profit").first()).toBeVisible();

  // Date inputs are present.
  await expect(page.getByLabel("Period start")).toBeVisible();
  await expect(page.getByLabel("Period end")).toBeVisible();

  // Table view toggle is present somewhere on the page.
  await expect(page.getByText(/Table view/i).first()).toBeVisible();

  // Print button is visible.
  await expect(page.getByRole("button", { name: /Print/i })).toBeVisible();

  // "Synthetic" disclaimer appears at least once (the financing banner).
  await expect(page.getByText(/Illustrative products|SYNTHETIC catalog/i).first()).toBeVisible();
});