import type { Metadata } from "next";
import { Caveat, Fraunces, JetBrains_Mono, Manrope } from "next/font/google";
import type { ReactNode } from "react";

import { BuildFooter } from "@/components/BuildFooter";
import { SiteNav } from "@/components/SiteNav";
import { APPLY_SAVED_PALETTE } from "@/lib/ui/palette";
import { APPLY_SAVED_THEME } from "@/lib/ui/theme";

import "./globals.css";

// Self-hosted by next/font at build time; the CSS variables feed the design tokens.
// Fraunces is the display voice, Manrope the body, JetBrains Mono the data, and Caveat
// the handwritten voice for taglines and callouts, used sparingly.
const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  axes: ["opsz", "SOFT", "WONK"],
});
const sans = Manrope({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });
const script = Caveat({ subsets: ["latin"], variable: "--font-script", display: "swap" });

export const metadata: Metadata = {
  title: "Tallyproof",
  description:
    "A streaming ledger for public spending data where every cited record carries a proof you can check in your browser.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${sans.variable} ${mono.variable} ${script.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Applies a saved theme before the first paint, so nothing flashes. */}
        <script dangerouslySetInnerHTML={{ __html: APPLY_SAVED_THEME + APPLY_SAVED_PALETTE }} />
      </head>
      <body className="flex min-h-dvh flex-col antialiased">
        <a
          href="#main"
          className="sr-only z-50 rounded-[var(--radius)] bg-accent px-4 py-2 text-accent-fg focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
        >
          Skip to content
        </a>
        <SiteNav />
        <div id="main" tabIndex={-1} className="flex-1 outline-none">
          {children}
        </div>
        <BuildFooter />
      </body>
    </html>
  );
}
