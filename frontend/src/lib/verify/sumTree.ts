// Merkle-sum tree total proofs (ADR-0024). A port of the verifier in
// tallyproof_core/sum_tree.py, checked against the same vectors.
//
// A proof splits the tree into pieces: subtrees entirely inside the run of keys
// under a prefix, and subtrees entirely outside it. The verifier rebuilds the root,
// checking at every join that sums and counts add up and keys stay in order, then
// checks that inside pieces carry the prefix and their neighbours don't. The total
// is the sum of the inside pieces. Amounts are cents, held as BigInt so nothing
// rounds. Verification never throws: a malformed proof is a failed proof.
import { sha256 } from "@noble/hashes/sha2.js";

import { concat, equal, fromHex, utf8 } from "./bytes";
import { EMPTY_ROOT, HASH_SIZE } from "./hashing";

const SUM_LEAF_PREFIX = Uint8Array.of(2);
const SUM_NODE_PREFIX = Uint8Array.of(3);
const SEPARATOR = 0;

export interface LeafJson {
  key: string[];
  amount: string;
  record_hash: string;
}

export interface NodeJson {
  left: string;
  right: string;
  total: string;
  count: number;
  low: string[];
  high: string[];
}

export type PieceJson = { leaf: LeafJson } | { node: NodeJson };

export interface TotalProofJson {
  size: number;
  prefix: string[];
  start: number;
  end: number;
  pieces: PieceJson[];
}

export interface Proven {
  /** Cents. */
  total: bigint;
  count: number;
}

export function encodeKey(key: readonly string[]): Uint8Array {
  if (key.length === 0 || key.some((part) => part.includes("\u0000"))) {
    throw new Error("a key needs at least one component and no NUL characters");
  }
  const parts = key.map(utf8);
  const out: Uint8Array[] = [];
  parts.forEach((part, i) => {
    if (i > 0) out.push(Uint8Array.of(SEPARATOR));
    out.push(part);
  });
  return concat(...out);
}

export function encodePrefix(prefix: readonly string[]): Uint8Array {
  return prefix.length === 0
    ? new Uint8Array()
    : concat(encodeKey(prefix), Uint8Array.of(SEPARATOR));
}

function lp(data: Uint8Array): Uint8Array {
  const length = new Uint8Array(4);
  new DataView(length.buffer).setUint32(0, data.length);
  return concat(length, data);
}

function ascii(value: bigint | number): Uint8Array {
  return utf8(value.toString());
}

/** Lexicographic byte order, as Python compares bytes. */
export function compareBytes(a: Uint8Array, b: Uint8Array): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    const d = (a[i] as number) - (b[i] as number);
    if (d !== 0) return d;
  }
  return a.length - b.length;
}

function startsWith(data: Uint8Array, prefix: Uint8Array): boolean {
  if (prefix.length > data.length) return false;
  for (let i = 0; i < prefix.length; i++) if (data[i] !== prefix[i]) return false;
  return true;
}

function leafDigest(key: Uint8Array, amount: bigint, recordHash: Uint8Array): Uint8Array {
  if (recordHash.length !== HASH_SIZE) throw new Error(`record hashes are ${HASH_SIZE} bytes`);
  return sha256(concat(SUM_LEAF_PREFIX, lp(key), lp(ascii(amount)), recordHash));
}

function nodeDigest(
  left: Uint8Array,
  right: Uint8Array,
  total: bigint,
  count: number,
  low: Uint8Array,
  high: Uint8Array,
): Uint8Array {
  if (left.length !== HASH_SIZE || right.length !== HASH_SIZE) {
    throw new Error(`child hashes are ${HASH_SIZE} bytes`);
  }
  return sha256(
    concat(SUM_NODE_PREFIX, left, right, lp(ascii(total)), lp(ascii(count)), lp(low), lp(high)),
  );
}

function splitPoint(size: number): number {
  let k = 1;
  while (k * 2 < size) k *= 2;
  return k;
}

interface Built {
  digest: Uint8Array;
  total: bigint;
  count: number;
  low: Uint8Array;
  high: Uint8Array;
}

