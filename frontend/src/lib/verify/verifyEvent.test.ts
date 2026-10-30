import * as ed from "@noble/ed25519";
import { sha256 } from "@noble/hashes/sha2.js";
import { describe, expect, it } from "vitest";

import { concat, toBase64, toHex, utf8 } from "./bytes";
import { canonicalize } from "./canonical";
import { parseVerifierKey } from "./checkpoint";
import { leafHash } from "./hashing";
import { inclusionProof, root } from "./merkle";
import { forgeCheckpointWithNewRoot, verifyEvent } from "./verifyEvent";

const NAME = "test.tallyproof.dev/log/v1";
const secret = sha256(utf8("verify event test key"));
const publicKey = ed.getPublicKey(secret);
const keyId = sha256(concat(utf8(NAME), Uint8Array.of(0x0a, 0x01), publicKey)).slice(0, 4);
const pinnedKey = parseVerifierKey(
  `${NAME}+${toHex(keyId)}+${toBase64(concat(Uint8Array.of(1), publicKey))}`,
);

function signNote(text: string, signingSecret = secret): string {
  const signature = ed.sign(utf8(text), signingSecret);
  return `${text}\n— ${NAME} ${toBase64(concat(keyId, signature))}\n`;
}

const records = Array.from({ length: 7 }, (_, i) =>
  canonicalize({ event_id: `evt_${i}`, payload: { amount: `${(i + 1) * 100}.00` } }),
);
const leaves = records.map((r) => leafHash(utf8(r)));
const note = signNote(`${NAME}\n7\n${toBase64(root(leaves))}\n`);

describe("verifyEvent", () => {
  const cited = (override: Record<string, unknown>, leafIndex = 3) =>
    verifyEvent({
      canonical: records[3]!,
      leafIndex,
      publishedLeaves: leaves,
      checkpointNote: note,
      pinnedKey,
      expected: { eventId: "evt_3", leafIndex: 3, treeSize: 7, ...override },
    });

  it("ties the proof to the cited event, leaf, and checkpoint", () => {
    const result = cited({});
    expect(result.steps.at(-1)).toMatchObject({ id: "match", ok: true });
    expect(result.ok).toBe(true);
  });

  it.each([
    ["another event", { eventId: "evt_4" }],
    ["another leaf", { leafIndex: 4 }],
    ["another checkpoint", { treeSize: 9 }],
  ])("fails when the record or proof is for %s", (_, mismatch) => {
    const result = cited(mismatch);
    expect(result.steps.find((s) => s.id === "match")?.ok).toBe(false);
    expect(result.steps.find((s) => s.id === "inclusion")?.ok).toBe(true);
    expect(result.ok).toBe(false);
  });

  it("checks a quote against the record's own text", () => {
    const text = "Only contracting officers may execute change orders.";
    const record = canonicalize({ event_id: "evt_q", payload: { text } });
    const single = leafHash(utf8(record));
    const quoteNote = signNote(`${NAME}\n1\n${toBase64(root([single]))}\n`);
    const check = (quote: string) =>
      verifyEvent({
        canonical: record,
        leafIndex: 0,
        publishedLeaves: [single],
        checkpointNote: quoteNote,
        pinnedKey,
        expected: { eventId: "evt_q", leafIndex: 0, treeSize: 1, quote },
      });
    expect(check("contracting officers may execute").ok).toBe(true);
    expect(check("anyone may execute change orders").ok).toBe(false);
  });

  it("passes every step for an untouched record", () => {
    const result = verifyEvent({
      canonical: records[3]!,
      leafIndex: 3,
      publishedLeaves: leaves,
      checkpointNote: note,
      pinnedKey,
    });
    expect(result.steps.map((s) => [s.id, s.ok])).toEqual([
      ["signature", true],
      ["canonical", true],
      ["leaf", true],
      ["inclusion", true],
    ]);
    expect(result.ok).toBe(true);
  });

  it("level 1: an edited record no longer reaches the signed root", () => {
    const edited = records[3]!.replace('"400.00"', '"900.00"');
    const result = verifyEvent({
      canonical: edited,
      leafIndex: 3,
      publishedLeaves: leaves,
      checkpointNote: note,
      pinnedKey,
    });
    expect(result.ok).toBe(false);
    expect(result.steps.find((s) => s.id === "inclusion")?.ok).toBe(false);
    expect(result.steps.find((s) => s.id === "signature")?.ok).toBe(true);
  });

  it("level 2: rebuilding the tree without the key fails the signature check", () => {
    const edited = records[3]!.replace('"400.00"', '"900.00"');
    const forged = forgeCheckpointWithNewRoot(note, leaves, 3, edited);
    const result = verifyEvent({
      canonical: edited,
      leafIndex: 3,
      publishedLeaves: leaves.map((l, i) => (i === 3 ? leafHash(utf8(edited)) : l)),
      checkpointNote: forged,
      pinnedKey,
    });
    expect(result.ok).toBe(false);
    expect(result.steps).toHaveLength(1);
    expect(result.steps[0]).toMatchObject({ id: "signature", ok: false });
  });

  it("rejects a checkpoint signed by a different key", () => {
    const other = signNote(`${NAME}\n7\n${toBase64(root(leaves))}\n`, sha256(utf8("other")));
    const result = verifyEvent({
      canonical: records[0]!,
      leafIndex: 0,
      publishedLeaves: leaves,
      checkpointNote: other,
      pinnedKey,
    });
    expect(result.steps[0]?.ok).toBe(false);
  });

  it("flags records that are not in canonical form or not JSON", () => {
    const spaced = records[2]!.replace(":", ": ");
    const notCanonical = verifyEvent({
      canonical: spaced,
      leafIndex: 2,
      publishedLeaves: leaves,
      checkpointNote: note,
      pinnedKey,
    });
    expect(notCanonical.steps.find((s) => s.id === "canonical")?.ok).toBe(false);
    const broken = verifyEvent({
      canonical: "{not json",
      leafIndex: 2,
      publishedLeaves: leaves,
      checkpointNote: note,
      pinnedKey,
    });
    expect(broken.steps.at(-1)).toMatchObject({ id: "canonical", ok: false });
  });

  it("fails inclusion for an index outside the checkpoint", () => {
    const result = verifyEvent({
      canonical: records[0]!,
      leafIndex: 9,
      publishedLeaves: leaves,
      checkpointNote: note,
      pinnedKey,
    });
    expect(result.steps.find((s) => s.id === "inclusion")?.ok).toBe(false);
  });

  it("live mode: an audit path from the API verifies, and an edit still fails", () => {
    const auditPath = inclusionProof(leaves, 4);
    const live = (canonical: string) =>
      verifyEvent({
        canonical,
        leafIndex: 4,
        publishedLeaves: [],
        auditPath,
        checkpointNote: note,
        pinnedKey,
      });
    expect(live(records[4]!).ok).toBe(true);
    const edited = canonicalize({ event_id: "evt_4", payload: { amount: "999.00" } });
    const result = live(edited);
    expect(result.ok).toBe(false);
    expect(result.steps.find((s) => s.id === "inclusion")?.ok).toBe(false);
  });

  it("live mode: a path that does not lead to the signed root fails", () => {
    const wrongPath = inclusionProof(leaves, 2);
    const result = verifyEvent({
      canonical: records[4]!,
      leafIndex: 4,
      publishedLeaves: [],
      auditPath: wrongPath,
      checkpointNote: note,
      pinnedKey,
    });
    expect(result.ok).toBe(false);
  });
});

