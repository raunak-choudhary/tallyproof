/** The theme choice: follow the system, or an explicit light or dark. */
export type Theme = "system" | "light" | "dark";

export const THEME_KEY = "tallyproof-theme";
const THEMES: readonly Theme[] = ["system", "light", "dark"];

export function isTheme(value: unknown): value is Theme {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value);
}

/** The next choice in the cycle system, light, dark. */
export function nextTheme(current: Theme): Theme {
  return THEMES[(THEMES.indexOf(current) + 1) % THEMES.length] ?? "system";
}

/** What `data-theme` on the root element should be for a choice: nothing for system. */
export function rootAttribute(theme: Theme): string | null {
  return theme === "system" ? null : theme;
}

/**
 * The script that runs before the first paint, so a saved choice never flashes the
 * other theme. It is inlined by the root layout and must stay free of anything that
 * could throw: storage may be blocked, and the value may be anything.
 */
export const APPLY_SAVED_THEME = `(function(){try{var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t)}}catch(e){}})();`;
