// C2SP signed-note and tlog-checkpoint verification with Ed25519 (strict RFC 8032).
// Signature lines must start with an em dash (U+2014) and a space: the format requires
// that exact character, an explicit exception to the project's writing rules.
import * as ed from "@noble/ed25519";
import { sha256, sha512 } from "@noble/hashes/sha2.js";

import { concat, equal, fromBase64, toHex, utf8 } from "./bytes";
import { HASH_SIZE } from "./hashing";

ed.hashes.sha512 = sha512;

const SIGNATURE_TYPE_ED25519 = 0x01;
const SIGNATURE_LINE_PREFIX = "— ";
const MAX_SIGNATURES = 100;
const DECIMAL = /^(0|[1-9][0-9]*)$/;

export class CheckpointError extends Error {}

export interface Checkpoint {
  origin: string;
  treeSize: number;
  rootHash: Uint8Array;
}

export interface VerifierKey {
  name: string;
  keyId: Uint8Array;
  publicKey: Uint8Array;
}

function keyId(name: string, publicKey: Uint8Array): Uint8Array {
  return sha256(concat(utf8(name), Uint8Array.of(0x0a, SIGNATURE_TYPE_ED25519), publicKey)).slice(
    0,
    4,
  );
}

function checkKeyName(name: string): void {
  if (!name || /[\s+]/u.test(name)) throw new CheckpointError(`invalid key name ${name}`);
}

/** Parse a verifier key: name+hex(key ID)+base64(0x01 || public key). */
export function parseVerifierKey(vkey: string): VerifierKey {
  const parts = vkey.split("+");
  if (parts.length !== 3) throw new CheckpointError("verifier key must have three parts");
  const [name, idHex, materialB64] = parts as [string, string, string];
  checkKeyName(name);
  const material = fromBase64(materialB64);
  if (material.length !== 33 || material[0] !== SIGNATURE_TYPE_ED25519) {
    throw new CheckpointError("verifier key is not an Ed25519 key");
  }
  const publicKey = material.slice(1);
  const id = keyId(name, publicKey);
  if (toHex(id) !== idHex) throw new CheckpointError("verifier key ID does not match the key");
  return { name, keyId: id, publicKey };
}

/** Verify a signed note and return its text. Unknown keys' signatures are ignored. */
export function verifyNote(note: string, key: VerifierKey): string {
  if (/[\u0000-\u0009\u000b-\u001f]/.test(note)) {
    throw new CheckpointError("notes must not contain control characters other than newline");
  }
  const separator = note.lastIndexOf("\n\n");
  if (separator === -1 || !note.endsWith("\n"))
    throw new CheckpointError("note has no signature block");
  const text = note.slice(0, separator + 1);
  const lines = note.slice(separator + 2, -1).split("\n");
  if (lines.length > MAX_SIGNATURES) throw new CheckpointError("note has too many signatures");

  let verified = false;
  for (const line of lines) {
    if (!line.startsWith(SIGNATURE_LINE_PREFIX))
      throw new CheckpointError("malformed signature line");
    const rest = line.slice(SIGNATURE_LINE_PREFIX.length);
    const space = rest.indexOf(" ");
    const name = rest.slice(0, space);
    const blob = fromBase64(rest.slice(space + 1));
    if (blob.length < 5) throw new CheckpointError("signature is too short");
    if (name !== key.name || !equal(blob.slice(0, 4), key.keyId)) continue;
    if (!ed.verify(blob.slice(4), utf8(text), key.publicKey, { zip215: false })) {
      throw new CheckpointError("signature from the trusted key does not verify");
    }
    verified = true;
  }
  if (!verified) throw new CheckpointError("note is not signed by the trusted key");
  return text;
}

/** Parse checkpoint note text: origin, tree size, and base64 root, each on a line. */
export function parseCheckpoint(text: string): Checkpoint {
  const lines = text.split("\n");
  if (lines.length !== 4 || lines[3] !== "") {
    throw new CheckpointError("checkpoint must have exactly origin, size, and root lines");
  }
  const [origin, size, root] = lines as [string, string, string];
  if (!origin) throw new CheckpointError("origin must be one non-empty line");
  if (!DECIMAL.test(size))
    throw new CheckpointError("tree size must be a decimal without leading zeros");
  const treeSize = Number(size);
  if (!Number.isSafeInteger(treeSize)) throw new CheckpointError("tree size is too large");
  const rootHash = fromBase64(root);
  if (rootHash.length !== HASH_SIZE)
    throw new CheckpointError(`root hash must be ${HASH_SIZE} bytes`);
  return { origin, treeSize, rootHash };
}

export function verifyCheckpoint(note: string, key: VerifierKey): Checkpoint {
  return parseCheckpoint(verifyNote(note, key));
}
