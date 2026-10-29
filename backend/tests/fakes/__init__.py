"""Shared fakes for unit, module, and integration tests.

- :class:`FakeBroker` and :class:`FakeMessage`: Kafka in memory, as confluent-kafka
  presents it, checked against Redpanda by a contract test.
- :class:`FrozenClock`: time that moves only when a test moves it.
- :class:`FakeLLM`: the scripted model client from ``apps.analyst.llm``, which the
  evaluation harness also uses, re-exported so tests import every fake from here.
"""

from apps.analyst.llm import FakeClient as FakeLLM
from tests.fakes.broker import FakeBroker, FakeConsumer, FakeError, FakeMessage
from tests.fakes.clock import FrozenClock

__all__ = [
    "FakeBroker",
    "FakeConsumer",
    "FakeError",
    "FakeLLM",
    "FakeMessage",
    "FrozenClock",
]
