/**
 * The palette choice, independent of light or dark. "ink" is Ink and Ultraviolet, the
 * default; "midnight" is Midnight and Gold, the warmer editorial option from the Phase 5
 * specimen. Each palette has its own light and dark values in tokens.css.
 */
export type Palette = "ink" | "midnight";

export const PALETTE_KEY = "tallyproof-palette";
const PALETTES: readonly Palette[] = ["ink", "midnight"];

export function isPalette(value: unknown): value is Palette {
  return typeof value === "string" && (PALETTES as readonly string[]).includes(value);
}

/** The other palette. */
export function nextPalette(current: Palette): Palette {
  return current === "ink" ? "midnight" : "ink";
}

/** What `data-palette` on the root element should be: nothing for the default. */
export function paletteAttribute(palette: Palette): string | null {
  return palette === "ink" ? null : palette;
}

/**
 * Runs before the first paint, beside the theme script, so a saved palette never flashes
 * the default. Must never throw: storage may be blocked and the value may be anything.
 */
export const APPLY_SAVED_PALETTE = `(function(){try{var p=localStorage.getItem(${JSON.stringify(PALETTE_KEY)});if(p==="midnight"){document.documentElement.setAttribute("data-palette",p)}}catch(e){}})();`;
