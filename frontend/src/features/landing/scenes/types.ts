import type { gsap } from "gsap";
import type { ReactNode } from "react";

/** Real data the scenes draw, computed at build time from the signed bundle. */
export interface StoryData {
  record: {
    eventId: string;
    leafIndex: number;
    agency: string;
    piid: string;
    amount: string;
    date: string;
    /** The record's canonical bytes, pretty-printed for the hash scene. */
    canonical: string;
    leafHex: string;
  };
  treeSize: number;
  /** The climb's hops, leaf first, as short hashes with the sibling side. */
  hops: { self: string; sibling: string; parent: string; side: "left" | "right" }[];
  rootHex: string;
  /** The latest signed checkpoint note, verbatim. */
  checkpointNote: string;
  /** The checkpoint an outside witness timestamped (the latest earlier one in the bundle). */
  witnessedSize: number;
}

/**
 * One scene: what it draws and how its timeline moves. `build` receives the scene's root
 * element and a GSAP timeline to add tweens to; the timeline is scrubbed by scrolling, or
 * jumped to its end under reduced motion.
 */
export interface SceneSpec {
  id: string;
  number: number;
  eyebrow: string;
  title: string;
  caption: string;
  proves: string;
  visual: (data: StoryData) => ReactNode;
  build: (tl: gsap.core.Timeline, root: HTMLElement) => void;
}
