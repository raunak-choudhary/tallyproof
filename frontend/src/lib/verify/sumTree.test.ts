import { describe, expect, it } from "vitest";

import { fromHex } from "./bytes";
import { EMPTY_ROOT } from "./hashing";
import { formatCents, type TotalProofJson, verifyTotal } from "./sumTree";
import { loadVectors } from "./vectors";

interface SumVectors {
  root_hex: string;
  total: string;
  cases: { prefix: string[]; proof: TotalProofJson; total: string; count: number }[];
  must_fail: { reason: string; proof: TotalProofJson }[];
}

const vectors = loadVectors<SumVectors>("sum_tree.json");
const root = fromHex(vectors.root_hex);

describe("total proofs, against the Python core's vectors", () => {
  it.each(vectors.cases.map((c) => [c.prefix.join(" / ") || "(everything)", c] as const))(
    "%s",
    (_, c) => {
      expect(verifyTotal(c.proof, root)).toEqual({ total: BigInt(c.total), count: c.count });
    },
  );

  it("covers an empty prefix, a missing one, and a component that is a string prefix of another", () => {
    const names = vectors.cases.map((c) => c.prefix.join("/"));
    expect(names).toContain("");
    expect(names).toContain("nothing");
    expect(names).toContain("obligations/Agency A");
    expect(names).toContain("obligations/Agency AB");
  });

  it.each(vectors.must_fail.map((c) => [c.reason, c.proof] as const))("rejects: %s", (_, proof) => {
    expect(verifyTotal(proof, root)).toBeNull();
  });

  it("rejects every honest proof against another root", () => {
    const other = fromHex(vectors.root_hex.replace(/^./, (c) => (c === "0" ? "1" : "0")));
    for (const c of vectors.cases) expect(verifyTotal(c.proof, other)).toBeNull();
  });
});

describe("malformed proofs fail without throwing", () => {
  const honest = vectors.cases[2]!.proof;

  it("rejects impossible ranges", () => {
    expect(verifyTotal({ ...honest, start: 3, end: 1 }, root)).toBeNull();
    expect(verifyTotal({ ...honest, size: -1 }, root)).toBeNull();
    expect(verifyTotal({ ...honest, end: Number.MAX_SAFE_INTEGER + 2 }, root)).toBeNull();
  });

  it("rejects bad hex, fractional amounts, and missing fields", () => {
    const pieces = honest.pieces.map((p) =>
      "leaf" in p ? { leaf: { ...p.leaf, amount: "1.5" } } : p,
    );
    expect(verifyTotal({ ...honest, pieces }, root)).toBeNull();
    expect(
      verifyTotal(
        { ...honest, pieces: [{ leaf: { key: ["a"], amount: "1", record_hash: "zz" } }] },
        root,
      ),
    ).toBeNull();
    expect(verifyTotal({ ...honest, pieces: [] }, root)).toBeNull();
  });

  it("accepts the empty tree only with no pieces", () => {
    expect(
      verifyTotal({ size: 0, prefix: ["x"], start: 0, end: 0, pieces: [] }, EMPTY_ROOT),
    ).toEqual({
      total: 0n,
      count: 0,
    });
    expect(verifyTotal({ ...honest, size: 0, start: 0, end: 0 }, EMPTY_ROOT)).toBeNull();
  });
});

describe("formatCents", () => {
  it("formats exactly, including negatives and amounts past 2^53", () => {
    expect(formatCents(-796000n)).toBe("-7960.00");
    expect(formatCents(7n)).toBe("0.07");
    expect(formatCents(9007199254740993n)).toBe("90071992547409.93");
  });
});
