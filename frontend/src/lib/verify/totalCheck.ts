// The checks behind "Verify the total", as a pure function the UI renders step by step.
// The server's own claim about the total is never used: the browser derives it from
// the proof and compares it with what the answer shows.
import type { TotalsNote, VerifierKey } from "./checkpoint";
import { verifyTotalsNote } from "./checkpoint";
import type { Proven, TotalProofJson } from "./sumTree";
import { formatCents, verifyTotal } from "./sumTree";

export type TotalStepId = "signature" | "checkpoint" | "proof" | "values";

export interface TotalStep {
  id: TotalStepId;
  label: string;
  ok: boolean;
  detail: string;
}

export interface TotalCheckInput {
  totalsNote: string;
  proof: TotalProofJson;
  pinnedKey: VerifierKey;
  expected: {
    /** The checkpoint the answer was pinned to. */
    treeSize: number;
    /** The total the answer shows, as a decimal string, if it shows one. */
    amount?: string;
    /** The number of records the answer shows, if it shows one. */
    count?: number;
  };
}

export interface TotalCheckResult {
  ok: boolean;
  steps: TotalStep[];
  proven: Proven | null;
}

/** Cents from a decimal string such as "-7960.00"; null if it has fractions of a cent. */
export function toCents(amount: string): bigint | null {
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(amount.trim());
  if (!match) return null;
  const [, sign, whole, fraction = ""] = match;
  const cents = BigInt(whole as string) * 100n + BigInt(fraction.padEnd(2, "0"));
  return sign ? -cents : cents;
}

export function checkTotal(input: TotalCheckInput): TotalCheckResult {
  const steps: TotalStep[] = [];
  const fail = (id: TotalStepId, label: string, detail: string): TotalCheckResult => {
    steps.push({ id, label, ok: false, detail });
    return { ok: false, steps, proven: null };
  };

  let note: TotalsNote;
  try {
    note = verifyTotalsNote(input.totalsNote, input.pinnedKey);
  } catch (caught: unknown) {
    const reason = caught instanceof Error ? caught.message : String(caught);
    return fail("signature", "Signed with the pinned key", reason);
  }
  steps.push({
    id: "signature",
    label: "Signed with the pinned key",
    ok: true,
    detail: `Totals for checkpoint ${note.treeSize.toLocaleString("en-US")}, signed by ${note.origin}.`,
  });

  if (note.treeSize !== input.expected.treeSize) {
    return fail(
      "checkpoint",
      "For the answer's checkpoint",
      `The answer is pinned to checkpoint ${input.expected.treeSize}, the totals to ${note.treeSize}.`,
    );
  }
  steps.push({
    id: "checkpoint",
    label: "For the answer's checkpoint",
    ok: true,
    detail: `Both are checkpoint ${note.treeSize.toLocaleString("en-US")}.`,
  });

  const proven = verifyTotal(input.proof, note.rootHash);
  if (!proven) {
    return fail(
      "proof",
      "The proof rebuilds the signed root",
      "The pieces don't add up to the signed tree.",
    );
  }
  steps.push({
    id: "proof",
    label: "The proof rebuilds the signed root",
    ok: true,
    detail: `${input.proof.pieces.length} pieces, no records needed: ${proven.count.toLocaleString("en-US")} records totalling ${formatCents(proven.total)}.`,
  });

  const { amount, count } = input.expected;
  const shown = amount === undefined ? null : toCents(amount);
  if (amount !== undefined && shown !== proven.total) {
    return fail(
      "values",
      "Matches the answer",
      `The answer shows ${amount}; the proof gives ${formatCents(proven.total)}.`,
    );
  }
  if (count !== undefined && count !== proven.count) {
    return fail(
      "values",
      "Matches the answer",
      `The answer counts ${count} records; the proof gives ${proven.count}.`,
    );
  }
  steps.push({
    id: "values",
    label: "Matches the answer",
    ok: true,
    detail: "The total and the number of records shown are the ones the proof establishes.",
  });
  return { ok: true, steps, proven };
}
