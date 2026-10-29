import { readFileSync } from "node:fs";
import path from "node:path";

import Link from "next/link";

import { Hero } from "@/features/landing/Hero";

interface Preview {
  eventId: string;
  agency: string;
  amount: string;
  date: string;
}

// Read at build time from the signed bundle: the home page links to real records.
function previews(count: number): { total: number; items: Preview[] } {
  const lines = readFileSync(path.join(process.cwd(), "public", "replay", "events.jsonl"), "utf-8")
    .trim()
    .split("\n");
  const items = lines.slice(0, count).map((line) => {
    const { event_id: eventId, canonical } = JSON.parse(line) as {
      event_id: string;
      canonical: string;
    };
    const event = JSON.parse(canonical) as {
      payload: { awarding_agency?: string; amount: string; action_date: string };
    };
    return {
      eventId,
      agency: event.payload.awarding_agency ?? "Contract modification",
      amount: event.payload.amount,
      date: event.payload.action_date,
    };
  });
  return { total: lines.length, items };
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export default function HomePage() {
  const { total, items } = previews(8);
  return (
    <>
      <Hero firstEventId={items[0]?.eventId ?? null} />
      <main className="mx-auto max-w-3xl px-[var(--gutter)] py-16">
        <section aria-labelledby="records-heading">
          <h2 id="records-heading" className="text-lg font-semibold">
            Records from the signed log
          </h2>
          <p className="mt-1 text-sm text-fg-muted">
            {total.toLocaleString("en-US")} FY2025 contract transactions from USAspending.gov, with
            personal data removed.
          </p>
          <ul className="mt-4 divide-y divide-border rounded-[var(--radius)] border border-border">
            {items.map((item) => (
              <li key={item.eventId}>
                <Link
                  href={`/ledger/events/${item.eventId}/`}
                  className="flex flex-col gap-1 px-4 py-3 hover:bg-bg-elevated focus-visible:outline-2 focus-visible:outline-accent sm:flex-row sm:items-center sm:justify-between"
                >
                  <span>
                    <span className="block">{item.agency}</span>
                    <span className="block font-mono text-xs text-fg-muted">{item.eventId}</span>
                  </span>
                  <span className="font-mono tabular-nums sm:text-right">
                    {usd.format(Number(item.amount))}
                    <span className="block text-xs text-fg-muted">{item.date}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        {process.env.NEXT_PUBLIC_API_URL && (
          <p className="mt-6">
            <Link href="/live/" className="text-accent underline-offset-4 hover:underline">
              Open the live ledger
            </Link>{" "}
            <span className="text-fg-muted">to verify events as the pipeline appends them.</span>
          </p>
        )}
        {process.env.NEXT_PUBLIC_API_URL && (
          <p className="mt-2">
            <Link href="/ask/" className="text-accent underline-offset-4 hover:underline">
              Ask the analyst
            </Link>{" "}
            <span className="text-fg-muted">
              a question and verify every record its answer cites.
            </span>
          </p>
        )}

        <section aria-labelledby="how-heading" className="mt-12 space-y-3 text-fg-muted">
          <h2 id="how-heading" className="text-lg font-semibold text-fg">
            What your browser checks
          </h2>
          <p>
            Each record is hashed into a Merkle log, and the log&apos;s root is signed. This site
            trusts exactly one public key, built into the page. When you press Verify, your browser
            recomputes the record&apos;s hash, walks its proof up to the signed root, and checks the
            signature. Nothing is taken on the server&apos;s word.
          </p>
        </section>
      </main>
    </>
  );
}
