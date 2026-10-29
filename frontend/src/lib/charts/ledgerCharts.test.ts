import { describe, expect, it } from "vitest";

import { rowFromCanonical, rowsFromRecords } from "@/lib/ledger/events";
import type { Fact } from "@/lib/ledger/stream";
import { openStream, parseFact, streamUrl } from "@/lib/ledger/stream";

import { rasterLayout } from "./raster";
import { OTHER, streamgraphLayout } from "./streamgraph";

function canonical(fields: Record<string, unknown>, payload: Record<string, unknown>): string {
  return JSON.stringify({
    event_id: "evt_1",
    event_type: "obligation.recorded",
    emitted_at: "2025-01-02T00:00:00Z",
    ...fields,
    payload,
  });
}

describe("rows from canonical bytes", () => {
  it("reads the date, group, and amount an obligation carries", () => {
    const row = rowFromCanonical(
      canonical({}, { action_date: "2025-03-14", awarding_agency: "Energy", amount: "12.50" }),
      7,
    );
    expect(row).toMatchObject({ eventId: "evt_1", leafIndex: 7, group: "Energy", amount: 12.5 });
    expect(row?.date.toISOString()).toBe("2025-03-14T00:00:00.000Z");
  });

  it("labels modifications, outlays, and cash by what they have", () => {
    const mod = rowFromCanonical(
      canonical({ event_type: "obligation.adjusted" }, { action_date: "2025-03-14", amount: "-5" }),
      1,
    );
    expect(mod).toMatchObject({ group: "Modification", amount: -5 });
    const cash = rowFromCanonical(
      canonical(
        { event_type: "cash.movement" },
        { record_date: "2025-03-14", account: "TGA", amount: "3" },
      ),
      2,
    );
    expect(cash?.group).toBe("TGA");
    expect(rowFromCanonical("not json", 3)).toBeNull();
    expect(rowFromCanonical(canonical({}, { amount: "1" }), 4)?.date.getFullYear()).toBe(2025);
  });

  it("orders bundle records by leaf", () => {
    const rows = rowsFromRecords([
      {
        canonical: canonical({ event_id: "b" }, { action_date: "2025-01-01", amount: "1" }),
        leafIndex: 2,
      },
      {
        canonical: canonical({ event_id: "a" }, { action_date: "2025-01-01", amount: "1" }),
        leafIndex: 1,
      },
      { canonical: "{}", leafIndex: 0 },
    ]);
    expect(rows.map((r) => r.eventId)).toEqual(["a", "b"]);
  });
});

function rows(spec: [string, string, number][]) {
  return spec.map(([group, date, amount], i) => ({
    eventId: `evt_${i}`,
    leafIndex: i,
    eventType: "obligation.recorded",
    date: new Date(date),
    group,
    amount,
  }));
}

describe("streamgraphLayout", () => {
  it("bins by month over a long span, keeps the largest groups, and folds the rest", () => {
    const layout = streamgraphLayout(
      rows([
        ["A", "2025-01-10", 100],
        ["A", "2025-02-10", 50],
        ["B", "2025-01-20", 30],
        ["C", "2025-03-01", 5],
        ["D", "2025-03-02", 4],
        ["E", "2025-03-03", 3],
        ["F", "2025-03-04", 2],
        ["G", "2025-05-05", -9],
      ]),
      { width: 300, height: 100, top: 3 },
    );
    expect(layout.kind).toBe("month");
    expect(layout.months).toHaveLength(5);
    expect(layout.layers.map((l) => l.group)).toEqual(["A", "B", "C", OTHER]);
    expect(layout.layers[0]?.totals.map((t) => t.amount)).toEqual([100, 50, 0, 0, 0]);
    expect(layout.layers[3]?.totals.map((t) => t.amount)).toEqual([0, 0, 9, 0, 0]); // negatives clamp
    expect(layout.monthTotals).toEqual([130, 50, 14, 0, 0]);
    expect(layout.layers[3]?.colour).toBe(5);
    for (const layer of layout.layers) expect(layer.path.startsWith("M")).toBe(true);
    expect(layout.x(layout.months[0]!)).toBe(0);
    expect(layout.x(layout.months[4]!)).toBe(300);
  });

  it("bins by day over a span of days", () => {
    const layout = streamgraphLayout(
      rows([
        ["A", "2025-01-01", 1],
        ["A", "2025-01-03", 2],
        ["B", "2025-01-06", 3],
      ]),
    );
    expect(layout.kind).toBe("day");
    expect(layout.months).toHaveLength(6);
    expect(layout.monthTotals).toEqual([1, 0, 2, 0, 0, 3]);
  });

  it("bins by position in the log when everything happened on one day", () => {
    const spec: [string, string, number][] = [];
    for (let i = 0; i < 100; i++) spec.push([i % 2 ? "A" : "B", "2024-10-01", 1]);
    const layout = streamgraphLayout(rows(spec));
    expect(layout.kind).toBe("leaf");
    expect(layout.months).toHaveLength(40);
    expect(layout.monthTotals.reduce((a, b) => a + b, 0)).toBe(100);
    expect(layout.months[0]!.getTime()).toBe(0); // the first leaf index
  });

  it("handles no rows and a single row", () => {
    expect(streamgraphLayout([]).layers).toEqual([]);
    const one = streamgraphLayout(rows([["A", "2025-05-05", 1]]));
    expect(one.kind).toBe("leaf");
    expect(one.layers).toHaveLength(1);
    expect(one.monthTotals.reduce((a, b) => a + b, 0)).toBe(1);
  });
});

