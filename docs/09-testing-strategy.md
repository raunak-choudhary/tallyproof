# 09. Testing Strategy

> Covers REQ-QA-04 to REQ-QA-10 and the eval layer (`08-eval-spec.md`).

## 1. Pyramid

| Layer | Scope | Tools | Speed budget | Runs |
|---|---|---|---|---|
| Unit | Pure logic: Merkle, Bloom, canonical JSON, money, reconciliation rules, SQL guard, verifier, journal derivation | pytest, Hypothesis | < 30 s total | Pre-commit (changed), every PR (parallel) |
| Module | One Django app with collaborators faked (fake broker, fake LLM, in-memory repositories) plus test Postgres | pytest-django | < 2 min | Every PR |
| Integration | Real Redpanda + Postgres/pgvector (+ SeaweedFS later) | Testcontainers, machine executor | < 6 min | Every PR after unit |
| E2E backend | Generator to verified answer with recorded LLM responses | pytest | < 4 min | Every PR (smoke), nightly (full) |
| Frontend unit | Verify library, components | Vitest | < 1 min | Every PR |
| Cross-language | Same vectors in pytest and Vitest | shared `testdata/vectors` | seconds | Every PR |
| UI E2E | Landing, verify, tamper, analyst, evals | Playwright + axe | < 5 min | Every PR touching `frontend/` (MLP) |
| Evals | Quality metrics | eval runner | smoke < 3 min | PR smoke, nightly full |

## 2. Property-based tests (Hypothesis)

- Merkle: for any list of leaves and any index, the inclusion proof verifies; flipping any bit in leaf, path, or root makes it fail; consistency proofs verify for all m <= n and fail after rewriting any of the first m leaves.
- Bloom: no false negatives for any inserted set; measured FPR within 1.5x of target at fixed seeds over large samples.
- Journal: every derived entry balances; trial balance is zero.
- Canonical JSON: round trip parse then canonicalize is idempotent.
- SQL guard: generated statements containing any banned node are rejected.

## 3. Rules

- Unit and module tests never call a real LLM (REQ-QA-09). A pytest fixture blocks outbound sockets for those layers; any attempt fails the test.
- No sleeps in tests; use events and timeouts.
- Fixed seeds everywhere; failures print the seed.
- Coverage: >= 85% on `core`, `ledger`, `reconciliation`, `ingestion` dedupe (REQ-QA-08), enforced from E-401; `core` targets >= 95%.
- Tests are named for behavior: `test_tampered_leaf_fails_inclusion_verification`.

## 4. Fakes

`FakeBroker`, `FakeLLMClient` (scripted responses keyed by prompt fingerprint), `FrozenClock`, `InMemoryWitness`. Fakes live in `tests/fakes/` and have their own contract tests against the real implementations (run in the integration layer) so fakes cannot drift.
