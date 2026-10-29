import Link from "next/link";

import { docsPath } from "@/lib/release/info";

import { buttonVariants } from "@/components/ui/Button";
import { cn } from "@/lib/ui/cn";

// The opening: the problem in highlights, then Tallyproof as the answer, then the tagline.
// Problem first is the owner's framing; the figures are the README's, sourced in
// docs/references.md. Server-rendered, no script.
export function Hero({ firstEventId }: { firstEventId: string | null }) {
  return (
    <section
      aria-labelledby="hero-heading"
      className="relative isolate overflow-hidden border-b border-border bg-bg-elevated"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            "radial-gradient(900px 480px at 85% -10%, var(--glow), transparent 60%), radial-gradient(600px 300px at 0% 110%, color-mix(in oklab, var(--accent-2) 18%, transparent), transparent 70%)",
        }}
      />
      <div className="mx-auto grid max-w-[1200px] gap-7 px-[var(--gutter)] py-[var(--space-section)]">
        <p className="text-xs font-semibold tracking-[0.14em] text-accent-2 uppercase">
          The problem
        </p>
        <h1
          id="hero-heading"
          className="display max-w-[18ch] text-[length:var(--text-hero)] leading-[1.05] font-normal"
        >
          AI gets the numbers wrong, and cites sources{" "}
          <em className="text-accent">it never read.</em>
        </h1>
        <p className="max-w-[60ch] text-[length:var(--text-lg)] text-fg-muted">
          In one study, up to 57 percent of citations in AI answers didn&apos;t match their source.
          And even an honest citation points at a database row that anyone with access can quietly
          edit.{" "}
          <strong className="font-semibold text-fg">
            Tallyproof is a ledger of real federal spending where every number an AI gives you is
            bound to a signed record, and your browser checks the proof.
          </strong>
        </p>
        <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
          <p className="script inline-block -rotate-1 text-[length:var(--text-xl)] font-semibold text-gold">
            Every number, proven.
          </p>
          <p className="font-mono text-xs tracking-wide text-fg-muted">
            append-only · signed · witnessed · verified by you
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          {firstEventId && (
            <Link
              href={`/ledger/events/${firstEventId}/`}
              className={cn(buttonVariants({ variant: "primary" }), "rounded-full px-5")}
            >
              Verify a record
            </Link>
          )}
          <Link
            href={process.env.NEXT_PUBLIC_API_URL ? "/ask/" : "/ledger/"}
            className={cn(buttonVariants({ variant: "ghost" }), "rounded-full px-5")}
          >
            {process.env.NEXT_PUBLIC_API_URL ? "Ask the ledger" : "Open the ledger"}
          </Link>
          <a
            href={`${docsPath()}references/`}
            className={cn(buttonVariants({ variant: "quiet" }), "px-2")}
            title="Where the figures come from"
          >
            Sources
          </a>
        </div>
      </div>
    </section>
  );
}
