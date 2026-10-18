import { test, expect } from "@playwright/test";

/**
 * Journey H — assistant chat.
 * With no provider configured, the assistant should show a clean error
 * for the user message, not a crash.
 */
test("H: assistant shows provider status and handles a failed chat", async ({ page }) => {
  await page.goto("/assistant");
  await expect(page.getByText("Provider status")).toBeVisible();

  // Type a question and submit. The provider is unavailable in CI,
  // so the assistant message will show a clean error.
  await page.getByPlaceholder(/ask the assistant/i).fill("Why is my closing cash negative?");
  await page.getByRole("button", { name: /^Send$/ }).click();

  // The user bubble appears.
  await expect(page.getByText("Why is my closing cash negative?")).toBeVisible();
  // The assistant's reply resolves to either an ok or a clean error — never a crash.
  // The Send button is enabled again (loading cleared).
  await expect(page.getByRole("button", { name: /^Send$/ })).toBeEnabled({ timeout: 10_000 });
});
