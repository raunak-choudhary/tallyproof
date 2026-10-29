import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/live/api";

import { askQuestion, assuranceNote, sampleNote, segments } from "./api";

const RAW = {
  answer_id: "ans_1",
  question: "How much?",
  status: "answered",
  text: "HHS obligated $1.00 [[c1]].",
  refusal: null,
  assurance: "filter_shown",
  filter_words: "total of obligations",
  checkpoint_tree_size: 9,
  slots: [
    {
      label: "s1",
      kind: "money",
      value: "1.00",
      display: "$1.00",
      meaning: "total",
      citation: "c1",
    },
  ],
  citations: [
    { label: "c1", meaning: "the 1 records", events: [{ event_id: "evt_1", leaf_index: 4 }] },
  ],
  quotes: [],
};

describe("analyst API client", () => {
  it("posts the question and maps the answer", async () => {
    let sent: RequestInit | undefined;
    const fetcher = (async (_url: string, init?: RequestInit) => {
      sent = init;
      return new Response(JSON.stringify(RAW), { status: 201 });
    }) as typeof fetch;
    const answer = await askQuestion("http://api", "How much?", fetcher);
    expect(sent?.method).toBe("POST");
    expect(JSON.parse(String(sent?.body))).toEqual({ question: "How much?" });
    expect(answer.treeSize).toBe(9);
    expect(answer.citations[0]?.events[0]).toEqual({ eventId: "evt_1", leafIndex: 4 });
  });

  it("surfaces problem details and rate limits", async () => {
    const fetcher = (async () =>
      new Response(JSON.stringify({ detail: "Request was throttled." }), {
        status: 429,
      })) as typeof fetch;
    await expect(askQuestion("http://api", "x?", fetcher)).rejects.toThrow(
      new ApiError("Request was throttled.", 429),
    );
  });

  it("splits text around citation markers", () => {
    expect(segments("A [[c1]] and [[q2]].")).toEqual([
      { kind: "text", text: "A " },
      { kind: "cite", label: "c1" },
      { kind: "text", text: " and " },
      { kind: "cite", label: "q2" },
      { kind: "text", text: "." },
    ]);
    expect(segments("plain")).toEqual([{ kind: "text", text: "plain" }]);
  });

  it("explains each level of assurance", () => {
    expect(assuranceNote("lower_assurance")).toMatch(/Lower assurance/);
    expect(assuranceNote("policy")).toMatch(/exact text/);
    expect(assuranceNote("filter_shown")).toMatch(/Verify any citation/);
  });

  it("labels a citation that lists only some of the records", () => {
    const events = [{ eventId: "evt_1", leafIndex: 1 }];
    expect(sampleNote({ label: "c1", meaning: "m", events, sampleOf: 52000 }, 1003)).toBe(
      "1 of 52,000 records listed here, each verifiable. The total covers all 52,000 as of checkpoint 1,003.",
    );
    expect(sampleNote({ label: "c1", meaning: "m", events, sampleOf: null }, 9)).toBeNull();
  });
});
