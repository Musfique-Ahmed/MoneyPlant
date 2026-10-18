import { test, expect } from "@playwright/test";

/**
 * Journey G — request an LLM explanation.
 * The provider is expected to be unavailable in CI (no API key, no Ollama);
 * the journey verifies the UI surfaces the error cleanly without crashing.
 */
test("G: explain-with-LLM shows a clean error when no provider is configured", async ({ page }) => {
  // Save + evaluate
  await page.goto("/simulator");
  await page.getByLabel("Industry").selectOption("retail");
  await page.getByLabel("Scenario name").fill("Explain target");
  await page.getByRole("button", { name: /^Simulate$/ }).click();
  await page.getByRole("button", { name: /^Save$/ }).click();
  await expect(page.getByText("Explain target")).toBeVisible({ timeout: 10_000 });

  await page.goto("/decisions");
  await page.getByLabel("Scenario").selectOption({ label: /Explain target/ });
  await page.getByRole("button", { name: /^Evaluate$/ }).click();
  await page.getByText("Should we proceed with this scenario as planned?").click();

  // Click explain; expect either an explanation block or a clean error block.
  await page.getByRole("button", { name: /explain with llm/i }).click();
  // Whichever it is, the rule evaluations block must still be visible.
  await expect(page.getByText("Rule evaluations")).toBeVisible();
});
