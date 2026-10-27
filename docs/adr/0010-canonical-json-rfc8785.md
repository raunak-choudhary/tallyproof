# ADR-0010: RFC 8785 canonical JSON for leaf bytes

- Status: Proposed (MC-01)
- Date: 2026-10-26

## Context

A leaf hash must be reproducible byte-for-byte by Python (server) and TypeScript (browser). Ordinary `json.dumps` and `JSON.stringify` differ in key order, whitespace, Unicode escaping, and number formatting.

## Decision

- Canonicalize with RFC 8785 (JSON Canonicalization Scheme). Python: `rfc8785` (Trail of Bits, used by Sigstore). TypeScript: `canonicalize` (by an RFC 8785 co-author). Do **not** use the Python `canonicaljson` package, which implements a different (Matrix) spec.
- Money and rates are decimal **strings** in events, never JSON numbers, so float formatting can never diverge.
- Shared golden vectors (`testdata/vectors/`) including the RFC appendix vectors run in both pytest and Vitest.
- Store the exact canonical bytes (`canonical_bytes`) alongside the parsed payload, so verification never depends on re-serializing from JSONB.
