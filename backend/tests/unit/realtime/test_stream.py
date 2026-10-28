import json
from typing import Any

from asgiref.sync import async_to_sync
from asgiref.testing import ApplicationCommunicator
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from django.test import override_settings

from apps.realtime.consumers import GROUP
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
