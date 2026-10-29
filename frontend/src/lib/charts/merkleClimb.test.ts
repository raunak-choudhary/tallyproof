import { sha256 } from "@noble/hashes/sha2.js";
import { describe, expect, it } from "vitest";

import { equal, utf8 } from "@/lib/verify/bytes";
import { leafHash, nodeHash } from "@/lib/verify/hashing";
import { inclusionProof, root, verifyInclusion } from "@/lib/verify/merkle";

import { climb, radialLayout, shortHex } from "./merkleClimb";

function leaves(n: number): Uint8Array[] {
  return Array.from({ length: n }, (_, i) => leafHash(utf8(`record ${i}`)));
}

describe("climb", () => {
  it("arrives at the same root as the verifier, for every leaf of every small tree", () => {
    for (let n = 1; n <= 40; n++) {
      const tree = leaves(n);
      const expected = root(tree);
      for (let i = 0; i < n; i++) {
        const proof = inclusionProof(tree, i);
        const result = climb(tree[i]!, i, n, proof);
        expect(result.wellFormed).toBe(true);
        expect(result.hops).toHaveLength(proof.length);
        expect(equal(result.computedRoot, expected)).toBe(true);
        expect(verifyInclusion(tree[i]!, i, n, proof, expected)).toBe(true);
      }
    }
  });

  it("records each hop so the parent is the hash of the two children in the stated order", () => {
    const tree = leaves(13);
    const result = climb(tree[5]!, 5, 13, inclusionProof(tree, 5));
    let held = tree[5]!;
    for (const hop of result.hops) {
      expect(equal(hop.self, held)).toBe(true);
      const parent =
        hop.siblingSide === "left"
          ? nodeHash(hop.sibling, hop.self)
          : nodeHash(hop.self, hop.sibling);
      expect(equal(hop.parent, parent)).toBe(true);
      held = hop.parent;
    }
    expect(equal(held, result.computedRoot)).toBe(true);
  });

  it("marks a malformed proof without throwing", () => {
    const tree = leaves(8);
    const proof = inclusionProof(tree, 3);
    expect(climb(tree[3]!, 3, 8, proof.slice(1)).wellFormed).toBe(false);
    expect(climb(tree[3]!, 9, 8, proof).wellFormed).toBe(false);
    expect(climb(new Uint8Array(5), 3, 8, proof).wellFormed).toBe(false);
    expect(climb(sha256(utf8("x")), 3, 8, proof).wellFormed).toBe(true); // wrong leaf, wrong root
  });

  it("a single-leaf tree has no hops and the leaf is the root", () => {
    const tree = leaves(1);
    const result = climb(tree[0]!, 0, 1, []);
    expect(result.hops).toHaveLength(0);
    expect(equal(result.computedRoot, tree[0]!)).toBe(true);
  });
});

describe("radialLayout", () => {
  it("puts the leaf on the rim, the root at the centre, and every node inside the drawing", () => {
    const tree = leaves(1000);
    const result = climb(tree[617]!, 617, 1000, inclusionProof(tree, 617));
    const layout = radialLayout(result, 400);
    const byId = new Map(layout.nodes.map((n) => [n.id, n]));
    expect(byId.get("root")).toMatchObject({ x: 200, y: 200, role: "root" });
    expect(byId.get("self-0")?.level).toBe(0);
    const dist = (id: string) => Math.hypot(byId.get(id)!.x - 200, byId.get(id)!.y - 200);
    for (let k = 1; k < result.hops.length; k++) {
      expect(dist(`self-${k}`)).toBeLessThan(dist(`self-${k - 1}`)); // each hop is nearer the centre
    }
    expect(dist("self-0")).toBeGreaterThan(130);
    for (const node of layout.nodes) {
      expect(node.x).toBeGreaterThanOrEqual(0);
      expect(node.x).toBeLessThanOrEqual(400);
      expect(node.y).toBeGreaterThanOrEqual(0);
      expect(node.y).toBeLessThanOrEqual(400);
    }
    expect(layout.nodes).toHaveLength(result.hops.length * 2 + 1);
    expect(layout.edges).toHaveLength(result.hops.length * 2);
    expect(layout.rings[0]).toBeGreaterThan(layout.rings[layout.rings.length - 1]!);
    expect(layout.rings[layout.rings.length - 1]).toBe(0);
  });

  it("keeps a sibling on the side the proof puts it", () => {
    const tree = leaves(8);
    const left = radialLayout(climb(tree[3]!, 3, 8, inclusionProof(tree, 3)));
    const right = radialLayout(climb(tree[2]!, 2, 8, inclusionProof(tree, 2)));
    const x = (l: ReturnType<typeof radialLayout>, id: string) =>
      l.nodes.find((n) => n.id === id)!.x;
    expect(x(left, "sibling-0")).toBeLessThan(x(left, "self-0")); // leaf 3's sibling is leaf 2
    expect(x(right, "sibling-0")).toBeGreaterThan(x(right, "self-0"));
  });

  it("shortens a hash in the middle", () => {
    expect(shortHex(new Uint8Array(32))).toBe("000000…0000");
  });
});
