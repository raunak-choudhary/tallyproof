/** The site's main pages, in the order the navigation shows them. */
export interface NavItem {
  href: string;
  label: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Story" },
  { href: "/ledger/", label: "Ledger" },
  { href: "/ask/", label: "Ask" },
  { href: "/tamper/", label: "Tamper" },
  { href: "/evals/", label: "Evals" },
  { href: "/how-it-works/", label: "How it works" },
];

/** Whether a navigation link is the page being viewed; the home link matches only itself. */
export function isActive(href: string, pathname: string): boolean {
  const path = pathname.endsWith("/") ? pathname : `${pathname}/`;
  if (href === "/") return path === "/";
  return path.startsWith(href);
}
