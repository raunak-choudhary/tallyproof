// The analyst API: ask a question, get an answer with values, citations, and
// quotes. The answer carries proofs to fetch, never a verdict; whether a citation
// holds up is decided in the browser by the verifier.
import { ApiError } from "@/lib/live/api";

export interface Slot {
  label: string;
  kind: "money" | "count" | "date" | "text";
  value: string;
  display: string;
  meaning: string;
  citation: string | null;
}

export interface CitedEvent {
  eventId: string;
  leafIndex: number;
}

export interface Citation {
  label: string;
  meaning: string;
  events: CitedEvent[];
}

export interface Quote {
  source: string;
  text: string;
  eventId: string;
  leafIndex: number;
  section: string;
  title: string;
}

export interface Answer {
  answerId: string;
  question: string;
  status: "answered" | "refused";
  text: string;
  refusal: { code: string; message: string } | null;
  assurance: string;
  filterWords: string;
  treeSize: number;
  slots: Slot[];
  citations: Citation[];
  quotes: Quote[];
}

interface RawAnswer {
  answer_id: string;
  question: string;
  status: "answered" | "refused";
  text: string;
  refusal: { code: string; message: string } | null;
  assurance: string;
  filter_words: string;
  checkpoint_tree_size: number;
  slots: Slot[];
  citations: {
    label: string;
    meaning: string;
    events: { event_id: string; leaf_index: number }[];
  }[];
  quotes: {
    source: string;
    text: string;
    event_id: string;
    leaf_index: number;
    section: string;
    title: string;
  }[];
}

export function toAnswer(raw: RawAnswer): Answer {
  return {
    answerId: raw.answer_id,
    question: raw.question,
    status: raw.status,
    text: raw.text,
    refusal: raw.refusal,
    assurance: raw.assurance,
    filterWords: raw.filter_words,
    treeSize: raw.checkpoint_tree_size,
    slots: raw.slots,
    citations: raw.citations.map((c) => ({
      label: c.label,
      meaning: c.meaning,
      events: c.events.map((e) => ({ eventId: e.event_id, leafIndex: e.leaf_index })),
    })),
    quotes: raw.quotes.map((q) => ({
      source: q.source,
      text: q.text,
      eventId: q.event_id,
      leafIndex: q.leaf_index,
      section: q.section,
      title: q.title,
    })),
  };
}

export async function askQuestion(
  base: string,
  question: string,
  fetcher: typeof fetch = fetch,
): Promise<Answer> {
  const response = await fetcher(`${base}/api/v1/queries`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? String(body.detail) : "";
    throw new ApiError(detail || `the API answered ${response.status}`, response.status);
  }
  return toAnswer(body as RawAnswer);
}

export type Segment = { kind: "text"; text: string } | { kind: "cite"; label: string };

/** Split answer text into prose and citation markers such as [[c1]] or [[q2]]. */
export function segments(text: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(/\[\[\s*([cq]\d+)\s*\]\]/g)) {
    if (match.index > last) out.push({ kind: "text", text: text.slice(last, match.index) });
    out.push({ kind: "cite", label: match[1] ?? "" });
    last = match.index + match[0].length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out;
}

/** What the reader is told about how much has been checked. */
export function assuranceNote(assurance: string): string {
  if (assurance === "lower_assurance") {
    return "Lower assurance: the model wrote this query. Each cited record can be verified, but the filter and completeness weren't checked.";
  }
  if (assurance === "policy") {
    return "Quotes are exact text from the cited regulation, and each section can be verified against the signed log.";
  }
  return "Every value comes from a query over the ledger. Verify any citation to check its records against the signed checkpoint.";
}
