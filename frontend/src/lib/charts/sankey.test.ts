import { describe, expect, it } from "vitest";

import { compactUsd, naicsSector, OTHER, sankeyLayout } from "./sankey";

const rows = [
  { agency: "Veterans Affairs", sector: "Health care", amount: 900 },
  { agency: "Veterans Affairs", sector: "Manufacturing", amount: 300 },
  { agency: "Defense", sector: "Manufacturing", amount: 500 },
  { agency: "Agriculture", sector: "Agriculture", amount: 20 },
  { agency: "Treasury", sector: "Information", amount: 10 },
  { agency: "Defense", sector: "Construction", amount: -40 },
];

describe("spending sankey", () => {
  const box = { width: 600, height: 300 };

  it("keeps the largest agencies and sectors and folds the rest into Other", () => {
    const { nodes } = sankeyLayout(rows, box, { agencies: 2, sectors: 2 });
    const agencies = nodes.filter((n) => n.side === "agency").map((n) => n.name);
    const sectors = nodes.filter((n) => n.side === "sector").map((n) => n.name);
    expect(agencies.sort()).toEqual(["Defense", OTHER, "Veterans Affairs"].sort());
    expect(sectors.sort()).toEqual(["Health care", "Manufacturing", OTHER].sort());
  });

  it("conserves the money: what leaves the agencies reaches the sectors", () => {
    const { nodes, links } = sankeyLayout(rows, box);
    const total = links.reduce((s, l) => s + l.value, 0);
    expect(total).toBe(1730);
    const out = nodes.filter((n) => n.side === "agency").reduce((s, n) => s + n.value, 0);
    const into = nodes.filter((n) => n.side === "sector").reduce((s, n) => s + n.value, 0);
    expect(out).toBe(total);
    expect(into).toBe(total);
  });

  it("draws agencies on the left and sectors on the right, inside the box", () => {
    const { nodes, links } = sankeyLayout(rows, box);
    for (const n of nodes) {
      expect(n.y0).toBeGreaterThanOrEqual(0);
      expect(n.y1).toBeLessThanOrEqual(box.height);
      expect(n.side === "agency" ? n.x0 < 50 : n.x1 > 550).toBe(true);
    }
    expect(links.every((l) => l.path.startsWith("M"))).toBe(true);
  });

  it("writes compact dollars the same way everywhere", () => {
    expect(compactUsd(40_912_345)).toBe("$40.9M");
    expect(compactUsd(223_700_000)).toBe("$224M");
    expect(compactUsd(1_000)).toBe("$1K");
    expect(compactUsd(-2_500)).toBe("-$2.5K");
    expect(compactUsd(950)).toBe("$950");
  });

  it("names NAICS sectors by their first two digits", () => {
    expect(naicsSector("334516")).toBe("Manufacturing");
    expect(naicsSector("621111")).toBe("Health care");
    expect(naicsSector(undefined)).toBe("Unclassified");
  });
});
