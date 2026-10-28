// Merkle log roots, inclusion proofs, and consistency proofs (RFC 9162 section 2.1).
// A line-for-line port of tallyproof_core/merkle.py, checked against the same vectors.
// Verification never throws: a malformed proof is a failed proof.
import { equal } from "./bytes";
import { EMPTY_ROOT, HASH_SIZE, nodeHash } from "./hashing";

function splitPoint(size: number): number {
  let k = 1;
  while (k * 2 < size) k *= 2;
  return k;
}

export function root(leaves: readonly Uint8Array[]): Uint8Array {
  if (leaves.length === 0) return EMPTY_ROOT;
  if (leaves.length === 1) return leaves[0] as Uint8Array;
  const k = splitPoint(leaves.length);
  return nodeHash(root(leaves.slice(0, k)), root(leaves.slice(k)));
}

export function inclusionProof(leaves: readonly Uint8Array[], index: number): Uint8Array[] {
  if (!Number.isInteger(index) || index < 0 || index >= leaves.length) {
    throw new Error(`index ${index} is outside a tree of size ${leaves.length}`);
  }
  if (leaves.length === 1) return [];
  const k = splitPoint(leaves.length);
  return index < k
    ? [...inclusionProof(leaves.slice(0, k), index), root(leaves.slice(k))]
    : [...inclusionProof(leaves.slice(k), index - k), root(leaves.slice(0, k))];
}

export function verifyInclusion(
  leaf: Uint8Array,
  index: number,
  treeSize: number,
  proof: readonly Uint8Array[],
  expectedRoot: Uint8Array,
): boolean {
  if (!Number.isSafeInteger(index) || !Number.isSafeInteger(treeSize)) return false;
  if (index < 0 || index >= treeSize) return false;
  if (leaf.length !== HASH_SIZE || proof.some((p) => p.length !== HASH_SIZE)) return false;
  // BigInt keeps the bit arithmetic exact for any tree size up to 2^53.
  let fn = BigInt(index);
  let sn = BigInt(treeSize - 1);
  let computed = leaf;
  for (const sibling of proof) {
    if (sn === 0n) return false;
    if (fn & 1n || fn === sn) {
      computed = nodeHash(sibling, computed);
      while (!(fn & 1n) && fn !== 0n) {
        fn >>= 1n;
        sn >>= 1n;
      }
    } else {
      computed = nodeHash(computed, sibling);
    }
    fn >>= 1n;
    sn >>= 1n;
  }
  return sn === 0n && equal(computed, expectedRoot);
}

function subproof(m: number, leaves: readonly Uint8Array[], complete: boolean): Uint8Array[] {
  if (m === leaves.length) return complete ? [] : [root(leaves)];
  const k = splitPoint(leaves.length);
  return m <= k
    ? [...subproof(m, leaves.slice(0, k), complete), root(leaves.slice(k))]
    : [...subproof(m - k, leaves.slice(k), false), root(leaves.slice(0, k))];
}

export function consistencyProof(leaves: readonly Uint8Array[], firstSize: number): Uint8Array[] {
  if (!Number.isInteger(firstSize) || firstSize < 1 || firstSize > leaves.length) {
    throw new Error(`first size ${firstSize} must be between 1 and ${leaves.length}`);
  }
  return subproof(firstSize, leaves, true);
}

export function verifyConsistency(
  firstSize: number,
  secondSize: number,
  firstRoot: Uint8Array,
  secondRoot: Uint8Array,
  proof: readonly Uint8Array[],
): boolean {
  if (!Number.isSafeInteger(firstSize) || !Number.isSafeInteger(secondSize)) return false;
  if (firstSize < 1 || firstSize > secondSize) return false;
  if (proof.some((p) => p.length !== HASH_SIZE)) return false;
  if (firstSize === secondSize) return proof.length === 0 && equal(firstRoot, secondRoot);
  if (proof.length === 0) return false;

  const path = [...proof];
  if ((firstSize & (firstSize - 1)) === 0) path.unshift(firstRoot);
  let fn = BigInt(firstSize - 1);
  let sn = BigInt(secondSize - 1);
  while (fn & 1n) {
    fn >>= 1n;
    sn >>= 1n;
  }
  let fr = path[0] as Uint8Array;
  let sr = fr;
  for (const sibling of path.slice(1)) {
    if (sn === 0n) return false;
    if (fn & 1n || fn === sn) {
      fr = nodeHash(sibling, fr);
      sr = nodeHash(sibling, sr);
      while (!(fn & 1n) && fn !== 0n) {
        fn >>= 1n;
        sn >>= 1n;
      }
    } else {
      sr = nodeHash(sr, sibling);
    }
    fn >>= 1n;
    sn >>= 1n;
  }
  return sn === 0n && equal(fr, firstRoot) && equal(sr, secondRoot);
}
