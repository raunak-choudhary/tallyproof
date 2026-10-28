# ADR-0018: Uvicorn instead of Daphne for the WebSocket server

- Status: Accepted
- Date: 2026-10-28
- Changes: the server named in [ADR-0004](0004-django-5-2-lts.md)

## Context

ADR-0004 picked Daphne, the server the Channels project maintains, for WebSockets. Daphne runs on Twisted. When Daphne was added to the lock file, `pip-audit` reported seven known vulnerabilities against the Twisted release it pulled in. The project's rule is that the audit stays clean, so a known vulnerability is a reason to change a dependency, not to suppress the finding.

## Decision

Serve the ASGI application with Uvicorn and the `websockets` library. Channels and channels-redis stay as they are. The REST API keeps running under gunicorn on its own port, and the WebSocket endpoint runs under Uvicorn on another, so a slow WebSocket client can't hold a REST worker.

Tests that used `channels.testing`, which imports Daphne, use asgiref's `ApplicationCommunicator` instead.

## Reasons

- The audit is clean again, with no ignored findings.
- Uvicorn is a widely used ASGI server. Channels only needs a server that speaks ASGI.
- Running the stream separately from the REST API keeps the two from competing for workers.

## Alternatives considered

- Keep Daphne and ignore the findings until Twisted fixes them. That trades a known issue for convenience, and the ignore list tends to outlive the reason for it.
- Hypercorn. Also fine, but less widely deployed than Uvicorn.

## Consequences

- `make stream` and `make demo` start Uvicorn on port 8001.
- Origin checking moves into the ASGI application (`AllowedHostsOriginValidator`), since Uvicorn doesn't do it.
