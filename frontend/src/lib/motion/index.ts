/**
 * The motion foundation. Motion (the library) handles component state changes anywhere;
 * GSAP with ScrollTrigger and Lenis drive the landing story only, so both load lazily
 * and only on that route. Everything respects the reader's reduced-motion setting.
 */

/** Whether the reader asked for reduced motion. Safe to call during server rendering. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** GSAP with ScrollTrigger registered, loaded on first use so other routes never pay for it. */
export async function loadGsap() {
  const [{ gsap }, { ScrollTrigger }] = await Promise.all([
    import("gsap"),
    import("gsap/ScrollTrigger"),
  ]);
  gsap.registerPlugin(ScrollTrigger);
  return { gsap, ScrollTrigger };
}

/** Lenis smooth scrolling, loaded on first use. Returns null under reduced motion. */
export async function startSmoothScroll(): Promise<{ stop: () => void } | null> {
  if (prefersReducedMotion()) return null;
  const { default: Lenis } = await import("lenis");
  const lenis = new Lenis({ lerp: 0.1 });
  let frame = 0;
  const raf = (time: number) => {
    lenis.raf(time);
    frame = requestAnimationFrame(raf);
  };
  frame = requestAnimationFrame(raf);
  return {
    stop: () => {
      cancelAnimationFrame(frame);
      lenis.destroy();
    },
  };
}