describe("the outside witness and displayed values", () => {
  const witnessedNote = signNote(`${NAME}\n4\n${toBase64(root(leaves.slice(0, 4)))}\n`);
  const run = (extra: Partial<Parameters<typeof verifyEvent>[0]>, publishedLeaves = leaves) =>
    verifyEvent({
      canonical: records[5]!,
      leafIndex: 5,
      publishedLeaves,
      checkpointNote: note,
      pinnedKey,
      ...extra,
    });
  const step = (r: ReturnType<typeof verifyEvent>, id: string) => r.steps.find((s) => s.id === id);

  it("passes when the signed log extends the witnessed checkpoint", () => {
    const r = run({ witness: { note: witnessedNote, source: "raw.githubusercontent.com" } });
    expect(step(r, "witness")?.ok).toBe(true);
    expect(r.ok).toBe(true);
  });

  it("fails when history before the witness was rewritten and re-signed with the key", () => {
    const rewritten = [...leaves];
    rewritten[1] = leafHash(utf8(canonicalize({ event_id: "evt_1", payload: { amount: "1.00" } })));
    const resigned = signNote(`${NAME}\n7\n${toBase64(root(rewritten))}\n`);
    const r = run(
      {
        checkpointNote: resigned,
        witness: { note: witnessedNote, source: "raw.githubusercontent.com" },
      },
      rewritten,
    );
    expect(step(r, "inclusion")?.ok).toBe(true);
    expect(step(r, "witness")?.ok).toBe(false);
    expect(r.ok).toBe(false);
  });

  it("refuses a witness that the pinned key didn't sign", () => {
    const other = sha256(utf8("someone else"));
    const r = run({
      witness: {
        note: signNote(`${NAME}\n4\n${toBase64(root(leaves.slice(0, 4)))}\n`, other),
        source: "x",
      },
    });
    expect(step(r, "witness")?.ok).toBe(false);
  });

  it("fails visibly when the witness couldn't be fetched", () => {
    const r = run({ witness: { error: "it answered 404", source: "raw.githubusercontent.com" } });
    expect(step(r, "witness")?.detail).toContain("404");
    expect(r.ok).toBe(false);
  });

  it("checks each displayed value against the verified bytes", () => {
    const shown = [{ label: "Amount", path: ["payload", "amount"], value: "600.00" }];
    expect(step(run({ displayed: shown }), "values")?.ok).toBe(true);
    const wrong = [{ label: "Amount", path: ["payload", "amount"], value: "601.00" }];
    const r = run({ displayed: wrong });
    expect(step(r, "values")?.ok).toBe(false);
    expect(step(r, "values")?.detail).toContain("amount");
  });
});
