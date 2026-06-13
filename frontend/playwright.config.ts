import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for Phase 3 mobile responsive tests (WS-3).
 * Tests run against a locally started Next.js dev server.
 *
 * Run: cd frontend && pnpm exec playwright test
 * Or via Makefile: make test-playwright
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3001",
    headless: true,
    screenshot: "only-on-failure",
  },
  // Only Chromium needed for these structural layout tests
  projects: [
    {
      name: "mobile-380",
      use: {
        ...devices["iPhone SE"],  // 375×667, closest to 380px
        viewport: { width: 380, height: 812 },
      },
    },
  ],
  // Start Next.js dev server if not already running
  webServer: {
    command: "pnpm dev",
    port: 3001,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
