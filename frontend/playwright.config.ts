import { defineConfig, devices } from "@playwright/test";

// Browser tests run against the dev server. CI installs Chromium only.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // CI executors report many cores but have little memory; 18 browsers at once got the job killed.
  ...(process.env.CI ? { workers: 2 } : {}),
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "pnpm exec next dev --port 3100",
    url: "http://localhost:3100",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      // The public demo key (frontend/.env.example): a real Ed25519 key, so record pages verify.
      NEXT_PUBLIC_PINNED_VERIFIER_KEY:
        process.env.NEXT_PUBLIC_PINNED_VERIFIER_KEY ??
        "tallyproof.dev/log/v1+c04b910b+ARIXhwyOWRiBdf5kvkuHmZxGuibupdyNRDe40eDIu15y",
      NEXT_TELEMETRY_DISABLED: "1",
    },
  },
});
