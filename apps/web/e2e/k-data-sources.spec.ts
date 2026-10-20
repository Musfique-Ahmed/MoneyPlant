import { test, expect } from "@playwright/test";

/**
 * Journey K — connected data sources.
 *
 * 1. Open the Data page.
 * 2. Confirm the credential-handling banner is visible.
 * 3. Add a file data source pointing at a sample CSV in the allowed
 *    directory.
 * 4. Confirm the source appears with a "Not synced yet" status label.
 * 5. Click "Sync now" and confirm the status becomes OK.
 * 6. Visit the dashboard and confirm the freshness strip reflects the
 *    completed sync.
 */

test("K: connect a data source, sync it, and see the dashboard update", async ({
  page,
}) => {
  await page.goto("/data");

  // The credential-handling banner must be visible before anything else.
  await expect(
    page.getByText(/SQL credentials are stored only as env-var names/i),
  ).toBeVisible();

  // Add-source form: file type is the default, so we just fill name + path.
  const nameField = page.locator('input[placeholder="Daily POS exports"]');
  await expect(nameField).toBeVisible();

  const sourceName = `E2E CSV source ${Date.now()}`;
  await nameField.fill(sourceName);

  const pathField = page.locator(
    'input[placeholder="daily_transactions.xlsx"]',
  );
  await pathField.fill("wholesale_demo.csv");

  await page.getByRole("button", { name: /Create source/i }).click();

  // The new source card appears with an explicit text status label —
  // never colour alone.
  await expect(page.getByText(sourceName)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Not synced yet").first()).toBeVisible();

  // Sync it now and confirm the status flips to "OK".
  const sourceCard = page
    .locator("div")
    .filter({ hasText: sourceName })
    .filter({ has: page.getByRole("button", { name: /^Sync now$/i }) })
    .last();
  await sourceCard.getByRole("button", { name: /^Sync now$/i }).click();

  // The "OK" badge is a text label inside the freshness strip / source row.
  await expect(page.getByText(/^OK$/).first()).toBeVisible({ timeout: 20_000 });

  // Dashboard freshness strip reflects the completed sync.
  await page.goto("/dashboard");
  await expect(page.getByText("Data freshness").first()).toBeVisible();
  await expect(page.getByText(/Last sync:/).first()).toBeVisible();
});