describe("rasterLayout", () => {
  it("gives the busiest groups a row each, folds the rest, and places ticks by leaf", () => {
    const spec: [string, string, number][] = [];
    for (let i = 0; i < 30; i++) spec.push([`G${i % 4}`, "2025-01-01", 1]);
    spec.push(["Rare", "2025-01-01", 1]);
    const layout = rasterLayout(rows(spec), { width: 310, maxRows: 3, marked: new Set(["evt_5"]) });
    expect(layout.rows.map((r) => r.group)).toEqual(["G0", "G1", "Other"]);
    expect(layout.height).toBe(3 * 14);
    expect(layout.ticks).toHaveLength(31);
    expect(layout.ticks[0]).toMatchObject({ x: 0, row: 0, leafIndex: 0 });
    expect(layout.ticks[30]).toMatchObject({ x: 310, row: 2, eventId: "evt_30" });
    expect(layout.ticks.find((t) => t.eventId === "evt_5")?.marked).toBe(true);
  });
});

describe("stream", () => {
  it("parses known facts and ignores anything else", () => {
    expect(parseFact('{"kind":"event_appended","event_id":"evt_1","leaf_index":3}')).toEqual({
      kind: "event_appended",
      event_id: "evt_1",
      leaf_index: 3,
    });
    expect(parseFact('{"kind":"surprise"}')).toBeNull();
    expect(parseFact("[1]")).toBeNull();
    expect(parseFact("{")).toBeNull();
    expect(streamUrl("ws://127.0.0.1:8001/")).toBe("ws://127.0.0.1:8001/ws/v1/stream");
  });

  it("delivers facts, reconnects with backoff after a drop, and stops on close", () => {
    class FakeSocket {
      onopen: ((ev: unknown) => void) | null = null;
      onmessage: ((ev: { data: unknown }) => void) | null = null;
      onclose: ((ev: unknown) => void) | null = null;
      onerror: ((ev: unknown) => void) | null = null;
      closed = false;
      close() {
        this.closed = true;
      }
    }
    const sockets: FakeSocket[] = [];
    const timers: { fn: () => void; ms: number }[] = [];
    const facts: Fact[] = [];
    const statuses: string[] = [];
    const handle = openStream("ws://x/ws/v1/stream", (f) => facts.push(f), {
      onStatus: (s) => statuses.push(s),
      connect: () => {
        const s = new FakeSocket();
        sockets.push(s);
        return s;
      },
      schedule: (fn, ms) => timers.push({ fn, ms }),
      cancel: () => {},
    });
    const first = sockets[0]!;
    first.onopen?.({});
    first.onmessage?.({ data: '{"kind":"checkpoint_signed","tree_size":9}' });
    first.onmessage?.({ data: 12 });
    expect(facts).toEqual([{ kind: "checkpoint_signed", tree_size: 9 }]);
    first.onclose?.({});
    expect(timers.map((t) => t.ms)).toEqual([1000]);
    timers[0]!.fn(); // reconnect
    expect(sockets).toHaveLength(2);
    sockets[1]!.onclose?.({});
    expect(timers.map((t) => t.ms)).toEqual([1000, 2000]);
    handle.close();
    expect(sockets[1]!.closed).toBe(true);
    expect(statuses).toEqual(["connecting", "open", "closed", "connecting", "closed"]);
  });
});
