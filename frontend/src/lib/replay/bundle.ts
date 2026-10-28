// Loads the signed replay bundle and checks it as a whole before anything in it is used.
import { sha256 } from "@noble/hashes/sha2.js";

import { toHex, utf8 } from "@/lib/verify/bytes";
import type { VerifierKey } from "@/lib/verify/checkpoint";
import { verifyNote } from "@/lib/verify/checkpoint";
import { leafHash } from "@/lib/verify/hashing";

export interface BundleRecord {
  leafIndex: number;
  eventId: string;
  canonical: string;
}

export interface Bundle {
  records: BundleRecord[];
  leaves: Uint8Array[];
  latestCheckpointNote: string;
  manifest: { origin: string; tree_size: number; root_hash_hex: string };
}

export class BundleError extends Error {}

async function fetchText(base: string, name: string): Promise<string> {
  const response = await fetch(`${base}/${name}`);
  if (!response.ok) throw new BundleError(`could not load ${name} (${response.status})`);
  return response.text();
}

/**
 * Fetch the bundle, check the manifest's signature against the pinned key, and check
 * every file against the manifest's hashes. Throws if anything does not match.
 */
export async function loadBundle(base: string, pinnedKey: VerifierKey): Promise<Bundle> {
  const [manifestText, signature] = await Promise.all([
    fetchText(base, "manifest.json"),
    fetchText(base, "manifest.sig"),
  ]);
  const signedText = verifyNote(signature, pinnedKey);
  const manifestHash = toHex(sha256(utf8(manifestText)));
  if (!signedText.includes(`manifest sha256 ${manifestHash}`)) {
    throw new BundleError("the manifest does not match its signature");
  }
  const manifest = JSON.parse(manifestText) as Bundle["manifest"] & {
    files: Record<string, string>;
  };
  const [eventsText, checkpointsText] = await Promise.all([
    fetchText(base, "events.jsonl"),
    fetchText(base, "checkpoints.jsonl"),
  ]);
  for (const [name, text] of [
    ["events.jsonl", eventsText],
    ["checkpoints.jsonl", checkpointsText],
  ] as const) {
    if (toHex(sha256(utf8(text))) !== manifest.files[name]) {
      throw new BundleError(`${name} does not match the signed manifest`);
    }
  }
  const records = eventsText
    .trim()
    .split("\n")
    .map((line) => {
      const raw = JSON.parse(line) as { leaf_index: number; event_id: string; canonical: string };
      return { leafIndex: raw.leaf_index, eventId: raw.event_id, canonical: raw.canonical };
    });
  const checkpoints = checkpointsText
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as { tree_size: number; note: string });
  const latest = checkpoints.at(-1);
  if (!latest) throw new BundleError("the bundle has no checkpoints");
  return {
    records,
    leaves: records.map((r) => leafHash(utf8(r.canonical))),
    latestCheckpointNote: latest.note,
    manifest,
  };
}
