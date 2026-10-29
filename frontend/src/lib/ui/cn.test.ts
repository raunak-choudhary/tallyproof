import { describe, expect, it } from "vitest";

import { cn } from "./cn";
import { isActive } from "./nav";
import { APPLY_SAVED_THEME, isTheme, nextTheme, rootAttribute } from "./theme";

describe("cn", () => {
  it("joins classes and lets the later utility win", () => {
    expect(cn("px-2", false && "hidden", "px-4", { "text-fg": true })).toBe("px-4 text-fg");
  });
});

describe("theme", () => {
  it("cycles system, light, dark", () => {
    expect(nextTheme("system")).toBe("light");
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("system");
  });

  it("sets data-theme only for an explicit choice", () => {
    expect(rootAttribute("system")).toBeNull();
    expect(rootAttribute("dark")).toBe("dark");
    expect(isTheme("dark")).toBe(true);
    expect(isTheme("blue")).toBe(false);
  });

  it("applies a saved choice before paint without ever throwing", () => {
    const run = (stored: string | null) => {
      const doc = { attr: null as string | null };
      const fn = new Function(
        "localStorage",
        "document",
        APPLY_SAVED_THEME.replace(/^\(function\(\)\{|\}\)\(\);$/g, ""),
      );
      fn(
        { getItem: () => stored },
        { documentElement: { setAttribute: (_: string, v: string) => (doc.attr = v) } },
      );
      return doc.attr;
    };
    expect(run("dark")).toBe("dark");
    expect(run("system")).toBeNull();
    expect(run(null)).toBeNull();
    expect(() =>
      new Function("localStorage", "document", APPLY_SAVED_THEME)(
        {
          getItem: () => {
            throw new Error("blocked");
          },
        },
        {},
      ),
    ).not.toThrow();
  });
});

describe("nav", () => {
  it("marks the page being viewed", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/", "/ask/")).toBe(false);
    expect(isActive("/ask/", "/ask")).toBe(true);
    expect(isActive("/ledger/", "/ledger/")).toBe(true);
    expect(isActive("/ledger/", "/ledger/events/evt_1/")).toBe(true);
  });
});
