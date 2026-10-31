/**
 * What a visitor does on each page, end to end: read the story, verify a record and
 * tamper with it, run the tamper ladder, read the ledger and the evaluation runs, and ask
 * the analyst and share the answer. Each flow runs on a phone and a laptop, in both
 * themes, and attaches a screenshot of where it ends.
 *
 * The analyst flows use a second dev server built with an API URL, and answer that API
 * here from the signed replay bundle, with real proofs, so the browser verifies real data.
 */

import { readFileSync } from "node:fs";
import path from "node:path";

import type { Page, TestInfo } from "@playwright/test";
import { expect, test } from "@playwright/test";

import { toHex, utf8 } from "../src/lib/verify/bytes";
import { leafHash } from "../src/lib/verify/hashing";
import { inclusionProof } from "../src/lib/verify/merkle";
import { LIVE_API } from "../playwright.config";

const LIVE = "http://localhost:3101";
const RECORD = "evt_01J92P0V00ZQSM7FGKNG6F5228";

const SIZES = [
  { name: "phone", width: 375, height: 812 },
  { name: "laptop", width: 1280, height: 800 },
] as const;

async function snap(page: Page, info: TestInfo) {
  await info.attach("end of flow", {
    body: await page.screenshot({ fullPage: false }),
    contentType: "image/png",
  });
}

/** Click once the page has hydrated: the dev server renders before React attaches. */
async function clickWhenLive(page: Page, name: string | RegExp, check: () => Promise<void>) {
  await expect(async () => {
    await page.getByRole("button", { name }).first().click();
    await check();
  }).toPass({ timeout: 20_000 });
}

// The replay bundle, read once, to answer the mocked API with real records and proofs.
const replay = path.join(process.cwd(), "public", "replay");
const records = readFileSync(path.join(replay, "events.jsonl"), "utf-8")
  .trim()
  .split("\n")
  .map((line) => JSON.parse(line) as { event_id: string; leaf_index: number; canonical: string });
const leaves = records.map((r) => leafHash(utf8(r.canonical)));
const latest = readFileSync(path.join(replay, "checkpoints.jsonl"), "utf-8")
  .trim()
  .split("\n")
  .map((line) => JSON.parse(line) as { tree_size: number; note: string })
  .at(-1)!;
const cited = records.filter((r) => r.canonical.includes('"amount"')).slice(0, 24);
const ANSWER = {
  answer_id: "ans_flow",
  question: "How much was obligated on 1 October 2024?",
  status: "answered",
  text: "Agencies obligated $1,000.00 [[c1]].",
  refusal: null,
  assurance: "filter_shown",
  filter_words: "obligations on 2024-10-01",
  checkpoint_tree_size: latest.tree_size,
  slots: [
    {
      label: "s1",
      kind: "money",
      value: "1000.00",
      display: "$1,000.00",
      meaning: "total obligated",
      citation: "c1",
    },
  ],
  citations: [
    {
      label: "c1",
      meaning: "the obligations summed",
      events: cited.map((r) => ({ event_id: r.event_id, leaf_index: r.leaf_index })),
    },
  ],
  quotes: [],
};

async function answerTheApi(page: Page) {
  await page.route(`${LIVE_API}/**`, async (route) => {
    const url = new URL(route.request().url());
    const proof = url.pathname.match(/^\/api\/v1\/events\/([^/]+)\/proof$/);
    const event = url.pathname.match(/^\/api\/v1\/events\/([^/]+)$/);
    const record = records.find(
      (r) => r.event_id === decodeURIComponent((proof ?? event)?.[1] ?? ""),
    );
    if (url.pathname === "/api/v1/queries" || url.pathname.startsWith("/api/v1/answers/"))
      return route.fulfill({ json: ANSWER });
    if (record && proof)
      return route.fulfill({
        json: {
          leaf_index: record.leaf_index,
          tree_size: latest.tree_size,
          audit_path_hex: inclusionProof(leaves, record.leaf_index).map(toHex),
          checkpoint_note: latest.note,
        },
      });
    if (record && event)
      return route.fulfill({
        json: {
          event_id: record.event_id,
          leaf_index: record.leaf_index,
          event_type: (JSON.parse(record.canonical) as { event_type: string }).event_type,
          canonical: record.canonical,
        },
      });
    return route.fulfill({ status: 404, json: { detail: "Not found." } });
  });
}

