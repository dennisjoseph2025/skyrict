/*
 * Reports workspace smoke suite (RPT-UI-001).
 *
 * Runs against the Next.js dev server + backend. Identity rotates and
 * invalidates the workspace session cookie on every /api/auth/session
 * hydration, and presenting an already-rotated token is treated as reuse,
 * which revokes the whole session family.
 *
 * The suite runs as ONE test with sequential page.goto() calls so the same
 * page object walks the rotation chain T0 -> T1 -> ... within a single
 * browser context. Splitting into separate tests (even with a shared
 * worker-scoped context) breaks the chain because Playwright does not
 * propagate cookie-jar updates reliably across page lifecycle events in the
 * rotation window.
 */

import {
  expect,
  test as base,
  type BrowserContext,
  type Page,
} from "@playwright/test";

const AUTH_FILE = "e2e/.auth/admin.json";
const WORKSPACE_BASE_URL = process.env.E2E_BASE_URL ?? "http://default.localhost:3000";

const test = base.extend<{ workspacePage: Page }, { workspaceContext: BrowserContext }>({
  workspaceContext: [
    async ({ browser }, use) => {
      const context = await browser.newContext({
        baseURL: WORKSPACE_BASE_URL,
        storageState: AUTH_FILE,
        viewport: { width: 1280, height: 800 },
      });
      await use(context);
      await context.close();
    },
    { scope: "worker" },
  ],
  workspacePage: async ({ workspaceContext }, use) => {
    const page = await workspaceContext.newPage();
    await use(page);
    await page.close();
  },
});

/** Wait for a successful report run result (table with rows, or empty state). */
async function waitForResult(page: Page) {
  await page
    .locator("table")
    .or(page.getByRole("heading", { name: "No rows" }))
    .first()
    .waitFor({ state: "visible", timeout: 20_000 });
}

test("reports workspace smoke: auth and page load", async ({ workspacePage: page }) => {
  // ── workspace listing ────────────────────────────────────────────────
  await test.step("page loads authenticated", async () => {
    await page.goto("/dashboard/erp/reports");

    // The dashboard top bar renders a second h1 ("Business Operations · …"),
    // so match the page heading exactly.
    await expect(
      page.getByRole("heading", { level: 1, name: "Reports", exact: true }),
    ).toBeVisible();

    // Sidebar is present, confirming authentication.
    await expect(
      page.getByRole("link", { name: "Dashboard", exact: true }),
    ).toBeVisible();

    // KPI section is rendered (even if metrics show unavailable).
    await expect(page.getByRole("region", { name: "Report KPIs" })).toBeVisible();
  });
});