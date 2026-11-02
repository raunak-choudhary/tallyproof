import { createRequire } from "module";
import { rename, writeFile } from "fs/promises";
const require = createRequire("/Users/raunakchoudhary/Data/Projects/tallyproof/frontend/package.json");
const { chromium } = require("@playwright/test");
const out = "/Users/raunakchoudhary/Data/Projects/tallyproof/internal/phase8/outputs/brag/tallyproof-launch/work";
const url = "https://raunak-choudhary.github.io/tallyproof/ledger/events/evt_01J92P0V00ZQSM7FGKNG6F5228/";
const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 }, colorScheme: "dark", deviceScaleFactor: 1,
  recordVideo: { dir: out + "/rec", size: { width: 1920, height: 1080 } },
});
const page = await ctx.newPage();
const t0 = Date.now();
const marks = {};
const mark = (k) => (marks[k] = (Date.now() - t0) / 1000);
await page.goto(url, { waitUntil: "networkidle" });
await page.waitForTimeout(800);
await page.evaluate(() => {
  const h = [...document.querySelectorAll("h2")].find((e) => e.textContent.trim() === "Check it yourself");
  const y = h.getBoundingClientRect().top + window.scrollY - 120;
  window.scrollTo({ top: y, behavior: "instant" });
});
await page.waitForTimeout(1200);
mark("verify-click");
await page.getByRole("button", { name: "Verify this record" }).click();
await page.waitForTimeout(600);
mark("scroll-1");
await page.evaluate(() => {
  const h = [...document.querySelectorAll("h2")].find((e) => e.textContent.trim() === "Check it yourself");
  window.scrollTo({ top: h.getBoundingClientRect().top + window.scrollY - 90, behavior: "smooth" });
});
await page.waitForTimeout(3400);
await page.screenshot({ path: out + "/site/verify-passed.png" });
const input = page.getByPlaceholder("9347.55");
mark("input-click");
await input.click();
await input.fill("");
const keys = "9347.56";
for (const ch of keys) { mark("key-" + Object.keys(marks).length); await page.keyboard.type(ch); await page.waitForTimeout(140); }
await page.waitForTimeout(500);
mark("edit-click");
await page.getByRole("button", { name: "Edit the record and verify" }).click();
await page.waitForTimeout(500);
await page.evaluate(() => {
  const h = [...document.querySelectorAll("h2")].find((e) => e.textContent.trim() === "Check it yourself");
  window.scrollTo({ top: h.getBoundingClientRect().top + window.scrollY - 90, behavior: "smooth" });
});
await page.waitForTimeout(4000);
await page.screenshot({ path: out + "/site/verify-failed.png" });
mark("end");
const video = page.video();
await ctx.close();
await rename(await video.path(), out + "/verify-flow.webm");
await writeFile(out + "/verify-marks.json", JSON.stringify(marks, null, 2));
await browser.close();
console.log(JSON.stringify(marks));
