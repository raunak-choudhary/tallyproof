import { defineConfig, devices } from "@playwright/test";

// Browser tests run against the dev server. CI installs Chromium only.

/** The API origin the live-mode server is built with; flows answer it with page.route. */
export const LIVE_API = "http://api.test";

const SHARED_ENV = {
  // The public demo key (frontend/.env.example): a real Ed25519 key, so record pages verify.
  NEXT_PUBLIC_PINNED_VERIFIER_KEY:
    process.env.NEXT_PUBLIC_PINNED_VERIFIER_KEY ??
    "tallyproof.dev/log/v1+c04b910b+ARIXhwyOWRiBdf5kvkuHmZxGuibupdyNRDe40eDIu15y",
  NEXT_TELEMETRY_DISABLED: "1",
};
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // The dev server compiles each page on first visit, which is slow on CI executors.
  ...(process.env.CI ? { timeout: 60_000 } : {}),
  // CI executors report many cores but have little memory; 18 browsers at once got the job killed.
  ...(process.env.CI ? { workers: 2 } : {}),
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // The site as GitHub Pages serves it: static data only, no API.
      command: "pnpm exec next dev --port 3100",
      url: "http://localhost:3100",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { ...SHARED_ENV },
    },
    {
      // The same site built with an API URL, for the analyst flows. The tests answer that
      // API themselves (page.route), so no backend runs. Its own build folder keeps the two
      // dev servers apart.
      command: "pnpm exec next dev --port 3101",
      url: "http://localhost:3101",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { ...SHARED_ENV, NEXT_DIST_DIR: ".next-live", NEXT_PUBLIC_API_URL: LIVE_API },
    },
  ],
});
