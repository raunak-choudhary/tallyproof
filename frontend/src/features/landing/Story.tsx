"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { buttonVariants } from "@/components/ui/Button";
import { loadGsap, prefersReducedMotion, startSmoothScroll } from "@/lib/motion";
import { cn } from "@/lib/ui/cn";

import { SCENES } from "./scenes/scenes";
import type { StoryData } from "./scenes/types";

// The landing story: seven pinned scenes, each a real mechanism drawn from the bundle's
// data, scrubbed by scrolling. Under reduced motion, or before GSAP loads, every scene
// shows its finished state as a still, so the page reads top to bottom without script.
export function Story({ data }: { data: StoryData }) {
  const root = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<"stills" | "scroll">("stills");

  useEffect(() => {
    if (prefersReducedMotion() || !root.current) return;
    let cancelled = false;
    let stopScroll: (() => void) | null = null;
    let triggers: { kill: () => void }[] = [];
    void (async () => {
      const [{ gsap, ScrollTrigger }, smooth] = await Promise.all([
        loadGsap(),
        startSmoothScroll(),
      ]);
      if (cancelled || !root.current) {
        smooth?.stop();
        return;
      }
      stopScroll = smooth?.stop ?? null;
      setMode("scroll");
      const sections = root.current.querySelectorAll<HTMLElement>("[data-scene]");
      sections.forEach((section) => {
        const spec = SCENES.find((s) => s.id === section.dataset["scene"]);
        if (!spec) return;
        const tl = gsap.timeline({ paused: true });
        spec.build(tl, section);
        triggers.push(
          ScrollTrigger.create({
            trigger: section,
            start: "top top",
            end: "+=120%",
            pin: true,
            scrub: 0.6,
            animation: tl,
          }),
        );
      });
      ScrollTrigger.refresh();
    })();
    return () => {
      cancelled = true;
      triggers.forEach((t) => t.kill());
      triggers = [];
      stopScroll?.();
    };
  }, []);

  return (
    <div ref={root} data-mode={mode} className="border-b border-border">
      <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-4 px-[var(--gutter)] py-4 text-sm text-fg-muted">
        <span>
          How it works, in {SCENES.length} scenes.{" "}
          {mode === "scroll" ? "Scroll to move each one." : ""}
        </span>
        <Link href="#records" className={cn(buttonVariants({ variant: "quiet", size: "sm" }))}>
          Skip the story
        </Link>
      </div>
      {SCENES.map((scene) => (
        <section
          key={scene.id}
          data-scene={scene.id}
          aria-labelledby={`scene-${scene.id}`}
          className={cn(
            "grid content-center gap-6 bg-bg px-[var(--gutter)] py-12",
            mode === "scroll" ? "min-h-dvh" : "",
          )}
        >
          <div className="mx-auto grid w-full max-w-[1200px] items-center gap-8 md:grid-cols-[3fr_2fr] md:gap-12">
            <div
              className="min-w-0 rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-3 [&_svg]:h-auto [&_svg]:w-full"
              style={{ boxShadow: "var(--shadow-1)" }}
            >
              <div className="[&_.script]:font-[family-name:var(--font-script)]">
                {scene.visual(data)}
              </div>
            </div>
            <div className="grid min-w-0 gap-3">
              <p className="text-xs font-semibold tracking-[0.14em] text-accent-2 uppercase">
                Scene {scene.number} · {scene.eyebrow}
              </p>
              <h2
                id={`scene-${scene.id}`}
                className="display text-[length:var(--text-2xl)] font-normal"
              >
                {scene.title}
              </h2>
              <p className="text-fg-muted">{scene.caption}</p>
              <p className="border-l-2 border-accent pl-3 text-sm text-fg-muted">
                <span className="font-medium text-fg">What this proves: </span>
                {scene.proves}
              </p>
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
