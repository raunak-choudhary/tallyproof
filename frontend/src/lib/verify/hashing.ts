// Leaf and node hashing (RFC 9162 section 2.1.1), domain separated with 0x00 and 0x01.
import { sha256 } from "@noble/hashes/sha2.js";

import { concat } from "./bytes";

export const HASH_SIZE = 32;
export const EMPTY_ROOT = sha256(new Uint8Array());

export function leafHash(data: Uint8Array): Uint8Array {
  return sha256(concat(Uint8Array.of(0), data));
}

export function nodeHash(left: Uint8Array, right: Uint8Array): Uint8Array {
  if (left.length !== HASH_SIZE || right.length !== HASH_SIZE) {
    throw new Error(`child hashes must be ${HASH_SIZE} bytes`);
  }
  return sha256(concat(Uint8Array.of(1), left, right));
}
