import { describe, expect, it } from "vitest";

import { verifyTotalsNote, parseVerifierKey } from "./checkpoint";
import type { TotalProofJson } from "./sumTree";
import { formatCents } from "./sumTree";
import { checkTotal, toCents } from "./totalCheck";
import { loadVectors } from "./vectors";

interface SumVectors {
  verifier_key: string;
  totals_note: string;
  checkpoint_note_with_the_same_root: string;
  cases: { prefix: string[]; proof: TotalProofJson; total: string; count: number }[];
  must_fail: { reason: string; proof: TotalProofJson }[];
}

const v = loadVectors<SumVectors>("sum_tree.json");
const agencyA = v.cases.find((c) => c.prefix.join("/") === "obligations/Agency A")!;
const size = 13;

function input(overrides: Partial<Parameters<typeof checkTotal>[0]> = {}) {
  return {
    totalsNote: v.totals_note,
    proof: agencyA.proof,
    pinnedKey: parseVerifierKey(v.verifier_key),
    expected: {
      treeSize: size,
      amount: formatCents(BigInt(agencyA.total)),
      count: agencyA.count,
    },
    ...overrides,
  };
}

describe("checkTotal", () => {
  it("passes every step for an honest total", () => {
    const result = checkTotal(input());
    expect(result.ok).toBe(true);
    expect(result.steps.map((s) => s.id)).toEqual(["signature", "checkpoint", "proof", "values"]);
    expect(result.proven).toEqual({ total: BigInt(agencyA.total), count: agencyA.count });
  });

  it("refuses another key", () => {
    const other = { ...parseVerifierKey(v.verifier_key), keyId: new Uint8Array(4) };
    const result = checkTotal(input({ pinnedKey: other }));
    expect(result.ok).toBe(false);
    expect(result.steps.at(-1)?.id).toBe("signature");
  });

  it("refuses a checkpoint note passed off as totals", () => {
    const result = checkTotal(input({ totalsNote: v.checkpoint_note_with_the_same_root }));
    expect(result.steps.at(-1)).toMatchObject({ id: "signature", ok: false });
  });

  it("refuses totals for a different checkpoint than the answer's", () => {
    const result = checkTotal(input({ expected: { treeSize: size + 1 } }));
    expect(result.steps.at(-1)).toMatchObject({ id: "checkpoint", ok: false });
  });

  it.each(v.must_fail.map((c) => [c.reason, c.proof] as const))(
    "refuses a forged proof: %s",
    (_, proof) => {
      expect(checkTotal(input({ proof })).steps.at(-1)).toMatchObject({ id: "proof", ok: false });
    },
  );

  it("fails when the answer shows a different total or count", () => {
    const off = checkTotal(input({ expected: { treeSize: size, amount: "1.00" } }));
    expect(off.steps.at(-1)).toMatchObject({ id: "values", ok: false });
    const miscounted = checkTotal(
      input({ expected: { treeSize: size, count: agencyA.count + 1 } }),
    );
    expect(miscounted.steps.at(-1)).toMatchObject({ id: "values", ok: false });
  });

  it("reads the vector note with the vector key", () => {
    const note = verifyTotalsNote(v.totals_note, parseVerifierKey(v.verifier_key));
    expect(note.treeSize).toBe(size);
  });
});

describe("toCents", () => {
  it("reads decimal strings exactly", () => {
    expect(toCents("-7960.00")).toBe(-796000n);
    expect(toCents("12.5")).toBe(1250n);
    expect(toCents("90071992547409.93")).toBe(9007199254740993n);
    expect(toCents("1.005")).toBeNull();
    expect(toCents("abc")).toBeNull();
  });
});
