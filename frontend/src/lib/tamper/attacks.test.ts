import * as ed from "@noble/ed25519";
import { sha256 } from "@noble/hashes/sha2.js";
import { describe, expect, it } from "vitest";

import { concat, toBase64, toHex, utf8 } from "@/lib/verify/bytes";
import { canonicalize } from "@/lib/verify/canonical";
import { parseVerifierKey, verifyCheckpoint } from "@/lib/verify/checkpoint";
import { leafHash } from "@/lib/verify/hashing";
import { root } from "@/lib/verify/merkle";
import { verifyEvent } from "@/lib/verify/verifyEvent";

import { ATTACKS, stage, witnessCheck, witnessedBefore } from "./attacks";

const NAME = "test.tallyproof.dev/log/v1";
const secret = sha256(utf8("tamper ladder test key"));
const publicKey = ed.getPublicKey(secret);
const keyId = sha256(concat(utf8(NAME), Uint8Array.of(0x0a, 0x01), publicKey)).slice(0, 4);
const pinnedKey = parseVerifierKey(
  `${NAME}+${toHex(keyId)}+${toBase64(concat(Uint8Array.of(1), publicKey))}`,
);

function signNote(text: string): string {
  const signature = ed.sign(utf8(text), secret);
  return `${text}\n— ${NAME} ${toBase64(concat(keyId, signature))}\n`;
}

const records = Array.from({ length: 12 }, (_, i) =>
  canonicalize({ event_id: `evt_${i}`, payload: { amount: `${(i + 1) * 100}.00` } }),
);
const leaves = records.map((r) => leafHash(utf8(r)));
const note = (size: number) =>
  signNote(`${NAME}\n${size}\n${toBase64(root(leaves.slice(0, size)))}\n`);
const checkpoints = [4, 8, 12].map((size) => ({ treeSize: size, note: note(size) }));
const latest = checkpoints[2]!.note;
const TARGET = 2; // a record before the witnessed checkpoint at 8

function verify(staged: ReturnType<typeof stage>) {
  return verifyEvent({
    canonical: staged.canonical,
    leafIndex: TARGET,
    publishedLeaves: staged.leaves,
    checkpointNote: staged.note,
    pinnedKey,
  });
}

describe("the tamper ladder", () => {
  it("names four attacks in order", () => {
    expect(ATTACKS.map((a) => a.level)).toEqual([1, 2, 3, 4]);
  });

  it("level 1: the edited record no longer reaches the signed root", () => {
    const result = verify(stage(1, records[TARGET]!, TARGET, leaves, latest, "999.00"));
    expect(result.ok).toBe(false);
    expect(result.steps.find((s) => s.id === "signature")?.ok).toBe(true);
    expect(result.steps.find((s) => s.id === "inclusion")?.ok).toBe(false);
  });

  it("level 2: the rebuilt log's root is not the signed one", () => {
    const staged = stage(2, records[TARGET]!, TARGET, leaves, latest, "999.00");
    expect(staged.leaves[TARGET]).toEqual(leafHash(utf8(staged.canonical)));
    const result = verify(staged);
    expect(result.steps.find((s) => s.id === "signature")?.ok).toBe(true);
    expect(result.steps.find((s) => s.id === "inclusion")?.ok).toBe(false);
  });

  it("level 3: the forged checkpoint fails the signature check", () => {
    const result = verify(stage(3, records[TARGET]!, TARGET, leaves, latest, "999.00"));
    expect(result.steps).toHaveLength(1);
    expect(result.steps[0]).toMatchObject({ id: "signature", ok: false });
  });

  it("level 4: with the signature taken as valid, the witness catches the rewrite", () => {
    const staged = stage(4, records[TARGET]!, TARGET, leaves, latest, "999.00");
    expect(staged.assumeSigned).toBe(true);
    const witnessed = witnessedBefore(checkpoints, 12, pinnedKey);
    expect(witnessed?.treeSize).toBe(8);
    const check = witnessCheck(witnessed!, staged.leaves);
    expect(check.ok).toBe(false);
    expect(check.detail).toContain("does not extend");
    // The honest log is consistent with the same witnessed checkpoint.
    expect(witnessCheck(witnessed!, leaves).ok).toBe(true);
    // An edit after the witnessed checkpoint isn't caught by this witness alone.
    const late = stage(4, records[10]!, 10, leaves, latest, "999.00");
    expect(witnessCheck(witnessed!, late.leaves).ok).toBe(true);
  });

  it("picks the latest verifiable checkpoint before a size", () => {
    expect(witnessedBefore(checkpoints, 9, pinnedKey)?.treeSize).toBe(8);
    expect(witnessedBefore(checkpoints, 4, pinnedKey)).toBeNull();
    const bad = [{ treeSize: 8, note: note(8).replace("8\n", "9\n") }];
    expect(witnessedBefore([...bad, checkpoints[0]!], 12, pinnedKey)?.treeSize).toBe(4);
    expect(verifyCheckpoint(latest, pinnedKey).treeSize).toBe(12);
  });
});
