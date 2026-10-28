# health

Liveness and readiness endpoints for whatever runs the API.

- `GET /healthz` answers as long as the process is up. It touches no dependency.
- `GET /readyz` runs each check in `checks.py` (the database and the Kafka broker) and answers 503 naming whichever is down, without the underlying error text.

Consumes and produces no events. Tests: `tests/module/health/`.
