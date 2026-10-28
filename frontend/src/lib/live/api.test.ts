import { describe, expect, it } from "vitest";

import { ApiError, fetchProof, recentEvents } from "./api";

function fakeFetch(status: number, body: unknown): typeof fetch {
  return (async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    })) as typeof fetch;
}

describe("live API client", () => {
  it("maps proofs to bytes", async () => {
    const proof = await fetchProof(
      "http://api",
      "evt_1",
      fakeFetch(200, {
        leaf_index: 3,
        tree_size: 8,
        audit_path_hex: ["00ff", "0a0b"],
        checkpoint_note: "note",
      }),
    );
    expect(proof.treeSize).toBe(8);
    expect(Array.from(proof.auditPath[0] ?? [])).toEqual([0, 255]);
  });

  it("surfaces the problem detail on errors", async () => {
    const failing = fakeFetch(409, { detail: "Checkpoints close within seconds." });
    await expect(fetchProof("http://api", "evt_1", failing)).rejects.toThrow(
      new ApiError("Checkpoints close within seconds.", 409),
    );
  });

  it("lists recent events", async () => {
    const events = await recentEvents(
      "http://api",
      2,
      fakeFetch(200, {
        results: [
          { event_id: "evt_a", leaf_index: 0, event_type: "cash.movement", canonical: "{}" },
        ],
      }),
    );
    expect(events).toEqual([
      { eventId: "evt_a", leafIndex: 0, eventType: "cash.movement", canonical: "{}" },
    ]);
  });
});
