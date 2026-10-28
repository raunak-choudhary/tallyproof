# realtime

Pushes ledger facts to browsers over a WebSocket at `/ws/v1/stream`. The stream is for watching; proofs always come from the REST API.

| Module | What it does |
|---|---|
| `fanout.py` and `management/commands/fanout.py` | Consume `ledger.appended.v1`, `ledger.checkpoints.v1`, and `recon.breaks.v1`, turn each message into a small fact, and send it to the `ledger-stream` group through Redis, from one long-lived event loop |
| `consumers.py` | Accepts connections whose origin is in `DJANGO_ALLOWED_HOSTS`, up to `WS_MAX_CONNECTIONS_PER_IP` per IP, and forwards the group's facts. Each client has its own buffer of `WS_CLIENT_BUFFER` facts; a client that falls behind drops its oldest and receives `{"kind": "facts_dropped", "count": n}` |
| `management/commands/stream.py` | Serves the endpoint under Uvicorn with `STREAM_HOST`, `STREAM_PORT`, and `WS_MAX_MESSAGE_BYTES` |

Fact kinds: `event_appended`, `checkpoint_signed`, `break_found`, `facts_dropped`.

| Command | Make target |
|---|---|
| `fanout` | `make fanout` |
| `stream` | `make stream` |

Uvicorn replaced Daphne, whose Twisted dependency failed the dependency audit ([ADR-0018](../../../docs/adr/0018-uvicorn-for-websockets.md)). Tests: `tests/unit/realtime/`.
