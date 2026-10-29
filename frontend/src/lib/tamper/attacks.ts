/**
 * The tamper ladder: four attacks on one record, each carried out in the browser against
 * the signed bundle, and the check that catches each. Pure functions; the page renders.
 *
 * 1. Edit a value: the record's bytes change, so its leaf no longer reaches the root.
 * 2. Replace the leaf: the attacker publishes a rebuilt log with the edited record's real
 *    leaf, but the signed root still commits to the old one.
 * 3. Rewrite the tree: the attacker rebuilds the tree and writes the new root into the
 *    checkpoint, but can't sign it; the signature check fails against the pinned key.
 * 4. Steal the key: the attacker signs the rewritten history for real. Every check on the
 *    record passes, so the browser turns to the witness: a consistency proof from the
 *    checkpoint an outside party timestamped to the rewritten log, which fails.
 */

import { canonicalize } from "@/lib/verify/canonical";
import type { Checkpoint, VerifierKey } from "@/lib/verify/checkpoint";
import { verifyCheckpoint } from "@/lib/verify/checkpoint";
import { leafHash } from "@/lib/verify/hashing";
import { consistencyProof, root, verifyConsistency } from "@/lib/verify/merkle";
import { utf8 } from "@/lib/verify/bytes";
import { forgeCheckpointWithNewRoot } from "@/lib/verify/verifyEvent";

export type Level = 1 | 2 | 3 | 4;

export interface Attack {
  level: Level;
  title: string;
  /** What the attacker does, in a sentence. */
  does: string;
  /** What catches it. */
  caught: string;
}

export const ATTACKS: readonly Attack[] = [
  {
    level: 1,
    title: "Edit a value",
    does: "Change the amount in the record and present it as the original.",
    caught: "The leaf hash of the edited bytes no longer reaches the signed root.",
  },
  {
    level: 2,
    title: "Replace the leaf",
    does: "Recompute the leaf for the edited record and publish a log that contains it.",
    caught: "The rebuilt tree's root does not match the one the checkpoint signed.",
  },
  {
    level: 3,
    title: "Rewrite the tree",
    does: "Rebuild the whole tree around the edit and write the new root into the checkpoint.",
    caught: "The checkpoint's signature fails against the key pinned in this page.",
  },
  {
    level: 4,
    title: "Steal the key",
    does: "Sign the rewritten history with the real key, so every check on the record passes.",
    caught:
      "The consistency proof from a checkpoint an outside witness timestamped to the rewritten log fails: the two histories disagree about the past.",
  },
];

export interface Staged {
  /** The record's bytes as the attacker presents them. */
  canonical: string;
  /** The log as the attacker publishes it. */
  leaves: Uint8Array[];
  /** The checkpoint note as the attacker presents it. */
  note: string;
  /** For level 4: the signature is taken as valid, to stand in for a stolen key. */
  assumeSigned: boolean;
}

/** The record with its amount changed, in canonical form. */
export function withAmount(canonical: string, amount: string): string {
  const record = JSON.parse(canonical) as { payload: Record<string, unknown> };
  return canonicalize({ ...record, payload: { ...record.payload, amount } });
}

/** Stage one attack on the record at `leafIndex`. */
export function stage(
  level: Level,
  original: string,
  leafIndex: number,
  leaves: readonly Uint8Array[],
  latestNote: string,
  editedAmount: string,
): Staged {
  const canonical = withAmount(original, editedAmount);
  if (level === 1) return { canonical, leaves: [...leaves], note: latestNote, assumeSigned: false };
  const rebuilt = leaves.map((l, i) => (i === leafIndex ? leafHash(utf8(canonical)) : l));
  if (level === 2) return { canonical, leaves: rebuilt, note: latestNote, assumeSigned: false };
  const forged = forgeCheckpointWithNewRoot(latestNote, leaves, leafIndex, canonical);
  return { canonical, leaves: rebuilt, note: forged, assumeSigned: level === 4 };
}

export interface WitnessCheck {
  /** The earlier, witnessed checkpoint's size. */
  firstSize: number;
  /** The log size the attacker presents. */
  secondSize: number;
  ok: boolean;
  detail: string;
}

/**
 * Level 4's catch: take the latest checkpoint an outside witness timestamped (any earlier
 * one in the bundle stands in), build the consistency proof from the attacker's log, and
 * check it against the witnessed root. The rewritten prefix can't be made consistent.
 */
export function witnessCheck(
  witnessed: Checkpoint,
  attackedLeaves: readonly Uint8Array[],
): WitnessCheck {
  const secondSize = attackedLeaves.length;
  if (witnessed.treeSize > secondSize) {
    return {
      firstSize: witnessed.treeSize,
      secondSize,
      ok: false,
      detail: "the witnessed checkpoint is larger than the log presented",
    };
  }
  const proof = consistencyProof(attackedLeaves, witnessed.treeSize);
  const secondRoot = root(attackedLeaves);
  const ok = verifyConsistency(
    witnessed.treeSize,
    secondSize,
    witnessed.rootHash,
    secondRoot,
    proof,
  );
  return {
    firstSize: witnessed.treeSize,
    secondSize,
    ok,
    detail: ok
      ? `the log at ${secondSize} extends the witnessed log at ${witnessed.treeSize}`
      : `the log at ${secondSize} does not extend the witnessed log at ${witnessed.treeSize}: a record before leaf ${witnessed.treeSize} was changed`,
  };
}

/** The earlier checkpoint that stands in for the witnessed one: the latest below `size`. */
export function witnessedBefore(
  checkpoints: readonly { treeSize: number; note: string }[],
  size: number,
  key: VerifierKey,
): Checkpoint | null {
  const earlier = checkpoints
    .filter((c) => c.treeSize < size)
    .sort((a, b) => b.treeSize - a.treeSize);
  for (const c of earlier) {
    try {
      return verifyCheckpoint(c.note, key);
    } catch {
      continue;
    }
  }
  return null;
}
