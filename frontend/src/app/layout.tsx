import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import type { ReactNode } from "react";

import { BuildFooter } from "@/components/BuildFooter";
import { SiteNav } from "@/components/SiteNav";
import { APPLY_SAVED_THEME } from "@/lib/ui/theme";

import "./globals.css";

// Self-hosted by next/font at build time; the CSS variables feed the design tokens.
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Tallyproof",
  description:
    "A streaming ledger for public spending data where every cited record carries a proof you can check in your browser.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        {/* Applies a saved theme before the first paint, so nothing flashes. */}
        <script dangerouslySetInnerHTML={{ __html: APPLY_SAVED_THEME }} />
      </head>
      <body className="flex min-h-dvh flex-col antialiased">
        <SiteNav />
        <div className="flex-1">{children}</div>
        <BuildFooter />
      </body>
    </html>
  );
}
