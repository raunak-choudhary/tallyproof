"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

import type { Theme } from "@/lib/ui/theme";
import { isTheme, nextTheme, rootAttribute, THEME_KEY } from "@/lib/ui/theme";

const LABEL: Record<Theme, string> = {
  system: "Theme follows your system",
  light: "Light theme",
  dark: "Dark theme",
};
const CHANGED = "tallyproof-theme-changed";

function readTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    return isTheme(saved) ? saved : "system";
  } catch {
    return "system";
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

function choose(next: Theme): void {
  const attr = rootAttribute(next);
  if (attr) document.documentElement.setAttribute("data-theme", attr);
  else document.documentElement.removeAttribute("data-theme");
  try {
    if (next === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, next);
  } catch {
    // storage blocked: the choice lasts for this page only
  }
  window.dispatchEvent(new Event(CHANGED));
}

// One button that cycles system, light, dark. The choice persists in this browser; the
// inline script in the root layout applies it before the first paint. The server renders
// "system", and the stored choice takes over once the page is interactive.
export function ThemeSwitch({ className = "" }: { className?: string }) {
  const theme = useSyncExternalStore(subscribe, readTheme, () => "system" as Theme);
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  return (
    <button
      type="button"
      onClick={() => choose(nextTheme(theme))}
      aria-label={`${LABEL[theme]}. Switch theme`}
      title={LABEL[theme]}
      className={`inline-flex size-10 items-center justify-center rounded-md border border-border text-fg-muted hover:border-accent hover:text-fg ${className}`}
    >
      <Icon aria-hidden="true" className="size-4" />
    </button>
  );
}
