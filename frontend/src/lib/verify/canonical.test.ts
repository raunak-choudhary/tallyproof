import { sha256 } from "@noble/hashes/sha2.js";
import { describe, expect, it } from "vitest";

import { toHex, utf8 } from "./bytes";
import { CanonicalizationError, canonicalize } from "./canonical";
import { leafHash } from "./hashing";
import { loadVectors } from "./vectors";

interface CanonicalVectors {
  cases: {
    name: string;
    input: unknown;
    canonical_utf8: string;
    canonical_sha256_hex: string;
    leaf_hash_hex: string;
  }[];
}

const vectors = loadVectors<CanonicalVectors>("canonical.json");

describe("canonical JSON matches the Python core byte for byte", () => {
  it.each(vectors.cases)("$name", (c) => {
    const text = canonicalize(c.input);
    expect(text).toBe(c.canonical_utf8);
    expect(toHex(sha256(utf8(text)))).toBe(c.canonical_sha256_hex);
    expect(toHex(leafHash(utf8(text)))).toBe(c.leaf_hash_hex);
  });

  it.each([1.5, { amount: 10.25 }, -1, 2 ** 53, { memo: "lone \ud800 surrogate" }])(
    "rejects %o, which could serialize differently in another language",
    (value) => {
      expect(() => canonicalize(value)).toThrow(CanonicalizationError);
    },
  );
});
