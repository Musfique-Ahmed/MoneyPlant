import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for MoneyPlant end-to-end journeys.
 *
 * The web app proxies /api/* to the FastAPI backend; the BASE_URL
 * below is the Next.js dev server. The backend is expected to be
 * running on BACKEND_URL.
 */
const PORT = Number(process.env.PORT ?? 3000);
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // shared backend DB; serial is safer.
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
