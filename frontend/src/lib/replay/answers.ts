// The static site's demo answers: real answers to a fixed list of questions, computed
// once on a ledger built from exactly this bundle's records. The file isn't signed;
// what makes an answer checkable is that every record it cites is in the signed bundle.
import type { Answer, RawAnswer } from "@/lib/analyst/api";
import { toAnswer } from "@/lib/analyst/api";

export interface DemoAnswers {
  treeSize: number;
  routerModel: string;
  answerModel: string;
  computedAt: string;
  commit: string;
  answers: Answer[];
}

export function parseDemoAnswers(text: string): DemoAnswers {
  const raw = JSON.parse(text) as {
    tree_size: number;
    router_model: string;
    answer_model: string;
    computed_at: string;
    commit: string;
    answers: RawAnswer[];
  };
  return {
    treeSize: raw.tree_size,
    routerModel: raw.router_model,
    answerModel: raw.answer_model,
    computedAt: raw.computed_at,
    commit: raw.commit,
    answers: raw.answers.map(toAnswer),
  };
}

export async function loadDemoAnswers(base: string): Promise<DemoAnswers> {
  const response = await fetch(`${base}/answers.json`);
  if (!response.ok) throw new Error(`could not load answers.json (${response.status})`);
  return parseDemoAnswers(await response.text());
}
