/*
 * Playwright config for the reports workspace smoke suite (RPT-UI-001).
 *
 * The app serves four subdomain surfaces (see src/middleware.ts); the suite
 * runs against the tenant workspace (default.localhost) which the identity
 * seed creates with the admin sign-in used by the setup project.
 *
 * Local smoke runs reuse an already-running Next.js dev server when one is up
 * (webServer.reuseExistingServer = true off CI); otherwise Playwright boots
 * `pnpm run dev` itself. The default base URL can be overridden with
 * E2E_BASE_URL when the stack runs on another host/port.
 *
 * Projects:
 *   - setup: signs in as the seeded admin (through /signin on the signin
 *     surface), completes mandatory MFA enrollment, and saves the session to
 *     e2e/.auth/admin.json.
 *   - reports-smoke: runs the suite already authenticated via the setup
 *     project's storage state, applied by the spec's own worker-scoped browser
 *     context fixture (the runner's default per-test context cannot be used;
 *     see the spec header).
 *
 * The whole suite must run serially in one worker. Identity rotates the
 * refresh token on every /api/auth/session hydration, and presenting an
 * already-rotated token is treated as token reuse, which revokes the session
 * family. Per-test contexts loaded from the same storage state would present
 * the same token seven times and revoke the family on the second test. The
 * reports smoke spec instead opens ONE worker-scoped context from the stored
 * token and walks the rotation chain sequentially (T0 -> T1 -> ...) across its
 * tests, which is exactly what identity expects.
 */

import { defineConfig } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "http://default.localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  // Serial within a worker: see the header comment on refresh-token rotation.
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  reporter: process.env.CI ? "html" : "list",
  use: {
    baseURL,
    trace: "on-first-retry",
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: "reports-smoke",
      testIgnore: /auth\.setup\.ts/,
      dependencies: ["setup"],
      // NOTE: no `use.storageState` here. The spec opens a single
      // worker-scoped context from e2e/.auth/admin.json so the cookie jar can
      // advance the refresh-token rotation chain across its seven tests.
    },
  ],
  webServer: {
    // Run the DEV server (turbopack). `next start`/`next build` force
    // NODE_ENV=production, which makes applySessionCookie set a `Secure`
    // cookie - and over plain http://localhost Chromium drops Secure cookies,
    // so the rotated token never reaches the context jar and the next page
    // reload presents a stale token (a reuse that revokes the family).
    // Dev mode sets Secure:false, so the rotation propagates correctly.
    command: "pnpm run dev",
    // Readiness probe must use `localhost`: the Node-side check cannot
    // resolve `*.localhost` (only Chromium can). Tests still navigate the
    // tenant surface via baseURL above.
    url: "http://localhost:3000/",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});