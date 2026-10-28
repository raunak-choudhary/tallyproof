# ADR-0004: Django 5.2 LTS

- Status: Accepted. The WebSocket server was changed to Uvicorn by [ADR-0018](0018-uvicorn-for-websockets.md).
- Date: 2026-10-26

## Context

The backend uses Django. Support windows, checked in October 2026:

| Series | Latest | Security support ends |
|---|---|---|
| 5.2 LTS | 5.2.18 | April 2028 |
| 6.0 | 6.0.9 | April 2027 |
| 6.1 | 6.1.2 | December 2027 (not LTS) |
| 6.2 LTS | not released, planned April 2027 | April 2030 |

Django 6.1 is newer, but it isn't a long-term support release, and its security support ends in December 2027, four months before 5.2's.

## Decision

Use Django 5.2.x (latest patch, pinned via pip-tools) with Python 3.12, DRF 3.18, drf-spectacular 0.30, Channels 4.3 with channels-redis 4.3, Daphne 4.2.

## Reasons

- Longest support window available today.
- All required libraries declare 5.2 compatibility.
- Upgrade path: move to 6.2 LTS after April 2027. Documented, not scheduled.

## Notes

- Django is used for the API, admin (local only), migrations, and Channels. Workers are management commands that import framework-free `tallyproof_core` for the critical logic.
- Channels has had no release in 11 months. Acceptable for this scope; flagged in the risk log.
