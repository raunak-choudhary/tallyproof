"use client";

import { Palette as PaletteIcon } from "lucide-react";
import { useSyncExternalStore } from "react";

import type { Palette } from "@/lib/ui/palette";
import { isPalette, nextPalette, PALETTE_KEY, paletteAttribute } from "@/lib/ui/palette";

const LABEL: Record<Palette, string> = {
  ink: "Ink and Ultraviolet palette",
  midnight: "Midnight and Gold palette",
};
const CHANGED = "tallyproof-palette-changed";

function readPalette(): Palette {
  try {
    const saved = localStorage.getItem(PALETTE_KEY);
    return isPalette(saved) ? saved : "ink";
  } catch {
    return "ink";
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGED, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGED, onChange);
    window.removeEventListener("storage", onChange);
  };
}

function choose(next: Palette): void {
  const attr = paletteAttribute(next);
  if (attr) document.documentElement.setAttribute("data-palette", attr);
  else document.documentElement.removeAttribute("data-palette");
  try {
    if (next === "ink") localStorage.removeItem(PALETTE_KEY);
    else localStorage.setItem(PALETTE_KEY, next);
  } catch {
    // storage blocked: the choice lasts for this page only
  }
  window.dispatchEvent(new Event(CHANGED));
}

// One button that swaps between the two palettes. Works with the theme switch: each
// palette has its own light and dark values, so any combination is a designed one.
export function PaletteSwitch({ className = "" }: { className?: string }) {
  const palette = useSyncExternalStore(subscribe, readPalette, () => "ink" as Palette);
  return (
    <button
      type="button"
      onClick={() => choose(nextPalette(palette))}
      aria-label={`${LABEL[palette]}. Switch palette`}
      title={LABEL[palette]}
      className={`inline-flex size-10 items-center justify-center rounded-md border border-border text-fg-muted hover:border-accent hover:text-fg ${className}`}
    >
      <PaletteIcon aria-hidden="true" className="size-4" />
    </button>
  );
}
