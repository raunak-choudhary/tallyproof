/**
 * The accessibility pass beyond axe. Keyboard paths: every page opens with a skip link
 * that lands on the content, every focus stop shows where it is, and the charts that take
 * input work from the keyboard. Reduced motion: the story is stills and nothing scrubs.
 */

import { expect, test } from "@playwright/test";

const PAGES = [
  "/",
  "/ledger/",
  "/ask/",
  "/tamper/",
  "/evals/",
  "/how-it-works/",
  "/ledger/events/evt_01J92P0V00ZQSM7FGKNG6F5228/",
] as const;

for (const path of PAGES) {
  test(`${path}: skip link first, and every focus stop is visible`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => undefined);
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to content" });
    await expect(skip).toBeFocused();
    await expect(skip).toBeInViewport();
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press("Tab");
      const stop = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body || el.tagName === "NEXTJS-PORTAL") return null;
        const style = getComputedStyle(el);
        const box = el.getBoundingClientRect();
        return {
          name: (el.getAttribute("aria-label") ?? el.textContent ?? el.tagName).trim().slice(0, 40),
          shown: box.width > 0 && box.height > 0,
          ring:
            (style.outlineStyle !== "none" && style.outlineWidth !== "0px") ||
            style.boxShadow !== "none",
        };
      });
      if (!stop) break;
      expect(stop.shown, `"${stop.name}" takes focus while hidden`).toBe(true);
      expect(stop.ring, `"${stop.name}" shows no focus ring`).toBe(true);
    }
  });
}

test("the skip link moves focus past the navigation", async ({ page }) => {
  await page.goto("/tamper/");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
});

test("the question matrix is one tab stop, moved with the arrow keys", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/evals/");
  const cells = page.locator("[data-cell]");
  await expect(cells.first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("[data-cell][tabindex='0']")).toHaveCount(1);
  await page.locator("[data-cell][tabindex='0']").focus();
  const before = await page.evaluate(() => document.activeElement?.getAttribute("data-cell"));
  await page.keyboard.press("ArrowDown");
  const after = await page.evaluate(() => document.activeElement?.getAttribute("data-cell"));
  expect(after).not.toBe(before);
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-cell][aria-pressed='true']")).toHaveCount(1);
});

test("the streamgraph moves between bins with the arrow keys", async ({ page }) => {
  await page.goto("/ledger/");
  const chart = page.getByRole("img", { name: /bins by/ });
  await expect(chart).toBeVisible({ timeout: 20_000 });
  const caption = page.locator("figcaption span").first();
  await chart.focus();
  await page.keyboard.press("Home");
  const first = await caption.textContent();
  await page.keyboard.press("ArrowRight");
  await expect(caption).not.toHaveText(first ?? "");
});

test.describe("with reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("the story is a set of stills that scroll normally", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => undefined);
    await expect(page.locator("[data-mode]")).toHaveAttribute("data-mode", "stills");
    await expect(page.locator(".pin-spacer")).toHaveCount(0);
    await expect(page.locator("html.lenis")).toHaveCount(0);
  });
});
