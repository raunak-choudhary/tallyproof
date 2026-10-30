import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { parseVerifierKey } from "@/lib/verify/checkpoint";
import { formatCents } from "@/lib/verify/sumTree";
import { checkTotal } from "@/lib/verify/totalCheck";

import { parseTotals } from "./totals";

const read = (name: string) =>
  readFileSync(new URL(`../../../public/replay/${name}`, import.meta.url), "utf-8");

describe("the committed bundle's totals", () => {
  const totals = parseTotals(read("totals.json"));
  const key = parseVerifierKey(
    (JSON.parse(read("log-key.json")) as { verifier_key: string }).verifier_key,
  );
  const size = (JSON.parse(read("manifest.json")) as { tree_size: number }).tree_size;

  it("covers the whole bundle", () => {
    expect(totals.treeSize).toBe(size);
  });

  it("proves every total it lists, in the browser", () => {
    for (const t of totals.totals) {
      const result = checkTotal({
        totalsNote: totals.note,
        proof: t.proof,
        pinnedKey: key,
        expected: { treeSize: size, amount: formatCents(t.totalCents), count: t.count },
      });
      expect(result.ok, `${t.entity} ${t.agency ?? "(all)"}`).toBe(true);
    }
  });

  it("fails a total that was edited in the file", () => {
    const [first] = totals.totals;
    const result = checkTotal({
      totalsNote: totals.note,
      proof: first!.proof,
      pinnedKey: key,
      expected: {
        treeSize: size,
        amount: formatCents(first!.totalCents + 1n),
        count: first!.count,
      },
    });
    expect(result.steps.at(-1)).toMatchObject({ id: "values", ok: false });
  });
});
