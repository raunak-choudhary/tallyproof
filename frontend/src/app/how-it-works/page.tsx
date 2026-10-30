import { readFileSync } from "node:fs";
import path from "node:path";

import type { Metadata } from "next";

import { ArchitectureFlow } from "@/features/how/ArchitectureFlow";
import { SpendingSankey } from "@/features/how/SpendingSankey";
import type { FlowRow } from "@/lib/charts/sankey";
import { naicsSector } from "@/lib/charts/sankey";
import { docsPath } from "@/lib/release/info";

export const metadata: Metadata = { title: "How it works · Tallyproof" };

// New obligations from the signed bundle, read at build time.
function flows(): FlowRow[] {
  const file = path.join(process.cwd(), "public", "replay", "events.jsonl");
  return readFileSync(file, "utf-8")
    .trim()
    .split("\n")
    .flatMap((line) => {
      const event = JSON.parse((JSON.parse(line) as { canonical: string }).canonical) as {
        event_type: string;
        payload: { awarding_agency?: string; naics_code?: string; amount: string };
      };
      if (event.event_type !== "obligation.recorded" || !event.payload.awarding_agency) return [];
      return [
        {
          agency: event.payload.awarding_agency,
          sector: naicsSector(event.payload.naics_code),
          amount: Number(event.payload.amount),
        },
      ];
    });
}

const SCALED = [
  ["1,000,000 events replayed", "13.1 million cleaned transactions, both years", "One setting"],
  [
    "One Postgres and one broker in a 3 GiB VM",
    "Aurora with replicas, a broker cluster",
    "Connection strings",
  ],
  ["A free-tier model, paced to its limits", "A paid tier", "One setting"],
  [
    "Agency totals are proven whole by a Merkle-sum tree; other filters cite a labelled sample",
    "A sum tree for every filter shape",
    "One key order per shape",
  ],
] as const;

export default function HowItWorks() {
  const docs = docsPath();
  return (
    <main className="mx-auto grid max-w-[1200px] gap-14 px-[var(--gutter)] py-12">
      <header className="grid max-w-3xl gap-3">
        <p className="text-xs font-semibold tracking-[0.14em] text-accent-2 uppercase">
          How it works
        </p>
        <h1 className="display text-[length:var(--text-2xl)] font-normal">
          From a bulk file to a number you can check.
        </h1>
        <p className="text-fg-muted">
          The architecture in plain words, what the ledger promises, what was scaled down to run on
          one laptop, and where the full documentation goes deeper.
        </p>
      </header>

      <section aria-labelledby="flow-heading" className="grid gap-4">
        <h2 id="flow-heading" className="text-lg font-semibold">
          The path a record takes
        </h2>
        <ArchitectureFlow />
      </section>

      <section aria-labelledby="promise-heading" className="grid gap-6 lg:grid-cols-2">
        <div className="grid content-start gap-3">
          <h2 id="promise-heading" className="text-lg font-semibold">
            What the ledger promises
          </h2>
          <p className="max-w-[65ch] text-fg-muted">
            Every record is hashed into a Merkle log. Every few seconds the root is signed, and the
            signature is timestamped by an outside witness. A record&apos;s proof is a short list of
            hashes your browser checks against a key built into this page.
          </p>
          <p className="max-w-[65ch] text-fg-muted">
            Numbers in answers are bound to query results and cited to the records behind them. The
            analyst never types a number.
          </p>
          <p className="max-w-[65ch] text-fg-muted">
            What it doesn&apos;t promise: that the source data is right. A wrong number in
            USAspending is faithfully, provably wrong here too. The proofs say a record is the one
            that was logged, not that it is true.
          </p>
        </div>
        <SpendingSankey rows={flows()} />
      </section>

      <section aria-labelledby="scaled-heading" className="grid gap-4">
        <h2 id="scaled-heading" className="text-lg font-semibold">
          What was scaled down, and how to run the real thing
        </h2>
        <div
          className="overflow-x-auto"
          tabIndex={0}
          aria-label="Scaled-down parts, scrolls sideways"
        >
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-fg-muted">
              <tr>
                <th scope="col" className="py-2 pr-4 font-medium">
                  Here
                </th>
                <th scope="col" className="py-2 pr-4 font-medium">
                  At scale
                </th>
                <th scope="col" className="py-2 font-medium">
                  Change
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {SCALED.map(([here, scale, change]) => (
                <tr key={here}>
                  <td className="py-2 pr-4">{here}</td>
                  <td className="py-2 pr-4 text-fg-muted">{scale}</td>
                  <td className="py-2 text-fg-muted">{change}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-sm text-fg-muted">
          The full table, with the reason for each cut and the AWS service that replaces it, is in{" "}
          <a href={`${docs}limitations/`} className="text-accent underline underline-offset-4">
            the documentation
          </a>
          .
        </p>
      </section>

      <nav aria-label="Further reading" className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <a href={docs} className="text-accent underline-offset-4 hover:underline">
          Read the documentation
        </a>
        <a href={`${docs}adr/`} className="text-accent underline-offset-4 hover:underline">
          Decision records
        </a>
        <a href={`${docs}threat-model/`} className="text-accent underline-offset-4 hover:underline">
          Threat model
        </a>
      </nav>
    </main>
  );
}
