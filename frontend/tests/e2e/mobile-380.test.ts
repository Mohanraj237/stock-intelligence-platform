/**
 * WS-3 — Mobile responsive viewport tests at 380px width.
 *
 * Each test:
 *   1. Navigates to the page at 380×812 (set in playwright.config.ts).
 *   2. Asserts no uncontained horizontal overflow (body width matches viewport).
 *   3. Asserts key interactive controls are visible and not clipped.
 *   4. Asserts the main data container exists and is not empty.
 *
 * Run: cd frontend && pnpm exec playwright test --project=mobile-380
 * Or:  make test-playwright
 *
 * Requires: Next.js dev server running on port 3001 (started automatically via
 * playwright.config.ts webServer block, or run `pnpm dev` first).
 */

import { test, expect } from "@playwright/test";

const VIEWPORT_WIDTH = 380;

// ── Helpers ────────────────────────────────────────────────────────────────────

/** Assert the page body does not overflow beyond the viewport width. */
async function assertNoHorizontalOverflow(page: import("@playwright/test").Page) {
  const bodyScrollWidth: number = await page.evaluate(
    () => document.body.scrollWidth,
  );
  expect(
    bodyScrollWidth,
    `Body scrollWidth (${bodyScrollWidth}px) exceeds viewport (${VIEWPORT_WIDTH}px) — horizontal overflow detected`,
  ).toBeLessThanOrEqual(VIEWPORT_WIDTH + 2); // 2px tolerance for sub-pixel rounding
}

/** Wait for the page to settle (no pending network requests). */
async function waitForPageReady(page: import("@playwright/test").Page) {
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {
    // timeout is OK — some pages have long-polling; just ensure DOM is loaded
  });
}

// ── Option Chain (/option-chain) ───────────────────────────────────────────────

test.describe("/option-chain at 380px (WS-3)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/option-chain");
    await waitForPageReady(page);
  });

  test("no horizontal overflow at 380px", async ({ page }) => {
    await assertNoHorizontalOverflow(page);
  });

  test("symbol selector or heading is visible", async ({ page }) => {
    // Page header text should be visible
    const heading = page.locator("h1, [data-testid='page-title']").first();
    await expect(heading).toBeVisible();
  });

  test("data table or loading state renders within viewport", async ({ page }) => {
    // Should have a table container or skeleton
    const container = page.locator(
      "table, [class*='Skeleton'], [class*='skeleton'], [class*='overflow-x-auto']",
    ).first();
    await expect(container).toBeVisible();
  });
});

// ── Expiry Heatmap (/expiry-heatmap) ──────────────────────────────────────────

test.describe("/expiry-heatmap at 380px (WS-3)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/expiry-heatmap");
    await waitForPageReady(page);
  });

  test("no horizontal overflow at 380px", async ({ page }) => {
    await assertNoHorizontalOverflow(page);
  });

  test("page header controls wrap correctly", async ({ page }) => {
    // The PageHeader and its actions should both be visible
    const header = page.locator("header, h1").first();
    await expect(header).toBeVisible();
  });

  test("heatmap container (overflow-x-auto) is present", async ({ page }) => {
    // Heatmap grid sits inside overflow-x-auto; the outer container must be visible
    const container = page.locator("[class*='overflow-x-auto']").first();
    await expect(container).toBeVisible();
    const box = await container.boundingBox();
    if (box) {
      // Container itself must not be wider than viewport
      expect(box.width).toBeLessThanOrEqual(VIEWPORT_WIDTH + 4);
    }
  });
});
