import { describe, expect, it } from "vitest";

import { fromHex, toHex } from "./bytes";
import { leafHash } from "./hashing";
import {
  consistencyProof,
  inclusionProof,
  root,
  verifyConsistency,
  verifyInclusion,
} from "./merkle";
import { loadVectors } from "./vectors";

interface Reference {
  leaf_inputs_hex: string[];
  root_hashes_by_size_hex: string[];
  inclusion_proofs: { index: number; size: number; proof_hex: string[] }[];
  consistency_proofs: { size1: number; size2: number; proof_hex: string[] }[];
}

const vectors = loadVectors<Reference>("merkle_reference.json");
const leaves = vectors.leaf_inputs_hex.map((h) => leafHash(fromHex(h)));
const roots = vectors.root_hashes_by_size_hex.map(fromHex);

function flipBit(bytes: Uint8Array, bit: number): Uint8Array {
  const copy = bytes.slice();
  copy[bit >> 3] = (copy[bit >> 3] ?? 0) ^ (1 << (bit & 7));
  return copy;
}

describe("Merkle log against the RFC 6962 reference vectors", () => {
  it("computes the reference root for every tree size", () => {
    vectors.root_hashes_by_size_hex.forEach((expected, size) => {
      expect(toHex(root(leaves.slice(0, size)))).toBe(expected);
    });
  });

  it.each(vectors.inclusion_proofs)("builds and verifies inclusion proof %o", (c) => {
    expect(inclusionProof(leaves.slice(0, c.size), c.index).map(toHex)).toEqual(c.proof_hex);
    const proof = c.proof_hex.map(fromHex);
    expect(verifyInclusion(leaves[c.index]!, c.index, c.size, proof, roots[c.size]!)).toBe(true);
  });

  it.each(vectors.consistency_proofs)("builds and verifies consistency proof %o", (c) => {
    expect(consistencyProof(leaves.slice(0, c.size2), c.size1).map(toHex)).toEqual(c.proof_hex);
    const proof = c.proof_hex.map(fromHex);
    expect(verifyConsistency(c.size1, c.size2, roots[c.size1]!, roots[c.size2]!, proof)).toBe(true);
  });

  it("proves consistency between every pair of reference sizes", () => {
    for (let n = 1; n <= 8; n++) {
      for (let m = 1; m <= n; m++) {
        const proof = consistencyProof(leaves.slice(0, n), m);
        expect(verifyConsistency(m, n, roots[m]!, roots[n]!, proof)).toBe(true);
      }
    }
  });

  it("fails inclusion when any bit of the leaf or the proof changes", () => {
    const proof = inclusionProof(leaves, 5);
    for (let bit = 0; bit < 256; bit += 7) {
      expect(verifyInclusion(flipBit(leaves[5]!, bit), 5, 8, proof, roots[8]!)).toBe(false);
      const tampered = proof.map((p, i) => (i === bit % proof.length ? flipBit(p, bit) : p));
      expect(verifyInclusion(leaves[5]!, 5, 8, tampered, roots[8]!)).toBe(false);
    }
  });

  it("fails consistency when history is rewritten", () => {
    const rewritten = [...leaves];
    rewritten[1] = leafHash(new TextEncoder().encode("forged record"));
    const proof = consistencyProof(rewritten, 3);
    expect(verifyConsistency(3, 8, roots[3]!, root(rewritten), proof)).toBe(false);
  });

  it("fails closed on malformed input instead of throwing", () => {
    expect(verifyInclusion(leaves[0]!, 8, 8, [], roots[8]!)).toBe(false);
    expect(verifyInclusion(leaves[0]!, 0, 8, [new Uint8Array(3)], roots[8]!)).toBe(false);
    expect(verifyConsistency(5, 3, roots[5]!, roots[3]!, [])).toBe(false);
    expect(verifyConsistency(8, 8, roots[8]!, roots[7]!, [])).toBe(false);
    expect(() => inclusionProof(leaves, 9)).toThrow(/outside/);
    expect(() => consistencyProof(leaves, 0)).toThrow(/first size/);
  });
});
