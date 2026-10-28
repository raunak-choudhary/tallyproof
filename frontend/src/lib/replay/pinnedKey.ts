// The only key this site trusts. It is compiled into the build from configuration and
// never read from the bundle it is checking, so a swapped bundle can't vouch for itself.
import type { VerifierKey } from "@/lib/verify/checkpoint";
import { parseVerifierKey } from "@/lib/verify/checkpoint";

export function pinnedVerifierKey(): VerifierKey {
  const vkey = process.env.NEXT_PUBLIC_PINNED_VERIFIER_KEY;
  if (!vkey) {
    throw new Error("NEXT_PUBLIC_PINNED_VERIFIER_KEY is not set; see docs/configuration.md");
  }
  return parseVerifierKey(vkey);
}
