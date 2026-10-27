# 12. Risks and Decisions Log

## 1. Decisions log (append only, newest last)

| Date | Decision | Reason | Ref |
|---|---|---|---|
| 2026-10-26 | Rolling-wave planning: detail Phases 0 to 3, epics for 4 to 6, re-plan at RP-1/RP-2/RP-3 | Owner wants room to adapt as reality teaches us | 06 |
| 2026-10-26 | Phase 1 reordered into a thin "proof slice" shipped publicly within about 4 days | Reviewers may look within days; a small real demo beats a big plan | 06 |
| 2026-10-26 | Feature branches, PR to `main`, self squash-merge after CI and review comments; merged branches kept for about a month | Owner preference; PR history is portfolio evidence | 10 |
| 2026-10-26 | No AI co-author trailer in commits | Owner preference | 10 |
| 2026-10-26 | Single append-only Merkle log (RFC 9162) with checkpoints, not independent batch trees | Consistency proofs, standard, stronger DSA signal | ADR-0003 |
| 2026-10-26 | Signed checkpoints and external witnessing added to MVP | Without it the tamper story has a hole | ADR-0007 |
| 2026-10-26 | Bloom filter as fast path only; UNIQUE constraint is the authority; offsets in same transaction | Bloom alone can drop real payments | ADR-0008 |
| 2026-10-26 | Bound-slot answer format | Numbers never typed by model | ADR-0009 |
| 2026-10-26 | Ground-truth labels in separate manifest, never in events | Otherwise analyst can read the answer key | 05 |
| 2026-10-26 | Independent eval oracle sharing no code with analyst | Shared bugs would pass silently | 08 |
| 2026-10-26 | Lake sink and load test promoted to MLP | Strongest data-pipeline signal | ADR-0012 |
| 2026-10-26 | Double-entry journal added to MVP | Finance credibility | ADR-0013 |
| 2026-10-26 | SeaweedFS instead of MinIO | MinIO community archived | ADR-0012 |
| 2026-10-26 | TypeScript pinned to 6.0.x, ESLint 10 | TS 7 incompatible with typescript-eslint; ESLint 9 EOL | 03 |
| 2026-10-26 | Keep MkDocs Material (strong default) with Zensical-compatible config | Material in maintenance mode; avoid lock-in without deviating | 03 |
| 2026-10-26 | release-please via minimal GitHub Action; all CI on CircleCI | GitHub-only tool; avoids PAT | ADR-0011 |
| 2026-10-26 | Added docs: `15-aws-reference-architecture.md`, `docs/research/*` | AWS signal without AWS usage; auditable sources | 15 |
| 2026-10-26 | Brief claims corrected: SR 26-2 dropped; EU AI Act dates corrected; DS@GT, FinLFQA, timeline paper reframed | Primary-source verification | research/verified-sources.md |
| 2026-10-26 | T-002 docs PR exceeds 400-line target | Planning docs are one reviewable unit | 06 |
| 2026-10-27 | Repository created under the working name `ledgerline`, private until the owner makes it public | Owner wanted version control from the start; the name can still change (GitHub redirects renamed repos) | ADR-0006 |
| 2026-10-27 | Rebase-merge instead of squash; every commit must be a Conventional Commit | Keeps every commit visible on `main`; refines REQ-GIT-03 | 10 |
| 2026-10-27 | Original brief kept out of the public repo | It is addressed to an agent and names target reviewers; the docs supersede it | n/a |
| 2026-10-27 | Design review: verification trust model narrowed to a pinned key plus an externally timestamped checkpoint | Same-origin key and proof proved nothing | ADR-0015 |
| 2026-10-27 | Design review: constrained query IR replaces provenance from free-form SQL | Provenance undefined for most query shapes | ADR-0014 |
| 2026-10-27 | Design review: leaf indexes from a counter row, staged inserts, fenced offsets | Sequence gaps and zombie consumers | ADR-0008 |
| 2026-10-27 | Design review: payments post to unapplied cash first | Deterministic journal re-derivation | ADR-0013 |
| 2026-10-27 | Design review: integrity checks separated from quality metrics; held-out question set | Several gates were true by construction | 08 |
| 2026-10-27 | Design review: Phase 1 split into 1a (static proof page) and 1b (live pipeline) | Demo was last in an infra-first order | 06 |
| 2026-10-27 | Agent guide (CLAUDE.md) kept local and untracked | Public repository shows only documentation written for people | 10 |
| 2026-10-27 | Final name `tallyproof`; repository renamed from `ledgerline` | Free on PyPI, npm, and GitHub; names the thesis | ADR-0006 |
| 2026-10-27 | Design review: OpenTimestamps as the independent witness | The git witness is controlled by the operator | 11, ADR-0007 |

