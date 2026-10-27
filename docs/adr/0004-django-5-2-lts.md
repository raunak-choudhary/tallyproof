# ADR-0004: Django 5.2 LTS

- Status: Proposed (MC-01)
- Date: 2026-10-26
- Zone: Strong default (confirmed with corrected facts)

## Context

The brief locks Django and recommends 5.2 LTS. Research on 2026-10-26 (see `docs/research/stack-versions-2026-10.md`):

| Series | Latest | Security support ends |
|---|---|---|
| 5.2 LTS | 5.2.18 | April 2028 |
| 6.0 | 6.0.9 | April 2027 |
| 6.1 | 6.1.2 | December 2027 (not LTS) |
| 6.2 LTS | not released, planned April 2027 | April 2030 |

The brief described 6.1 as "ends extended support December 2027". The date is right, but 6.1 is not an extended-support release. 5.2 LTS outlives it.

## Decision

Use Django 5.2.x (latest patch, pinned via pip-tools) with Python 3.12, DRF 3.18, drf-spectacular 0.30, Channels 4.3 with channels-redis 4.3, Daphne 4.2.

## Reasons

- Longest support window available today.
- All required libraries declare 5.2 compatibility.
- Upgrade path: move to 6.2 LTS after April 2027. Documented, not scheduled.

## Notes

- Django is used for the API, admin (local only), migrations, and Channels. Workers are management commands that import framework-free `ledgerline_core` for the critical logic.
- Channels has had no release in 11 months. Acceptable for this scope; flagged in the risk log.
