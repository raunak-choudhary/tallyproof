import * as ed from "@noble/ed25519";
import { sha256 } from "@noble/hashes/sha2.js";
import { describe, expect, it } from "vitest";

import { concat, toBase64, toHex, utf8 } from "./bytes";
import { canonicalize } from "./canonical";
import { parseVerifierKey } from "./checkpoint";
import { leafHash } from "./hashing";
import { root } from "./merkle";
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
});
