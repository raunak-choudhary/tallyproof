// The checks behind the Verify button, as a pure function the UI renders step by step.
// Every check runs in the browser; nothing from the server is taken as a verdict.
import { equal, toBase64, toHex, utf8 } from "./bytes";
import { canonicalize } from "./canonical";
import type { Checkpoint, VerifierKey } from "./checkpoint";
import { verifyCheckpoint } from "./checkpoint";
import { leafHash } from "./hashing";
import { inclusionProof, root, verifyInclusion } from "./merkle";

export type StepId = "signature" | "canonical" | "leaf" | "inclusion";

export interface Step {
  id: StepId;
  label: string;
  ok: boolean;
  detail: string;
}

export interface VerifyInput {
  /** The record's canonical JSON text, possibly edited by the reader. */
  canonical: string;
  leafIndex: number;
  /** Leaf hashes of the whole log as published, in order. Empty when an audit path is given. */
  publishedLeaves: readonly Uint8Array[];
  /**
   * The audit path from a live API, leaf first. When given, the browser checks this
   * path instead of building one from the published leaves. It is still only
   * trusted if it leads to the root the pinned key signed.
   */
  auditPath?: readonly Uint8Array[];
  checkpointNote: string;
  /** The key compiled into the web build: the only key this page trusts. */
  pinnedKey: VerifierKey;
}

export interface VerifyResult {
  ok: boolean;
  steps: Step[];
  checkpoint?: Checkpoint;
  computedLeafHex?: string;
}

export function verifyEvent(input: VerifyInput): VerifyResult {
  const steps: Step[] = [];
  const done = (extra: Partial<VerifyResult> = {}): VerifyResult => ({
    ok: steps.every((s) => s.ok),
    steps,
    ...extra,
  });

  let checkpoint: Checkpoint;
  try {
    checkpoint = verifyCheckpoint(input.checkpointNote, input.pinnedKey);
    steps.push({
      id: "signature",
      label: "Checkpoint signed by the pinned key",
      ok: true,
      detail: `${checkpoint.origin}, ${checkpoint.treeSize} records`,
    });
  } catch (error) {
    steps.push({
      id: "signature",
      label: "Checkpoint signed by the pinned key",
      ok: false,
      detail: error instanceof Error ? error.message : "signature check failed",
    });
    return done();
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(input.canonical);
    const recanonical = canonicalize(parsed);
    steps.push({
      id: "canonical",
      label: "Record is in canonical form",
      ok: recanonical === input.canonical,
      detail:
        recanonical === input.canonical
          ? "Re-serializing gives the same bytes"
          : "Re-serializing changes the bytes",
    });
  } catch (error) {
    steps.push({
      id: "canonical",
      label: "Record is in canonical form",
      ok: false,
      detail: error instanceof Error ? error.message : "not valid JSON",
    });
    return done({ checkpoint });
  }

  const computed = leafHash(utf8(input.canonical));
  const published = input.publishedLeaves[input.leafIndex];
  steps.push({
    id: "leaf",
    label: "Leaf hash recomputed in your browser",
    ok: true,
    detail:
      input.auditPath || (published && equal(published, computed))
        ? `${toHex(computed).slice(0, 16)}…`
        : `${toHex(computed).slice(0, 16)}… (differs from the published log)`,
  });

  const size = checkpoint.treeSize;
  const inRange =
    input.leafIndex >= 0 &&
    input.leafIndex < size &&
    (input.auditPath !== undefined || input.publishedLeaves.length >= size);
  const proof = !inRange
    ? []
    : (input.auditPath ?? inclusionProof(input.publishedLeaves.slice(0, size), input.leafIndex));
  const included =
    inRange && verifyInclusion(computed, input.leafIndex, size, proof, checkpoint.rootHash);
  steps.push({
    id: "inclusion",
    label: "Leaf reaches the signed root through its proof",
    ok: included,
    detail: included
      ? `${proof.length} sibling hashes, root ${toHex(checkpoint.rootHash).slice(0, 16)}…`
      : "The recomputed leaf does not reproduce the signed root",
  });
  return done({ checkpoint, computedLeafHex: toHex(computed) });
}

/**
 * What an attacker without the signing key can do after editing a record: rebuild
 * the tree and write the new root into the checkpoint, keeping the old signature.
 * Used by the tamper demo to show the signature check catching it.
 */
export function forgeCheckpointWithNewRoot(
  note: string,
  publishedLeaves: readonly Uint8Array[],
  leafIndex: number,
  editedCanonical: string,
): string {
  const leaves = [...publishedLeaves];
  leaves[leafIndex] = leafHash(utf8(editedCanonical));
  const separator = note.lastIndexOf("\n\n");
  const [origin, size] = note.slice(0, separator).split("\n");
  if (origin === undefined || size === undefined) return note;
  const forgedRoot = toBase64(root(leaves.slice(0, Number(size))));
  return `${origin}\n${size}\n${forgedRoot}\n${note.slice(separator + 1)}`;
}
