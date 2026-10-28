# Testing

Tests are layered so the fast ones run constantly and the slow ones run only where they earn their time. Answer quality is measured separately, as described in [evaluation.md](evaluation.md).

## Layers

| Layer | What it covers | Tools | Time budget | When it runs |
|---|---|---|---|---|
| Unit | Pure logic: Merkle log, Bloom filter, canonical JSON, money, reconciliation rules, query compiler, verifier, journal | pytest, Hypothesis | Under 30 seconds | Pre-commit for changed code, every pull request |
| Module | One Django app with its collaborators faked, against a test Postgres | pytest-django | Under 2 minutes | Every pull request |
| Data pipeline | Spark jobs and Deequ checks on the committed sample of about 50k real rows | pytest, PySpark local mode | Under 3 minutes | Pull requests that touch the pipeline |
| Integration | Real Redpanda and Postgres with pgvector, and object storage later | Testcontainers | Under 6 minutes | Pull requests that touch ingestion, the ledger, or infrastructure |
| End to end | Evaluation dataset through Redpanda, ingestion, projections, and the checkpointer, then questions through the API; every cited event is verified through the proof API. Model replies replay from `testdata/llm_recordings/e2e` (`E2E_RECORD=1` re-records) | pytest (`tests/integration/analyst/test_end_to_end.py`) | Under 10 seconds | Every pull request, in the integration job |
| Frontend unit | Verification library and components | Vitest | Under 1 minute | Every pull request |
| Cross-language | The same test vectors checked by Python and TypeScript | Shared files in `testdata/vectors` | Seconds | Every pull request |
| Browser | Landing page, verify, tamper, analyst, and evaluation dashboard flows, with accessibility checks | Playwright, axe | Under 5 minutes | Pull requests that touch the frontend |

## Property-based tests

Hypothesis generates inputs for the code where a single wrong edge case would undermine the project:

- **Merkle log.** For any set of leaves and any index, the inclusion proof verifies, and flipping any bit of the leaf, path, or root makes it fail. Consistency proofs verify between any two sizes and fail if any earlier leaf is rewritten.
- **Bloom filter.** No inserted key is ever reported missing, and the measured false-positive rate stays within 1.5 times the target over large seeded samples.
- **Leaf allocation.** Random rollbacks never leave a gap in leaf indexes.
- **Journal.** Every derived entry balances, and the trial balance is zero.
- **Canonical JSON.** Parsing and re-canonicalizing gives the same bytes.
- **Query guard.** Generated statements containing any banned construct are rejected.

## Rules

- Unit and module tests never call a real LLM. A fixture blocks outbound network access in those layers, and any attempt fails the test.
- No `sleep` in tests. They wait on events with timeouts.
- Seeds are fixed, and a failing test prints its seed.
- Coverage must stay at or above 85% for `tallyproof_core`, the ledger, reconciliation, and ingestion deduplication. `tallyproof_core` aims for 95%.
- Test names describe behavior, for example `test_tampered_leaf_fails_inclusion_verification`.
- A test proves that no deny-listed personal data column survives cleaning, and another scans sample values for email and phone patterns.

## Fakes

The fakes are `FakeBroker`, `FakeLLMClient` (scripted responses keyed by prompt fingerprint), `FrozenClock`, and `InMemoryWitness`. They live in `tests/fakes/`, and each one has contract tests that also run against the real implementation in the integration layer, so a fake can't quietly drift from the thing it stands in for.
