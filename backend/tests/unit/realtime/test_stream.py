import asyncio
import json
from collections import deque
from types import SimpleNamespace
from typing import Any

from asgiref.sync import async_to_sync
from asgiref.testing import ApplicationCommunicator
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from django.test import override_settings

from apps.realtime import consumers
from apps.realtime.consumers import GROUP, LedgerStreamConsumer
from apps.realtime.fanout import to_fact
from apps.realtime.routing import websocket_urlpatterns

IN_MEMORY = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def test_topic_messages_become_typed_facts():
    value = json.dumps({"event_id": "evt_1", "leaf_index": 3}).encode()
    fact = to_fact("ledger.appended.v1", value)
    assert fact == {"kind": "event_appended", "event_id": "evt_1", "leaf_index": 3}
    found = to_fact("recon.breaks.v1", b'{"break_id": "brk_1"}')
    assert found is not None
    assert found["kind"] == "break_found"
    assert to_fact("fin.events.raw.v1", value) is None
    assert to_fact("ledger.appended.v1", None) is None


@override_settings(CHANNEL_LAYERS=IN_MEMORY)
def test_connected_clients_receive_broadcast_facts():
    scope: dict[str, Any] = {"type": "websocket", "path": "/ws/v1/stream", "headers": []}

    async def scenario() -> None:
        client = ApplicationCommunicator(URLRouter(websocket_urlpatterns), scope)
        await client.send_input({"type": "websocket.connect"})
        assert (await client.receive_output(timeout=2))["type"] == "websocket.accept"
        layer = get_channel_layer()
        assert layer is not None
        fact = {"kind": "checkpoint_signed", "tree_size": 9}
        await layer.group_send(GROUP, {"type": "ledger.fact", "fact": fact})
        sent = await client.receive_output(timeout=2)
        assert json.loads(sent["text"]) == fact
        await client.send_input({"type": "websocket.receive", "text": '{"anything": "ignored"}'})
        assert await client.receive_nothing(timeout=0.2)
        await client.send_input({"type": "websocket.disconnect", "code": 1000})

    async_to_sync(scenario)()


def limits(**overrides: int) -> SimpleNamespace:
    values = {"ws_max_connections_per_ip": 5, "ws_client_buffer": 100} | overrides
    return SimpleNamespace(**values)


def test_a_client_that_falls_behind_keeps_the_latest_facts_and_learns_what_it_missed():
    consumer = LedgerStreamConsumer()
    consumer.pending = deque(maxlen=2)
    consumer.dropped = 0
    sent: list[dict[str, Any]] = []

    async def scenario() -> None:
        consumer.ready = asyncio.Event()
        for n in range(5):  # arrive faster than the client reads
            await consumer.ledger_fact({"fact": {"kind": "event_appended", "leaf_index": n}})

        async def record(content: dict[str, Any], close: bool = False) -> None:
            sent.append(content)

        consumer.send_json = record  # type: ignore[method-assign]
        task = asyncio.create_task(consumer._send_pending())
        await asyncio.sleep(0.05)
        task.cancel()

    async_to_sync(scenario)()
    assert sent == [
        {"kind": "facts_dropped", "count": 3},
        {"kind": "event_appended", "leaf_index": 3},
        {"kind": "event_appended", "leaf_index": 4},
    ]


@override_settings(CHANNEL_LAYERS=IN_MEMORY)
def test_connections_beyond_the_per_ip_cap_are_refused(monkeypatch):
    monkeypatch.setattr(consumers, "app_settings", lambda: limits(ws_max_connections_per_ip=1))
    scope: dict[str, Any] = {
        "type": "websocket",
        "path": "/ws/v1/stream",
        "headers": [],
        "client": ("203.0.113.9", 50000),
    }

    async def scenario() -> None:
        first = ApplicationCommunicator(URLRouter(websocket_urlpatterns), scope)
        await first.send_input({"type": "websocket.connect"})
        assert (await first.receive_output(timeout=2))["type"] == "websocket.accept"
        second = ApplicationCommunicator(URLRouter(websocket_urlpatterns), scope)
        await second.send_input({"type": "websocket.connect"})
        refused = await second.receive_output(timeout=2)
        assert refused == {"type": "websocket.close", "code": consumers.TRY_AGAIN_LATER}
        await first.send_input({"type": "websocket.disconnect", "code": 1000})
        await first.wait(timeout=2)
        third = ApplicationCommunicator(URLRouter(websocket_urlpatterns), scope)
        await third.send_input({"type": "websocket.connect"})
        assert (await third.receive_output(timeout=2))["type"] == "websocket.accept"
        await third.send_input({"type": "websocket.disconnect", "code": 1000})

    async_to_sync(scenario)()


def test_the_stream_command_serves_with_limits_from_settings(monkeypatch):
    from django.core.management import call_command

    from apps.realtime.management.commands import stream

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: calls.append({"app": app, **kwargs}))
    monkeypatch.setattr(
        stream,
        "app_settings",
        lambda: SimpleNamespace(
            stream_host="127.0.0.1", stream_port=8001, ws_max_message_bytes=4096, log_level="INFO"
        ),
    )
    call_command("stream")
    assert calls == [
        {
            "app": "config.asgi:application",
            "host": "127.0.0.1",
            "port": 8001,
            "ws_max_size": 4096,
            "log_level": "info",
        }
    ]


def test_the_stream_server_serves_no_http():
    from config.asgi import application

    async def scenario() -> None:
        scope = {"type": "http", "method": "GET", "path": "/api/v1/queries", "headers": []}
        client = ApplicationCommunicator(application, scope)
        await client.send_input({"type": "http.request", "body": b"", "more_body": False})
        start = await client.receive_output(timeout=2)
        assert (start["type"], start["status"]) == ("http.response.start", 404)
        body = await client.receive_output(timeout=2)
        assert body["type"] == "http.response.body"

    async_to_sync(scenario)()
