/**
 * The climb from a leaf to the root, as the verifier walks it, laid out as a radial tree.
 *
 * `climb` replays the RFC 9162 inclusion walk (the same bit arithmetic as
 * `verifyInclusion`) and records every hop: the hash we hold, the sibling the proof
 * supplies, which side each sits on, and the parent they make. The chart draws exactly
 * those hashes, so what the reader sees is what the verifier computed.
 *
 * `radialLayout` places the hops on concentric rings: the leaf on the outer ring, the root
 * at the centre, our path straight up, each sibling beside its partner. Pure functions,
 * unit-tested; the React component only renders the result.
 */

import { toHex } from "@/lib/verify/bytes";
import { HASH_SIZE, nodeHash } from "@/lib/verify/hashing";

export interface Hop {
  /** 0 for the leaf's own level; the root is at `hops.length`. */
  level: number;
  /** The hash we hold at this level. */
  self: Uint8Array;
  /** The sibling the proof supplies. */
  sibling: Uint8Array;
  /** Which side the sibling sits on when the two are hashed together. */
  siblingSide: "left" | "right";
  /** The parent the two make. */
  parent: Uint8Array;
}

export interface Climb {
  hops: Hop[];
  /** What the climb arrives at; equal to the signed root when the proof is good. */
  computedRoot: Uint8Array;
  /** False when the proof is malformed for this leaf index and tree size. */
  wellFormed: boolean;
}

/** Replay the inclusion walk, keeping every intermediate hash. Never throws. */
export function climb(
  leaf: Uint8Array,
  index: number,
  treeSize: number,
  proof: readonly Uint8Array[],
): Climb {
  const hops: Hop[] = [];
  const bad = (root: Uint8Array): Climb => ({ hops, computedRoot: root, wellFormed: false });
  if (!Number.isSafeInteger(index) || !Number.isSafeInteger(treeSize)) return bad(leaf);
  if (index < 0 || index >= treeSize) return bad(leaf);
  if (leaf.length !== HASH_SIZE || proof.some((p) => p.length !== HASH_SIZE)) return bad(leaf);
  let fn = BigInt(index);
  let sn = BigInt(treeSize - 1);
  let computed = leaf;
  for (const sibling of proof) {
    if (sn === 0n) return bad(computed);
    const siblingOnLeft = Boolean(fn & 1n) || fn === sn;
    const parent = siblingOnLeft ? nodeHash(sibling, computed) : nodeHash(computed, sibling);
    hops.push({
      level: hops.length,
      self: computed,
      sibling,
      siblingSide: siblingOnLeft ? "left" : "right",
      parent,
    });
    computed = parent;
    if (siblingOnLeft) {
      while (!(fn & 1n) && fn !== 0n) {
        fn >>= 1n;
        sn >>= 1n;
      }
    }
    fn >>= 1n;
    sn >>= 1n;
  }
  return { hops, computedRoot: computed, wellFormed: sn === 0n };
}

export interface Placed {
  id: string;
  x: number;
  y: number;
  /** 0 is the leaf ring; `levels` is the root. */
  level: number;
  role: "self" | "sibling" | "root";
  hash: Uint8Array;
  hex: string;
  short: string;
  /** Index into `hops` for self and sibling nodes. */
  hop: number;
}

export interface Edge {
  from: string;
  to: string;
  /** True for the two edges that meet at each parent on our path. */
  onPath: boolean;
}

export interface RadialLayout {
  nodes: Placed[];
  edges: Edge[];
  /** Ring radii from the root outward, for drawing guide rings. */
  rings: number[];
  size: number;
}

export function shortHex(bytes: Uint8Array): string {
  const hex = toHex(bytes);
  return `${hex.slice(0, 6)}…${hex.slice(-4)}`;
}

/**
 * Place a climb on rings. `size` is the drawing's width and height; the root sits at the
 * centre and the leaf on the outermost ring. Our path sweeps around the disc as it
 * climbs, and each sibling sits beside its partner on the same ring.
 */
export function radialLayout(result: Climb, size = 400): RadialLayout {
  const { hops } = result;
  const levels = hops.length;
  const cx = size / 2;
  const cy = size / 2;
  const outer = size / 2 - 56; // room for a label beyond the rim
  // Rings are spaced by the square root of the level, so the inner ones, where the climb
  // converges, get as much room as the outer ones.
  const rings = Array.from({ length: levels + 1 }, (_, k) =>
    levels === 0 ? 0 : outer * Math.sqrt((levels - k) / levels),
  );
  const nodes: Placed[] = [];
  const edges: Edge[] = [];
  const place = (
    id: string,
    level: number,
    angle: number,
    role: Placed["role"],
    hash: Uint8Array,
    hop: number,
  ): Placed => {
    const r = rings[level] ?? 0;
    const node: Placed = {
      id,
      x: cx + r * Math.sin(angle),
      y: cy - r * Math.cos(angle),
      level,
      role,
      hash,
      hex: toHex(hash),
      short: shortHex(hash),
      hop,
    };
    nodes.push(node);
    return node;
  };
  if (levels === 0) {
    place("root", 0, 0, "root", result.computedRoot, 0);
    return { nodes, edges, rings, size };
  }
  // Our path sweeps around the disc as it climbs, one step per level, so consecutive hops
  // never stack and every label has room; the leaf starts at 12 o'clock. Each sibling sits
  // beside its partner on the same ring, on the side the proof puts it.
  const step = Math.min(Math.PI / 5, (Math.PI * 1.7) / levels);
  const spread = step * 0.45;
  hops.forEach((hop, k) => {
    const angle = k * step;
    const sign = hop.siblingSide === "left" ? -1 : 1;
    place(`self-${k}`, k, angle, "self", hop.self, k);
    place(`sibling-${k}`, k, angle + sign * spread, "sibling", hop.sibling, k);
    const parentId = k + 1 === levels ? "root" : `self-${k + 1}`;
    edges.push({ from: `self-${k}`, to: parentId, onPath: true });
    edges.push({ from: `sibling-${k}`, to: parentId, onPath: true });
  });
  place("root", levels, 0, "root", result.computedRoot, levels - 1);
  return { nodes, edges, rings, size };
}
