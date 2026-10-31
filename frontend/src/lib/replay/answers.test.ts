import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { bundleRecords } from "@/lib/analyst/records";
import { parseVerifierKey } from "@/lib/verify/checkpoint";
import { verifyEvent } from "@/lib/verify/verifyEvent";

import { loadDemoAnswers, parseDemoAnswers } from "./answers";
import { loadBundle } from "./bundle";

const REPLAY_DIR = new URL("../../../public/replay/", import.meta.url);
const vkey = /NEXT_PUBLIC_PINNED_VERIFIER_KEY=(.+)/.exec(
  readFileSync(new URL("../../../.env.example", import.meta.url), "utf-8"),
)?.[1];
const pinnedKey = parseVerifierKey(vkey ?? "");

describe("the static site's demo answers", () => {
  beforeEach(() =>
    vi.stubGlobal("fetch", (url: string) => {
      const name = url.split("/").at(-1) ?? "";
      return Promise.resolve(
        new Response(readFileSync(new URL(name, REPLAY_DIR), "utf-8"), { status: 200 }),
      );
    }),
  );
  afterEach(() => vi.unstubAllGlobals());

  it("are pinned to the bundle's checkpoint", async () => {
    const demo = await loadDemoAnswers("/replay");
    expect(demo.answers.length).toBeGreaterThan(0);
    for (const answer of demo.answers) expect(answer.treeSize).toBe(demo.treeSize);
  });

  it("cite only records that verify from the bundle, at the leaf they name", async () => {
    const [demo, bundle] = await Promise.all([
      loadDemoAnswers("/replay"),
      loadBundle("/replay", pinnedKey),
    ]);
    const records = bundleRecords(bundle);
    const seen = new Set<string>();
    for (const answer of demo.answers) {
      for (const cited of answer.citations.flatMap((c) => c.events)) {
        if (seen.has(cited.eventId)) continue;
        seen.add(cited.eventId);
        const [event, proof] = await Promise.all([
          records.event(cited.eventId),
          records.proof(cited.eventId, answer.treeSize),
        ]);
        const result = verifyEvent({
          canonical: event.canonical,
          leafIndex: proof.leafIndex,
          publishedLeaves: [],
          auditPath: proof.auditPath,
          checkpointNote: proof.checkpointNote,
          pinnedKey,
          expected: {
            eventId: cited.eventId,
            leafIndex: cited.leafIndex,
            treeSize: answer.treeSize,
          },
        });
        expect(result.ok, cited.eventId).toBe(true);
      }
    }
    expect(seen.size).toBeGreaterThan(100);
  }, 60_000);

  it("can't verify a record the bundle doesn't have", async () => {
    const records = bundleRecords(await loadBundle("/replay", pinnedKey));
    await expect(async () => records.proof("evt_not_there", 2000)).rejects.toThrow(/no record/);
  });

  it("keep refusals as refusals", () => {
    const demo = parseDemoAnswers(readFileSync(new URL("answers.json", REPLAY_DIR), "utf-8"));
    const refused = demo.answers.filter((a) => a.status === "refused");
    expect(refused.map((a) => a.refusal?.code).sort()).toEqual(["forecast", "personal_data"]);
  });
});
