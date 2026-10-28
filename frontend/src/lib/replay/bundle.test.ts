import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { parseVerifierKey } from "@/lib/verify/checkpoint";
import { verifyEvent } from "@/lib/verify/verifyEvent";

import { BundleError, loadBundle } from "./bundle";

// The real bundle exported by the Python pipeline from FY2025 contract data.
const REPLAY_DIR = new URL("../../../public/replay/", import.meta.url);
const vkey = /NEXT_PUBLIC_PINNED_VERIFIER_KEY=(.+)/.exec(
  readFileSync(new URL("../../../.env.example", import.meta.url), "utf-8"),
)?.[1];
const pinnedKey = parseVerifierKey(vkey ?? "");

function serve(overrides: Record<string, string> = {}) {
  vi.stubGlobal("fetch", (url: string) => {
    const name = url.split("/").at(-1) ?? "";
    const body = overrides[name] ?? readFileSync(new URL(name, REPLAY_DIR), "utf-8");
    return Promise.resolve(new Response(body, { status: 200 }));
  });
}

describe("the real replay bundle signed by the Python pipeline", () => {
  beforeEach(() => serve());
  afterEach(() => vi.unstubAllGlobals());

  it("passes the manifest signature and file hash checks", async () => {
    const bundle = await loadBundle("/replay", pinnedKey);
    expect(bundle.records).toHaveLength(2000);
    expect(bundle.manifest.tree_size).toBe(2000);
  });

  it("verifies real events at the start, middle, and end of the log", async () => {
    const bundle = await loadBundle("/replay", pinnedKey);
    for (const index of [0, 1234, 1999]) {
      const record = bundle.records[index]!;
      const result = verifyEvent({
        canonical: record.canonical,
        leafIndex: record.leafIndex,
        publishedLeaves: bundle.leaves,
        checkpointNote: bundle.latestCheckpointNote,
        pinnedKey,
      });
      expect(result.ok).toBe(true);
    }
  });

  it("fails a real record whose amount was edited", async () => {
    const bundle = await loadBundle("/replay", pinnedKey);
    const record = bundle.records[42]!;
    const edited = record.canonical.replace(/"amount":"([^"]+)"/, '"amount":"1.00"');
    expect(edited).not.toBe(record.canonical);
    const result = verifyEvent({
      canonical: edited,
      leafIndex: record.leafIndex,
      publishedLeaves: bundle.leaves,
      checkpointNote: bundle.latestCheckpointNote,
      pinnedKey,
    });
    expect(result.steps.find((s) => s.id === "inclusion")?.ok).toBe(false);
  });

  it("rejects a bundle whose events file was swapped after signing", async () => {
    const events = readFileSync(new URL("events.jsonl", REPLAY_DIR), "utf-8");
    serve({ "events.jsonl": events.replace("Department", "Departmant") });
    await expect(loadBundle("/replay", pinnedKey)).rejects.toThrow(BundleError);
  });

  it("rejects a bundle signed by a key other than the pinned one", async () => {
    const other = parseVerifierKey(
      "example.com/foo+530d903a+AekyeRrm56hApGFkyQR4ZCbV54Id2LKaANYcrnKv3U2k",
    );
    await expect(loadBundle("/replay", other)).rejects.toThrow(/not signed by the trusted key/);
  });
});
