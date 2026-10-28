// Loads the shared cross-language test vectors written by the Python core.
import { readFileSync } from "node:fs";

export function loadVectors<T>(name: string): T {
  const url = new URL(`../../../../testdata/vectors/${name}`, import.meta.url);
  return JSON.parse(readFileSync(url, "utf-8")) as T;
}
