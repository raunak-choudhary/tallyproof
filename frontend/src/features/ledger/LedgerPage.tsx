"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fetchEvent, recentEvents } from "@/lib/live/api";
import type { LedgerRow } from "@/lib/ledger/events";
import { rowFromCanonical, rowsFromRecords } from "@/lib/ledger/events";
import type { Fact } from "@/lib/ledger/stream";
import { openStream, streamUrl } from "@/lib/ledger/stream";
import { loadBundle } from "@/lib/replay/bundle";
import { replayBase } from "@/lib/replay/paths";
import { pinnedVerifierKey } from "@/lib/replay/pinnedKey";
import { verifyCheckpoint } from "@/lib/verify/checkpoint";

import { ArrivalRaster } from "./ArrivalRaster";
import { ProvenTotals } from "./ProvenTotals";
import { Streamgraph } from "./Streamgraph";

type Status = "replay" | "connecting" | "open" | "closed";

interface FeedItem {
  key: string;
  kind: "event" | "checkpoint" | "break" | "dropped";
  text: string;
  href?: string;
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const FEED = 8;

// The ledger as it happens. With a WebSocket server configured, facts arrive over the
// stream and each appended event is fetched and proven on demand; otherwise the page
// replays the signed demo bundle. No polling in either mode.
export function LedgerPage() {
  const ws = process.env.NEXT_PUBLIC_WS_URL;
  const api = process.env.NEXT_PUBLIC_API_URL;
  const live = Boolean(ws && api);
  const [rows, setRows] = useState<LedgerRow[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [checkpoint, setCheckpoint] = useState<{ treeSize: number; note: string } | null>(null);
  const [breaks, setBreaks] = useState(0);
  const [dropped, setDropped] = useState(0);
  const [status, setStatus] = useState<Status>(live ? "connecting" : "replay");
  const [error, setError] = useState<string | null>(null);
  const [month, setMonth] = useState<Date | null>(null);

  useEffect(() => {
    if (live) return;
    loadBundle(replayBase(), pinnedVerifierKey())
      .then((bundle) => {
        const loaded = rowsFromRecords(bundle.records);
        setRows(loaded);
        setFeed(
          loaded
            .slice(-FEED)
            .reverse()
            .map((r) => ({
              key: r.eventId,
              kind: "event",
              text: `${r.eventId} appended · leaf ${r.leafIndex}`,
              href: `/ledger/events/${r.eventId}/`,
            })),
        );
        try {
          const cp = verifyCheckpoint(bundle.latestCheckpointNote, pinnedVerifierKey());
          setCheckpoint({ treeSize: cp.treeSize, note: bundle.latestCheckpointNote });
        } catch {
          setCheckpoint(null);
        }
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [live]);

  useEffect(() => {
    if (!live || !ws || !api) return;
    const base = api;
    const push = (item: FeedItem) => setFeed((f) => [item, ...f].slice(0, FEED));
    recentEvents(base, 200)
      .then((events) => {
        const loaded = rowsFromRecords(events);
        setRows(loaded);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
    const onFact = (fact: Fact) => {
      if (fact.kind === "event_appended") {
        fetchEvent(base, fact.event_id)
          .then((event) => {
            const row = rowFromCanonical(event.canonical, event.leafIndex);
            if (row) setRows((r) => [...r, row]);
            push({
              key: `${fact.event_id}-${fact.leaf_index}`,
              kind: "event",
              text: `${fact.event_id} appended · leaf ${fact.leaf_index}`,
              href: `/live/?event=${fact.event_id}`,
            });
          })
          .catch(() => {});
      } else if (fact.kind === "checkpoint_signed") {
        setCheckpoint((c) => ({ treeSize: fact.tree_size, note: c?.note ?? "" }));
        push({
          key: `cp-${fact.tree_size}`,
          kind: "checkpoint",
          text: `checkpoint signed · ${fact.tree_size.toLocaleString("en-US")} leaves`,
        });
      } else if (fact.kind === "break_found") {
        setBreaks((n) => n + 1);
        push({ key: fact.break_id, kind: "break", text: `break found · ${fact.break_id}` });
      } else {
        setDropped((n) => n + fact.count);
        push({
          key: `drop-${Date.now()}`,
          kind: "dropped",
          text: `behind by ${fact.count}, re-reading`,
        });
        recentEvents(base, 200)
          .then((events) => setRows(rowsFromRecords(events)))
          .catch(() => {});
      }
    };
    const handle = openStream(streamUrl(ws), onFact, { onStatus: setStatus });
    return () => handle.close();
  }, [live, ws, api]);

  const inMonth = useMemo(() => {
    if (!month) return [];
    return rows
      .filter(
        (r) =>
          r.date.getUTCFullYear() === month.getUTCFullYear() &&
          r.date.getUTCMonth() === month.getUTCMonth(),
      )
      .slice(0, 8);
  }, [rows, month]);

  const latestLeaf = rows.length ? rows[rows.length - 1]!.leafIndex : null;
  const pill =
    status === "replay"
      ? "Replay of the signed bundle"
      : status === "open"
        ? "Live"
        : status === "connecting"
          ? "Connecting to the stream"
          : "Stream closed, reconnecting";

  return (
    <main className="mx-auto grid max-w-[1200px] gap-6 px-[var(--gutter)] py-10">
      <header className="grid gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${status === "open" ? "border-accent-2 text-accent-2" : "border-border text-fg-muted"}`}
          >
            {status === "open" && (
              <span aria-hidden="true" className="size-2 rounded-full bg-accent-2" />
            )}
            {pill}
          </span>
          {latestLeaf !== null && (
            <span className="font-mono text-fg-muted">
              leaf {latestLeaf.toLocaleString("en-US")}
              {checkpoint ? ` · tree signed at ${checkpoint.treeSize.toLocaleString("en-US")}` : ""}
            </span>
          )}
        </div>
        <h1 className="display text-[length:var(--text-2xl)] font-normal">
          The ledger, as it happens
        </h1>
        {error && (
          <p role="alert" className="text-fail">
            {error}
          </p>
        )}
      </header>

      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["Events", rows.length.toLocaleString("en-US")],
          ["Signed at", checkpoint ? checkpoint.treeSize.toLocaleString("en-US") : "…"],
          ["Breaks found", live ? breaks.toLocaleString("en-US") : "n/a in replay"],
          ["Facts dropped", dropped.toLocaleString("en-US")],
        ].map(([k, v]) => (
          <div
            key={k}
            className="rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-4"
          >
            <dt className="text-xs text-fg-muted">{k}</dt>
            <dd className="mt-1 font-mono text-[length:var(--text-xl)] tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-6 md:grid-cols-[3fr_2fr]">
        <section className="min-w-0 rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-4">
          <Streamgraph rows={rows} onPickMonth={setMonth} />
          {month && (
            <div className="mt-4 border-t border-border pt-3 text-sm">
              <p className="text-fg-muted">
                {inMonth.length
                  ? "Records in that month, first eight:"
                  : "No records in that month."}
              </p>
              <ul className="mt-1 grid gap-1">
                {inMonth.map((r) => (
                  <li key={r.eventId} className="flex flex-wrap justify-between gap-x-3">
                    <Link
                      href={`/ledger/events/${r.eventId}/`}
                      className="font-mono text-xs text-accent hover:underline"
                    >
                      {r.eventId}
                    </Link>
                    <span className="font-mono text-xs tabular-nums text-fg-muted">
                      {r.group} · {usd.format(r.amount)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
        <section
          aria-label="Stream"
          className="min-w-0 rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-4"
        >
          <h2 className="text-sm font-medium">Stream</h2>
          <ol className="mt-2 divide-y divide-border text-xs">
            {feed.map((item) => (
              <li key={item.key} className="flex items-start gap-2 py-2">
                <span
                  aria-hidden="true"
                  className={`mt-1 size-2 shrink-0 ${item.kind === "checkpoint" ? "rounded-sm bg-ok" : item.kind === "break" ? "rounded-full bg-warn" : item.kind === "dropped" ? "rounded-full bg-fail" : "rounded-full bg-accent"}`}
                />
                {item.href ? (
                  <Link href={item.href} className="breakable font-mono hover:underline">
                    {item.text}
                  </Link>
                ) : (
                  <span className="breakable font-mono">{item.text}</span>
                )}
              </li>
            ))}
            {feed.length === 0 && <li className="py-2 text-fg-muted">Waiting for facts…</li>}
          </ol>
        </section>
      </div>

      <section className="min-w-0 rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-4">
        <ArrivalRaster rows={rows} />
      </section>

      {!live && <ProvenTotals base={replayBase()} treeSize={checkpoint?.treeSize ?? null} />}

      {checkpoint?.note && (
        <section className="min-w-0 rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-4">
          <h2 className="text-sm font-medium">Latest checkpoint</h2>
          <pre className="mt-2 overflow-x-auto font-mono text-xs whitespace-pre-wrap text-fg-muted">
            {checkpoint.note}
          </pre>
          <p className="mt-2 text-xs text-ok">✓ signature checked here against the pinned key</p>
        </section>
      )}
    </main>
  );
}
