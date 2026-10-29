# Testing

Tests are layered so the fast ones run constantly and the slow ones run where they earn their time. Answer quality is measured separately, as described in [evaluation.md](evaluation.md).

## Layers

| Layer | What it covers | Tools | Time | When it runs |
|---|---|---|---|---|
| Unit | Pure logic: Merkle log, Bloom filter, canonical JSON, money, IDs, checkpoints, reconciliation rules, journal, the analyst's query compiler, SQL guard, router, verifier, model client, and the evaluation scorer and oracle | pytest, Hypothesis | Under 10 seconds | Pre-commit for changed code, every pull request |
| Data pipeline | Spark jobs and Deequ checks on small hand-written CSV fixtures that cover every cleaning rule, plus the committed sample of 2,000 real events | pytest, PySpark local mode | About 1 minute | Every pull request |
| Module | One Django app through its real entry point, with everything outside the app faked: the question endpoint over HTTP with a scripted model, the fan-out from a fake broker to a WebSocket client, `verify_event` against a fake API serving a signed log, the health endpoints, and, against a real Postgres, the ingestion loop and a projection round. Suites live in `backend/tests/module/`, one folder per app | pytest-django, `tests/fakes` | Seconds | Every pull request; suites that need Postgres run in the integration job |
| Integration | Real Redpanda and Postgres containers with the production role script and migrations: ingestion, the ledger and its grants, projections, the outbox, the stream, the analyst's views and endpoints, and the contract test that holds the fake broker to Redpanda's behavior | Testcontainers (`tests/containers.py`) | Under 2 minutes | Every pull request |
| End to end | The evaluation dataset through Redpanda, ingestion, projections, and the checkpointer, then questions through the API; every cited event is verified through the proof API. Model replies replay from `testdata/llm_recordings/e2e` (`E2E_RECORD=1` re-records) | pytest (`tests/integration/analyst/test_end_to_end.py`) | Under 10 seconds | Every pull request, in the integration job |
| Evaluation | The smoke question set through the real pipeline in a throwaway ledger, replaying recorded model responses, scored against the oracle and held to every threshold ([evaluation.md](evaluation.md)) | `make eval` | About 2 minutes | Every pull request (`eval-smoke`) |
| Frontend unit | The verification library, the API clients, and the answer parser | Vitest | Under 1 minute | Every pull request |
| Cross-language | The same test vectors checked by Python and TypeScript | Shared files in `testdata/vectors` | Seconds | Every pull request |
| Browser | Planned with the site: landing, verify, tamper, analyst, and evaluation flows, with accessibility checks | Playwright, axe | | |

Every job runs on every pull request; none is skipped by path. Coverage is measured across the unit, Spark, and integration runs together.

## Property-based tests

Hypothesis generates inputs for the code where a single wrong edge case would undermine the project:

- **Merkle log.** For any set of leaves and any index, the inclusion proof verifies, and flipping any bit of the leaf, path, or root makes it fail. Consistency proofs verify between any two sizes and fail if any earlier leaf is rewritten. The in-memory log tree agrees with the reference implementation.
- **Bloom filter.** No inserted key is ever reported missing, and the measured false-positive rate stays within 1.5 times the target over large seeded samples.
- **Journal.** Every derived entry balances, and the trial balance is zero.
- **Canonical JSON, money, IDs, and checkpoints.** Round trips give the same bytes; malformed input is rejected.

Two more checks use seeded randomness or a fixed corpus rather than Hypothesis. Forty random rollbacks against a real Postgres never leave a gap in leaf indexes (`tests/integration/ledger/test_append.py`). The SQL guard rejects a corpus of 64 hostile queries that covers every rule in the threat model (`tests/unit/analyst/test_sql_guard.py`).

In CI, Hypothesis runs derandomized with 300 examples, so a failure reproduces exactly.

## Rules

- Unit and module tests never call a real model. Every model call goes through the client interface, and tests use the scripted fake; the real client is tested with a fake HTTP session, so it never connects.
- No test reaches another machine. A fixture in `tests/conftest.py` refuses every connection except to loopback and Unix sockets, which leaves the containers, Spark's local gateway, and Docker reachable.
- No `sleep` in tests. Code that waits takes a clock and a sleep function, and tests pass fakes.
- Seeds are fixed.
- Combined coverage must stay at or above 85% across `tallyproof_core`, the pipeline, the settings, the Django apps, and the evaluation harness; it is about 93%.
- Test names describe behavior, for example `test_any_tampered_leaf_fails_verification`.
- Personal data: one test feeds names, addresses, and phone numbers through cleaning and checks none survive anywhere, another stops the build if a deny-listed column appears, and the committed real sample is checked for personal data.

## Fakes

Shared fakes live in `backend/tests/fakes/`:

- `FakeBroker` is Kafka in memory. It produces with keys, headers, and delivery callbacks, and hands out consumers that subscribe, assign from a stored offset, consume, and seek. A contract test runs one script against Redpanda and against the fake and requires identical results (`tests/integration/test_fake_broker_contract.py`).
- `FrozenClock` stands in for `time.time`, `time.monotonic`, and `time.sleep`, and moves only when a test moves it.
- `FakeLLM` is the scripted model client from `apps/analyst/llm.py`, which the evaluation harness also uses.

Fakes for one outside API, such as the HTTP sessions that stand in for USAspending, Treasury, or an OpenTimestamps calendar, stay beside the tests for that client, since each speaks a different API.
