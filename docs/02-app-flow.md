# 02. App Flow

> Every screen and user journey. Routes follow REQ-URL-01. "Replay" means the public static demo; "Live" means the local full stack.

## 1. Screens

| Route | Screen | Live | Replay | Phase |
|---|---|---|---|---|
| `/` | Landing with motion story | Yes | Yes | 1 (static hero), 5 (motion) |
| `/how-it-works` | Long-form explainer: pipeline, Merkle log, tamper ladder, evals | Yes | Yes | 5 |
| `/stream` | Live event stream, batches closing, breaks appearing | WebSocket | Recorded timeline | 2 (basic), 5 |
| `/ledger/batches` | Batch list with checkpoints | Yes | Yes | 5 |
| `/ledger/batches/[batchId]` | Batch detail: range, root, signature, consistency with previous | Yes | Yes | 5 |
| `/ledger/events/[eventId]` | Event detail, proof path, Verify, tamper toggle | Yes | Yes (bundle events) | 1 |
| `/analyst` | Ask a question (Live) or pick a recorded question (Replay) | Yes | Fixed list | 3 |
| `/answers/[answerId]` | Answer with claims, slots, citations, Verify all | Yes | Yes | 3, 5 |
| `/tamper` | Guided tamper ladder levels 1 to 4 | Yes | Yes | 5 |
| `/evals` | Metrics across runs, baseline comparison | Yes | Yes | 5 |
| `/evals/runs/[runId]` | Per-question results | Yes | Yes | 5 |
| `/verify` | Paste-in verifier: event JSON + proof + checkpoint + public key | Yes | Yes | 5 (proposed addition) |

Global elements: header with mode badge ("Live" or "Replay of run `<sha>`"), theme toggle, link to GitHub and docs.

## 2. Journeys

### J1. Recruiter, 2 minutes (Replay)
1. `/`: hero animation shows an invoice event flowing through the stream, becoming a leaf, rising through the tree to a signed root, and appearing as a citation chip in an answer.
2. CTA "Try to break it" goes to `/tamper`.
3. Step 1: the cited event is shown with a green Verified badge. User changes the amount from 1,250.00 to 1,950.00. Verify turns red: "Leaf hash mismatch (level 1)".
4. Steps 2 to 4 escalate the attacker; each fails at a different, explained mechanism.
5. Close: "Level 5 is not detectable. Here's why and what production does about it." This candor is part of the pitch.

### J2. Analyst question (Live)
1. `/analyst`, type a question.
2. Streaming status: routing, querying, composing, verifying.
3. Answer page: sentences with highlighted value chips and citation chips.
4. Click a value: SQL shown (read-only), contributing events listed, "Recompute in browser" sums them and matches.
5. Click a citation: event JSON, proof path animation, Verify.
6. Refusal case: banner with typed reason and what evidence was missing.

### J3. Data engineer (Live)
1. `make up && make seed && make demo`.
2. `/stream`: per-partition lanes, consumer lag gauge, batch closures, breaks.
3. Redpanda Console in another tab shows topics.
4. `make check-totals` prints control totals table: topic, ledger, lake.

### J4. AI engineer (Replay or Live)
1. `/evals`: metric cards, trend lines across runs, baseline column.
2. Drill into a failing question: expected versus actual, cited versus expected events.

## 3. States every screen must handle

Loading (skeletons, not spinners), empty, error (RFC 9457 problem details shown humanely), offline (Live), not-in-replay (Replay), reduced motion, dark and light.
