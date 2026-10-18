import { test, expect } from "@playwright/test";
import path from "node:path";

/**
 * Journey B — import CSV.
 * Drop a CSV, confirm the suggested mapping, commit, see the
 * "X of Y rows" line in the recent imports list.
 */
test("B: import a CSV end-to-end", async ({ page }) => {
  await page.goto("/data");

  // The file input is hidden inside the dropzone label; set it via the input element.
  const csvPath = path.resolve(__dirname, "..", "..", "..", "sample_data", "retail_demo.csv");
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(csvPath);

  // Preview renders: the headers table appears.
  await expect(page.getByRole("columnheader", { name: "Header" })).toBeVisible();

  // Commit
  await page.getByRole("button", { name: /commit/i }).click();

  // Recent imports list updates.
  await expect(page.getByText(/rows · committed/)).toBeVisible({ timeout: 10_000 });
});
