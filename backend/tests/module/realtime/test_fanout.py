"""The realtime app end to end in one process: Kafka topics in, WebSocket facts out.

Messages go onto a fake broker, the fan-out loop reads them, and a client connected
to the real WebSocket route receives the facts through an in-memory channel layer.
"""

import json
from typing import Any

from asgiref.sync import async_to_sync
from asgiref.testing import ApplicationCommunicator
from channels.routing import URLRouter
from django.test import override_settings

from apps.realtime.fanout import pump
from apps.realtime.routing import websocket_urlpatterns
from tests.fakes import FakeBroker, FakeError, FakeMessage

IN_MEMORY = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
APPENDED, CHECKPOINTS, BREAKS = "ledger.appended.v1", "ledger.checkpoints.v1", "recon.breaks.v1"


def once() -> Any:
    """A should_stop that lets the loop run one round."""
    rounds = iter([False, True])
    return lambda: next(rounds, True)


@override_settings(CHANNEL_LAYERS=IN_MEMORY)
def test_facts_from_every_ledger_topic_reach_a_connected_client():
    broker = FakeBroker()
    broker.produce(APPENDED, value=json.dumps({"event_id": "evt_1", "leaf_index": 0}).encode())
    broker.produce(CHECKPOINTS, value=json.dumps({"tree_size": 1}).encode())
    broker.produce(BREAKS, value=json.dumps({"break_id": "brk_1"}).encode())
    broker.produce("fin.events.raw.v1", value=b'{"not": "a fact"}')
    broker.inject(FakeMessage(APPENDED, None, 1, _error=FakeError()))
    consumer = broker.consumer()
    consumer.subscribe([APPENDED, CHECKPOINTS, BREAKS, "fin.events.raw.v1"])
    scope = {"type": "websocket", "path": "/ws/v1/stream", "headers": [], "client": ("10.0.0.1", 1)}

    async def scenario() -> list[dict[str, Any]]:
        client = ApplicationCommunicator(URLRouter(websocket_urlpatterns), scope)
        await client.send_input({"type": "websocket.connect"})
        assert (await client.receive_output(timeout=2))["type"] == "websocket.accept"
        await pump(consumer, once())
        received = [json.loads((await client.receive_output(timeout=2))["text"]) for _ in range(3)]
        assert await client.receive_nothing(timeout=0.2)
        await client.send_input({"type": "websocket.disconnect", "code": 1000})
        return received

    assert async_to_sync(scenario)() == [
        {"kind": "event_appended", "event_id": "evt_1", "leaf_index": 0},
        {"kind": "checkpoint_signed", "tree_size": 1},
        {"kind": "break_found", "break_id": "brk_1"},
    ]


@override_settings(CHANNEL_LAYERS=IN_MEMORY)
def test_an_unreadable_message_is_skipped_and_the_loop_keeps_going():
    broker = FakeBroker()
    broker.produce(APPENDED, value=b"{not json")
    broker.produce(APPENDED, value=b"[1, 2]")
    broker.produce(APPENDED, value=json.dumps({"event_id": "evt_2", "leaf_index": 1}).encode())
    consumer = broker.consumer()
    consumer.subscribe([APPENDED])
    scope = {"type": "websocket", "path": "/ws/v1/stream", "headers": [], "client": ("10.0.0.2", 1)}

    async def scenario() -> dict[str, Any]:
        client = ApplicationCommunicator(URLRouter(websocket_urlpatterns), scope)
        await client.send_input({"type": "websocket.connect"})
        await client.receive_output(timeout=2)
        await pump(consumer, once())
        fact: dict[str, Any] = json.loads((await client.receive_output(timeout=2))["text"])
        await client.send_input({"type": "websocket.disconnect", "code": 1000})
        return fact

    assert async_to_sync(scenario)() == {
        "kind": "event_appended",
        "event_id": "evt_2",
        "leaf_index": 1,
    }
