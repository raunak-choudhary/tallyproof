// The checks behind the Verify button, as a pure function the UI renders step by step.
// Every check runs in the browser; nothing from the server is taken as a verdict.
import { equal, toBase64, toHex, utf8 } from "./bytes";
import { canonicalize } from "./canonical";
import type { Checkpoint, VerifierKey } from "./checkpoint";
import { verifyCheckpoint } from "./checkpoint";
import { leafHash } from "./hashing";
import {
  consistencyProof,
  inclusionProof,
  root,
  verifyConsistency,
  verifyInclusion,
} from "./merkle";

export type StepId =
  "signature" | "canonical" | "leaf" | "inclusion" | "witness" | "values" | "match";

/** What a citation claims about the record it points to. */
export interface Expected {
  eventId: string;
  leafIndex: number;
  /** The checkpoint the answer was pinned to. */
  treeSize: number;
  /** Text the answer quoted from this record, which must appear in its `payload.text`. */
  quote?: string;
}

export interface Step {
  id: StepId;
  label: string;
  ok: boolean;
  detail: string;
}

/** A checkpoint someone outside witnessed, fetched from a different origin than the bundle. */
export interface Witness {
  note: string;
  /** Where it came from, shown to the reader, for example raw.githubusercontent.com. */
  source: string;
  /** A consistency proof from a live API; otherwise it is built from the published leaves. */
  consistency?: readonly Uint8Array[];
}

/** A value the page shows from this record, and where it sits in the record. */
export interface Displayed {
  label: string;
  path: readonly string[];
  value: string;
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
  /**
   * When checking a citation: the event, leaf, and checkpoint it names. A valid proof
   * for some other record, leaf, or checkpoint then fails instead of passing.
   */
  expected?: Expected;
  /**
   * The outside witness. When given, the signed checkpoint must extend the witnessed one
   * (or be extended by it): a consistency proof between their roots has to verify, so a
   * history rewritten with a stolen key fails here.
   */
  witness?: Witness | { error: string; source: string };
  /** Values the page displays from this record; each must match the verified bytes. */
  displayed?: readonly Displayed[];
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
  if (input.witness) steps.push(witnessStep(input.witness, checkpoint, input));
  if (input.displayed?.length) steps.push(valuesStep(input.displayed, parsed));
  if (input.expected) steps.push(matchStep(input.expected, parsed, input.leafIndex, size));
  return done({ checkpoint, computedLeafHex: toHex(computed) });
}

const WITNESS_LABEL = "Consistent with the outside witness";

function witnessStep(
  witness: NonNullable<VerifyInput["witness"]>,
  checkpoint: Checkpoint,
  input: VerifyInput,
): Step {
  const fail = (detail: string): Step => ({
    id: "witness",
    label: WITNESS_LABEL,
    ok: false,
    detail,
  });
  if ("error" in witness) return fail(`Couldn't fetch it from ${witness.source}: ${witness.error}`);
  let witnessed: Checkpoint;
  try {
    witnessed = verifyCheckpoint(witness.note, input.pinnedKey);
  } catch (error) {
    return fail(
      `The witnessed checkpoint from ${witness.source} isn't signed by the pinned key: ${
        error instanceof Error ? error.message : "signature check failed"
      }`,
    );
  }
  if (witnessed.origin !== checkpoint.origin)
    return fail(`The witness is for log ${witnessed.origin}, not ${checkpoint.origin}`);
  const [first, second] =
    witnessed.treeSize <= checkpoint.treeSize ? [witnessed, checkpoint] : [checkpoint, witnessed];
  const proof =
    witness.consistency ??
    (input.publishedLeaves.length >= second.treeSize
      ? consistencyProof(input.publishedLeaves.slice(0, second.treeSize), first.treeSize)
      : null);
  if (proof === null) return fail("No consistency proof is available for these two sizes");
  const ok = verifyConsistency(
    first.treeSize,
    second.treeSize,
    first.rootHash,
    second.rootHash,
    proof,
  );
  return {
    id: "witness",
    label: WITNESS_LABEL,
    ok,
    detail: ok
      ? `Checkpoint ${witnessed.treeSize.toLocaleString("en-US")}, fetched from ${witness.source}, is a prefix of this log (${proof.length} hashes)`
      : `This log does not extend checkpoint ${witnessed.treeSize.toLocaleString("en-US")} witnessed at ${witness.source}: history was rewritten`,
  };
}

function valuesStep(displayed: readonly Displayed[], record: unknown): Step {
  const mismatched = displayed.filter((d) => {
    let at: unknown = record;
    for (const key of d.path)
      at = at && typeof at === "object" ? (at as Record<string, unknown>)[key] : undefined;
    return at === undefined || String(at) !== d.value;
  });
  return {
    id: "values",
    label: "Values on this page match the verified bytes",
    ok: mismatched.length === 0,
    detail:
      mismatched.length === 0
        ? displayed.map((d) => d.label.toLowerCase()).join(", ")
        : `The page's ${mismatched.map((d) => d.label.toLowerCase()).join(", ")} ${
            mismatched.length > 1 ? "don't" : "doesn't"
          } match the verified record`,
  };
}

function matchStep(expected: Expected, record: unknown, leafIndex: number, size: number): Step {
  const fields = (record ?? {}) as { event_id?: unknown; payload?: { text?: unknown } };
  const problems: string[] = [];
  if (fields.event_id !== expected.eventId)
    problems.push(`the record is ${String(fields.event_id)}`);
  if (leafIndex !== expected.leafIndex) problems.push(`the proof is for leaf ${leafIndex}`);
  if (size !== expected.treeSize) problems.push(`the checkpoint has ${size} records`);
  if (expected.quote !== undefined) {
    const text = fields.payload?.text;
    if (typeof text !== "string" || !text.includes(expected.quote))
      problems.push("the quoted text isn't in the record");
  }
  return {
    id: "match",
    label:
      expected.quote === undefined
        ? "Proof is for the cited record"
        : "Quote is in the cited record",
    ok: problems.length === 0,
    detail:
      problems.length === 0
        ? `${expected.eventId}, leaf ${expected.leafIndex}, checkpoint ${expected.treeSize}`
        : `Expected ${expected.eventId} at leaf ${expected.leafIndex}, checkpoint ${expected.treeSize}, but ${problems.join(", ")}`,
  };
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
