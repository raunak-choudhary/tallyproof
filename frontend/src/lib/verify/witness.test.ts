import { describe, expect, it } from "vitest";

import { fetchWitness, latestWitnessed } from "./witness";

describe("witness export", () => {
  it("takes the newest checkpoint in the file", () => {
    const text = [
      JSON.stringify({ tree_size: 512, note: "a" }),
      JSON.stringify({ tree_size: 1792, note: "b" }),
      "",
    ].join("\n");
    expect(latestWitnessed(text)).toEqual({ treeSize: 1792, note: "b" });
    expect(latestWitnessed("")).toBeNull();
  });

  it("reports where it fetched from, and failures as data", async () => {
    const ok = (async () =>
      new Response(JSON.stringify({ tree_size: 4, note: "n" }))) as unknown as typeof fetch;
    expect(await fetchWitness("https://raw.githubusercontent.com/o/r/main/w.jsonl", ok)).toEqual({
      note: "n",
      source: "raw.githubusercontent.com",
    });
    const missing = (async () => new Response("", { status: 404 })) as unknown as typeof fetch;
    expect(await fetchWitness("https://example.org/w.jsonl", missing)).toEqual({
      error: "it answered 404",
      source: "example.org",
    });
  });
});
