"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useId, useState } from "react";

import { PaletteSwitch } from "@/components/PaletteSwitch";
import { ThemeSwitch } from "@/components/ThemeSwitch";
import { isActive, NAV_ITEMS } from "@/lib/ui/nav";

// The top bar. From 768px the pages sit in a row; below that they fold into a menu
// (a declared adaptive pattern in the design brief). The menu closes when a link is chosen.
export function SiteNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const menuId = useId();

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-bg-elevated/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1200px] items-center gap-3 px-[var(--gutter)] py-3">
        <Link href="/" className="font-semibold tracking-tight">
          Tallyproof
        </Link>
        <nav aria-label="Main" className="ml-auto hidden items-center gap-6 text-sm md:flex">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive(item.href, pathname) ? "page" : undefined}
              className="text-fg-muted hover:text-fg aria-[current=page]:font-medium aria-[current=page]:text-fg"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <PaletteSwitch className="ml-auto md:ml-0" />
        <ThemeSwitch />
        <button
          type="button"
          className="inline-flex size-10 items-center justify-center rounded-md border border-border md:hidden"
          aria-expanded={open}
          aria-controls={menuId}
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen(!open)}
        >
          {open ? (
            <X aria-hidden="true" className="size-4" />
          ) : (
            <Menu aria-hidden="true" className="size-4" />
          )}
        </button>
      </div>
      <nav
        id={menuId}
        aria-label="Main"
        hidden={!open}
        className="border-t border-border px-[var(--gutter)] py-2 md:hidden"
      >
        <ul className="flex flex-col">
          {NAV_ITEMS.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                onClick={() => setOpen(false)}
                aria-current={isActive(item.href, pathname) ? "page" : undefined}
                className="block py-3 text-fg-muted hover:text-fg aria-[current=page]:font-medium aria-[current=page]:text-fg"
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