## 2. Risks

| ID | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| R-01 | Scope exceeds one month solo | High | High | Rolling wave, proof slice first, MVP-not-green rule, RP checkpoints | Raunak |
| R-02 | Reviewers see repo before anything works | Medium | High | Phase 1 proof slice in about 4 days; README status banner tells the truth | Raunak |
| R-03 | Cross-language hash mismatch (Python vs browser) | Medium | High | RFC 8785 libs, decimal strings, shared vectors in both test suites | Raunak |
| R-04 | Merkle implementation bug undermines thesis | Low | Critical | RFC vectors, Hypothesis properties, independent TS verifier | Raunak |
| R-05 | LLM cost overrun | Medium | Medium | Budgets, caching, fake mode before MC-05, daily cap | Raunak (MC-05) |
| R-06 | Eval thresholds set unrealistically | Medium | Medium | Set from first live baseline, then ratchet | Raunak |
| R-07 | CircleCI free-tier minutes exhausted by integration and eval jobs | Medium | Medium | Path filtering, caching, run heavy jobs only when relevant paths change | Raunak |
| R-08 | Testcontainers flakiness in CI | Medium | Medium | Machine executor, pinned images, health waits, retries only on infra errors | Raunak |
| R-09 | Single log writer limits throughput | High (at scale) | Low (for demo) | Measure and document; scale-out path in ADR-0003 | Raunak |
| R-10 | Completeness gap in aggregate proofs | Certain | Medium | Honest labeling; recompute in browser; Merkle-sum tree Nice-to-have | Raunak |
| R-11 | Public demo looks "fake" because it is replay | Medium | Medium | Bundle manifest with git SHA and seed; in-browser verification; clear labeling | Raunak |
| R-12 | SeaweedFS Object Lock incomplete | Medium | Low | Integration test before relying on it; git witness remains primary | Raunak |
| R-13 | Channels low release cadence | Low | Low | Thin usage; could swap to plain ASGI WebSocket | Raunak |
| R-14 | Naming collision discovered later | Low | Medium | Checked PyPI, npm, GitHub, web on 2026-10-26 | Raunak (MC-02) |
| R-15 | Overclaiming regulation (for example implying the tool is "EU AI Act compliant") | Medium | High | README language reviewed against verified-sources; say "motivated by", never "compliant with" | Raunak |

## 3. Open questions

| ID | Question | Needed by |
|---|---|---|
| Q-02 | Diagram skill choice: `diagram-design` (MIT, HTML/SVG, very popular) for the README hero; Mermaid in docs written directly or via a licensed Mermaid skill. `design-doc-mermaid` has **no license**, so we recommend not installing it | T-214 (MC-08) |
| Q-03 | When to make the repo public (now private) | Recommended: now, so the planning history is visible; at the latest when T-122 publishes the proof page |
| Q-04 | CircleCI plan: free tier acceptable? | T-103 (MC-04) |
| Q-05 | Custom domain for demo, or Vercel subdomain | T-122 (MC-06, pulled forward) |
| Q-06 | One Next.js route file for both static export and live mode, or two build targets | Decided by the T-117 spike; REQ-URL-01 path style must be preserved |
