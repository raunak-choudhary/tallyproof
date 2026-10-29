/**
 * The responsive contract (design brief, section 8), enforced on every page.
 *
 * At six viewports and 200 percent zoom, in both themes, no page may scroll sideways,
 * and every page passes the automated accessibility checks. The viewports are a tall
 * phone, a short phone (browser bar or keyboard up), a phone on its side, a tablet,
 * a laptop, and a desktop.
 */

import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

const VIEWPORTS = [
  { name: "phone", width: 375, height: 812 },
  { name: "short phone", width: 375, height: 560 },
  { name: "phone landscape", width: 812, height: 375 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "laptop", width: 1280, height: 800 },
  { name: "desktop", width: 1920, height: 1080 },
] as const;

const PAGES = [
  "/",
  "/ask/",
  "/live/",
  "/ledger/",
  "/ledger/events/evt_01J92P0V00ZQSM7FGKNG6F5228/",
] as const;
const THEMES = ["light", "dark"] as const;

async function noSidewaysScroll(page: Page, label: string) {
  const overflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(overflow.scroll, `${label}: the page scrolls sideways`).toBeLessThanOrEqual(
    overflow.client,
  );
}

for (const theme of THEMES) {
  test.describe(`${theme} theme`, () => {
    test.use({ colorScheme: theme });

    for (const path of PAGES) {
      for (const viewport of VIEWPORTS) {
        test(`${path} fits a ${viewport.name} (${viewport.width}x${viewport.height})`, async ({
          page,
        }) => {
          await page.setViewportSize({ width: viewport.width, height: viewport.height });
          await page.goto(path);
          await page.waitForLoadState("networkidle");
          await noSidewaysScroll(page, `${path} at ${viewport.name}`);
        });
      }

      test(`${path} fits a laptop at 200 percent zoom`, async ({ page }) => {
        // A 1280px laptop at 200 percent zoom lays out like a 640px viewport.
        await page.setViewportSize({ width: 640, height: 400 });
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await noSidewaysScroll(page, `${path} zoomed`);
      });

      test(`${path} passes accessibility checks`, async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze();
        expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      });
    }
  });
}

test("the navigation folds into a menu on phones and opens from it", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  const menu = page.locator("nav[aria-label='Main']").last(); // the folded menu, after the row
  await expect(menu).toBeHidden();
  // The dev server hydrates after load; retry the click until the menu responds.
  await expect(async () => {
    await page.getByRole("button", { name: "Open menu" }).click();
    await expect(menu).toBeVisible({ timeout: 500 });
  }).toPass();
  await expect(menu.getByRole("link", { name: "Ask" })).toBeVisible();
});

test("the theme switch persists and applies before paint", async ({ page }) => {
  await page.goto("/");
  const toggle = page.getByRole("button", { name: /Switch theme/ });
  const root = page.locator("html");
  await expect(async () => {
    await toggle.click(); // system -> light
    await expect(root).toHaveAttribute("data-theme", "light", { timeout: 500 });
  }).toPass();
  await toggle.click(); // light -> dark
  await expect(root).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(root).toHaveAttribute("data-theme", "dark");
});