for (const theme of ["light", "dark"] as const) {
  for (const size of SIZES) {
    test.describe(`${theme}, ${size.name}`, () => {
      test.use({ colorScheme: theme, viewport: { width: size.width, height: size.height } });

      test("the story leads to a real record", async ({ page }, info) => {
        await page.goto("/");
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await expect(page.locator("[data-scene]")).toHaveCount(7);
        await page.getByRole("link", { name: "Skip the story" }).click();
        await expect(page.locator("#records")).toBeInViewport();
        // Smooth scrolling can still be easing the list into place, so click the link itself.
        await page
          .locator("#records a")
          .first()
          .evaluate((a: HTMLAnchorElement) => a.click());
        await expect(page).toHaveURL(/\/ledger\/events\/evt_/);
        await snap(page, info);
      });

      test("a record verifies, and an edit is caught", async ({ page }, info) => {
        await page.goto(`/ledger/events/${RECORD}/`);
        const verdict = page.getByText(/^Verified: this record/);
        await clickWhenLive(page, "Verify this record", () =>
          expect(verdict).toBeVisible({ timeout: 2000 }),
        );
        await expect(page.getByText("Values on this page match the verified bytes")).toBeVisible();
        await page.getByLabel("Try a different amount").fill("1.00");
        await page.getByRole("button", { name: "Edit the record and verify" }).click();
        await expect(page.getByText(/^Tampering detected/)).toBeVisible();
        await snap(page, info);
      });

      test("every level of the tamper ladder is caught or explained", async ({ page }, info) => {
        await page.goto("/tamper/");
        const runs = page.getByRole("button", { name: "Run attack" });
        await expect(async () => {
          await runs.nth(0).click();
          await expect(page.getByRole("heading", { name: /^Level 1:/ })).toBeVisible({
            timeout: 2000,
          });
        }).toPass({ timeout: 20_000 });
        for (const level of [1, 2, 3]) {
          await runs.nth(level - 1).click();
          await expect(page.getByText(/^Tampering detected/)).toBeVisible();
        }
        await runs.nth(3).click();
        await expect(page.getByText(/every check on the record passes/).first()).toBeVisible();
        await expect(page.getByText(/Consistent with the checkpoint witnessed at/)).toBeVisible();
        await snap(page, info);
      });

      test("the ledger draws the replayed log", async ({ page }, info) => {
        await page.goto("/ledger/");
        await expect(page.getByRole("img", { name: /bins by/ })).toBeVisible({ timeout: 20_000 });
        await snap(page, info);
      });

      test("the evaluation runs can be compared and opened", async ({ page }, info) => {
        await page.goto("/evals/");
        const run = page.getByRole("combobox", { name: "Run", exact: true });
        await expect(run).toBeVisible({ timeout: 20_000 });
        await expect(async () => {
          await run.selectOption({ index: 0 });
          await expect(run).toHaveValue("20261029T002211Z.json", { timeout: 1000 });
        }).toPass({ timeout: 20_000 });
        await expect(page.locator("figcaption").getByText("Oct 29, 00:22 UTC")).toBeVisible();
        // The smoke questions come after the newest run's, past the rows drawn at first.
        await page.getByRole("button", { name: /^Show all \d+ questions$/ }).click();
        await page.getByRole("button", { name: /^S001, run 1:/ }).click();
        await expect(page.getByText(/^S001 · numeric aggregate · run 1/)).toBeVisible();
        if (size.name === "laptop") {
          const axis = page.locator("svg[aria-label^='Parallel coordinates'] g.axis-brush").first();
          await axis.scrollIntoViewIfNeeded();
          const box = (await axis.boundingBox())!;
          await page.mouse.move(box.x + box.width / 2, box.y + 4);
          await page.mouse.down();
          await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.15, { steps: 5 });
          await page.mouse.up();
          await expect(page.getByText(/runs inside the ranges you dragged/)).toBeVisible();
        }
        await snap(page, info);
      });

      test("an answer's citations verify, and the answer can be shared", async ({ page }, info) => {
        await answerTheApi(page);
        await page.goto(`${LIVE}/ask/`);
        const box = page.getByLabel("Ask about federal contract spending");
        await expect(async () => {
          await box.fill(ANSWER.question);
          await page.getByRole("button", { name: "Ask", exact: true }).click();
          await expect(page.getByText("Agencies obligated")).toBeVisible({ timeout: 2000 });
        }).toPass({ timeout: 20_000 });
        await expect(page.getByRole("img", { name: /Beeswarm of 24 cited records/ })).toBeVisible();
        await page.getByRole("button", { name: "Verify", exact: true }).first().click();
        await expect(page.getByText("✓ Verified").first()).toBeVisible();
        const share = page.getByRole("link", { name: "Link to this answer" });
        await expect(share).toHaveAttribute("href", "/answers/?id=ans_flow");
        await page.goto(`${LIVE}/answers/?id=ans_flow`);
        await expect(page.getByRole("heading", { name: ANSWER.question })).toBeVisible({
          timeout: 20_000,
        });
        await snap(page, info);
      });
    });
  }
}