function amountOf(text: string): bigint {
  if (!/^-?(0|[1-9][0-9]*)$/.test(text)) throw new Error("amounts are whole numbers of cents");
  return BigInt(text);
}

/** Check a total proof against a signed sum root; null if anything fails. */
export function verifyTotal(proof: TotalProofJson, root: Uint8Array): Proven | null {
  try {
    return verify(proof, root);
  } catch {
    return null;
  }
}

function verify(proof: TotalProofJson, root: Uint8Array): Proven | null {
  const { size, start, end } = proof;
  if (![size, start, end].every(Number.isSafeInteger)) return null;
  if (size < 0 || start < 0 || start > end || end > size) return null;
  if (size === 0)
    return equal(root, EMPTY_ROOT) && proof.pieces.length === 0 ? { total: 0n, count: 0 } : null;
  const prefix = encodePrefix(proof.prefix);
  let next = 0;
  let total = 0n;
  let count = 0;
  const bounds = new Map<number, Built>();

  const take = (a: number, b: number): Built => {
    const piece = proof.pieces[next++];
    if (piece === undefined) throw new Error("too few pieces");
    if ("leaf" in piece) {
      if (b - a !== 1) throw new Error("a leaf piece where a subtree belongs");
      const key = encodeKey(piece.leaf.key);
      const amount = amountOf(piece.leaf.amount);
      return {
        digest: leafDigest(key, amount, fromHex(piece.leaf.record_hash)),
        total: amount,
        count: 1,
        low: key,
        high: key,
      };
    }
    const node = piece.node;
    if (b - a < 2 || node.count !== b - a) throw new Error("a subtree piece of the wrong size");
    const low = encodeKey(node.low);
    const high = encodeKey(node.high);
    if (compareBytes(low, high) > 0) throw new Error("smallest key above largest");
    const nodeTotal = amountOf(node.total);
    return {
      digest: nodeDigest(fromHex(node.left), fromHex(node.right), nodeTotal, node.count, low, high),
      total: nodeTotal,
      count: node.count,
      low,
      high,
    };
  };

  const rebuild = (a: number, b: number): Built => {
    const inside = start <= a && b <= end;
    const outside = b <= start || a >= end;
    if (b - a === 1 || inside || outside) {
      const built = take(a, b);
      if (inside && start < end) {
        if (!startsWith(built.low, prefix) || !startsWith(built.high, prefix)) {
          throw new Error("an inside piece has a key outside the prefix");
        }
        total += built.total;
        count += built.count;
      }
      bounds.set(a, built);
      return built;
    }
    const k = splitPoint(b - a);
    const left = rebuild(a, a + k);
    const right = rebuild(a + k, b);
    if (compareBytes(left.high, right.low) > 0) throw new Error("keys out of order");
    const sum = left.total + right.total;
    const n = left.count + right.count;
    return {
      digest: nodeDigest(left.digest, right.digest, sum, n, left.low, right.high),
      total: sum,
      count: n,
      low: left.low,
      high: right.high,
    };
  };

  const top = rebuild(0, size);
  if (next !== proof.pieces.length || !equal(top.digest, root)) return null;
  if (prefix.length > 0) {
    if (start > 0) {
      const before = [...bounds.entries()].find(
        ([a, p]) => a < start && a + p.count === start,
      )?.[1];
      if (!before || startsWith(before.high, prefix) || compareBytes(before.high, prefix) > 0)
        return null;
    }
    if (end < size) {
      const after = bounds.get(end);
      if (!after || startsWith(after.low, prefix) || compareBytes(after.low, prefix) < 0)
        return null;
    }
  }
  return { total, count };
}

/** Cents as a dollar string, exactly: -796000n becomes "-7960.00". */
export function formatCents(cents: bigint): string {
  const sign = cents < 0n ? "-" : "";
  const abs = cents < 0n ? -cents : cents;
  return `${sign}${(abs / 100n).toString()}.${(abs % 100n).toString().padStart(2, "0")}`;
}
