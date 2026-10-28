import { describe, expect, it } from "vitest";

import { toHex } from "./bytes";
import { CheckpointError, parseVerifierKey, verifyCheckpoint, verifyNote } from "./checkpoint";
import { loadVectors } from "./vectors";

interface CheckpointVectors {
  verifier_key: string;
  valid: { note: string; origin: string; tree_size: number; root_hash_hex: string };
  must_fail: { reason: string; note: string }[];
}

const vectors = loadVectors<CheckpointVectors>("checkpoint.json");
const key = parseVerifierKey(vectors.verifier_key);

// The worked example from https://c2sp.org/signed-note.
const SPEC_VKEY = "example.com/foo+530d903a+AekyeRrm56hApGFkyQR4ZCbV54Id2LKaANYcrnKv3U2k";
const SPEC_NOTE =
  "This is an example message.\n\n— example.com/foo Uw2QOkn8srV1yJGh2VYRlL1Tnagv1YEq6TfXppzi2ONncAlTgK7Ztg1ERYNZXsYjOBH3mFXmRKuwHjG1Yu72IneyaQM=\n";

describe("signed checkpoints", () => {
  it("verifies the C2SP specification example", () => {
    expect(verifyNote(SPEC_NOTE, parseVerifierKey(SPEC_VKEY))).toBe(
      "This is an example message.\n",
    );
  });

  it("verifies the checkpoint the Python core signed", () => {
    const checkpoint = verifyCheckpoint(vectors.valid.note, key);
    expect(checkpoint.origin).toBe(vectors.valid.origin);
    expect(checkpoint.treeSize).toBe(vectors.valid.tree_size);
    expect(toHex(checkpoint.rootHash)).toBe(vectors.valid.root_hash_hex);
  });

  it.each(vectors.must_fail)("rejects a note where the $reason", (c) => {
    expect(() => verifyCheckpoint(c.note, key)).toThrow(CheckpointError);
  });

  it("accepts keys whose base64 contains a plus sign", () => {
    // Only the first two "+" separate fields (C2SP signed-note); this key's base64 has one.
    const key = parseVerifierKey(
      "eval.tallyproof.dev/log/v1+e6394e68+Afy7CUs9XEqZ7UZMDtQG6caBei5luIfXm8TpQUb+Rew2",
    );
    expect(key.name).toBe("eval.tallyproof.dev/log/v1");
    expect(key.publicKey.length).toBe(32);
  });

  it("rejects malformed verifier keys", () => {
    expect(() => parseVerifierKey("example.com/foo+530d903a")).toThrow(/three parts/);
    expect(() =>
      parseVerifierKey("example.com/foo+00000000+AekyeRrm56hApGFkyQR4ZCbV54Id2LKaANYcrnKv3U2k"),
    ).toThrow(/does not match/);
    expect(() => parseVerifierKey("example.com/foo+530d903a+Ux==")).toThrow(/base64/);
  });
});
