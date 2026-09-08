/*
 * Playwright auth setup for the reports workspace smoke suite.
 *
 * Signs in as the seeded admin (admin@skyrict.io / Admin123! by default,
 * overridable via E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD) and completes the
 * mandatory MFA enrollment by capturing the TOTP secret from the browser's
 * setup-MFA API response. Saves the authenticated storage state so the
 * suite's tests start logged in.
 *
 * The first run takes the enrollment path (/setup-mfa). If the admin already
 * has MFA enabled, the challenge path is taken instead and requires
 * E2E_TOTP_SECRET.
 */

import { readFileSync, writeFileSync } from "node:fs";

import { expect, type Page, test as setup } from "@playwright/test";

import { totp } from "./helpers/totp";

export const AUTH_FILE = "e2e/.auth/admin.json";
/**
 * Persisted after the first enrollment so later runs can serve the challenge
 * path without the operator knowing the server-generated TOTP secret. The
 * whole directory is gitignored.
 */
const TOTP_SECRET_FILE = "e2e/.auth/totp-secret";
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@skyrict.io";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "Admin123!";

/** The admin's enrolled TOTP secret: env override wins, else the persisted file. */
function readEnrolledSecret(): string {
  const fromEnv = process.env.E2E_TOTP_SECRET;
  if (fromEnv) return fromEnv;
  try {
    return readFileSync(TOTP_SECRET_FILE, "utf8").trim();
  } catch {
    return "";
  }
}

/* ---------- helpers ---------- */

/** Fill each OtpInput digit box (aria-label "&lt;label&gt; digit N"). */
async function fillOtp(page: Page, label: string, code: string) {
  for (let i = 0; i < code.length; i += 1) {
    await page.locator(`input[aria-label="${label} digit ${i + 1}"]`).fill(code[i]!);
  }
}

/**
 * Persist the authenticated storage state deterministically.
 *
 * The workspace page hydrates its session on mount, rotating the refresh token
 * (identity invalidates the previous token on every rotate). Dev-mode Fast
 * Refresh can re-mount the page afterwards and rotate again - a stale file
 * token would then trip the reuse detector (family revoke) when the smoke
 * context presents it. Closing the page first stops all rotations, so the
 * captured cookie is exactly the token the smoke context will consume first.
 */
async function saveAuthState(page: Page) {
  await page.close();
  const state = await page.context().storageState({ path: AUTH_FILE });
  const hasWorkspaceCookie = state.cookies.some(
    (cookie) => cookie.name === "skyrict_session" && cookie.domain === "default.localhost",
  );
  if (!hasWorkspaceCookie) {
    throw new Error(
      "Workspace session cookie was not persisted to storage state; the smoke suite would start unauthenticated.",
    );
  }
  return state;
}

setup("authenticate as the seeded admin", async ({ page }) => {
  const enrolledSecret = readEnrolledSecret();

  // Capture the raw TOTP secret the browser receives from the MFA setup API
  // so the enrollment can be completed programmatically. A response listener
  // is used instead of route interception because route.fetch() re-issues the
  // request through Node, which cannot resolve the *.localhost host (only the
  // browser can).
  let mfaSecret: string | null = null;
  page.on("response", async (response) => {
    if (!response.url().includes("/api/auth/mfa/setup")) return;
    const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    mfaSecret = typeof body.secret === "string" ? body.secret : null;
  });

  await page.goto("/signin"); // workspace surface 302s to {slug}.signin.{apex}/signin
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();

  // The seeded admin either lands on /setup-mfa (first enrollment) or is
  // challenged for a TOTP code on the login form (already enrolled). Wait for
  // whichever path this run takes.
  const path = await new Promise<"enrollment" | "challenge">((resolve) => {
    void page
      .waitForURL("**/setup-mfa", { timeout: 15_000 })
      .then(() => resolve("enrollment"))
      .catch(() => {});
    void page
      .getByRole("heading", { name: "Two-factor check" })
      .waitFor({ timeout: 15_000 })
      .then(() => resolve("challenge"))
      .catch(() => {});
  });

  if (path === "challenge") {
    expect(
      enrolledSecret,
      "E2E_TOTP_SECRET must be set when the admin already has MFA enrolled.",
    ).toBeTruthy();
    await fillOtp(page, "Two-factor code", totp(enrolledSecret));
    // The OTP form submits itself as soon as the last digit is filled, so no
    // click is needed - and none is safe (the button is mid-flight disabled).
    // The handoff POSTs to the workspace origin and lands on {slug}.localhost.
    await waitForWorkspace(page);
    await saveAuthState(page);
    return;
  }

  // Enrollment path: wait for the intercepted secret, then verify a TOTP code
  // generated from it. Try the current, previous, and next 30s windows to
  // dodge clock boundaries.
  await expect
    .poll(() => mfaSecret, {
      timeout: 10_000,
      message: "MFA setup response did not include a TOTP secret.",
    })
    .toBeTruthy();

  const secret = mfaSecret ?? enrolledSecret;
  expect(secret, "MFA setup secret is missing.").toBeTruthy();
  // Persist the server-generated secret so a later run can play the challenge
  // path without the operator knowing it. Written before the TOTP loop so a
  // clock-boundary failure still leaves a recoverable secret.
  writeFileSync(TOTP_SECRET_FILE, secret, "utf8");

  let verified = false;
  for (const offset of [0, -1, 1]) {
    await fillOtp(page, "Authenticator code", totp(secret, offset));
    await page.getByRole("button", { name: "Verify and continue" }).click();

    const success = page
      .getByText("Authenticator verified")
      .waitFor({ timeout: 4_000 })
      .then(() => true)
      .catch(() => false);
    const failure = page
      .getByText("That code doesn't match")
      .waitFor({ timeout: 4_000 })
      .then(() => false)
      .catch(() => false);
    if (await Promise.race([success, failure])) {
      verified = true;
      break;
    }
  }
  expect(
    verified,
    "TOTP enrollment failed across the current, previous, and next windows.",
  ).toBe(true);

  // Acknowledge and finish; the handoff form-POSTs to the workspace origin
  // and lands on {slug}.localhost (never the signin host).
  await page
    .getByRole("button", { name: "I've saved my recovery codes somewhere safe." })
    .click();
  await page.getByRole("button", { name: "Finish setup" }).click();
  await waitForWorkspace(page);
  await saveAuthState(page);
});

/** Wait for the login/MFA handoff to land on the workspace host. */
async function waitForWorkspace(page: Page) {
  await page.waitForURL(
    (url) => !url.hostname.includes(".signin."),
    { timeout: 20_000 },
  );
}