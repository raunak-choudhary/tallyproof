"""Tracing: off without an endpoint, and spans carry what a trace reader needs."""

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from structlog.contextvars import bound_contextvars

from config.tracing import (
    MAX_IDS,
    configure_tracing,
    correlation_ids,
    current_correlation_id,
)
from tests.fakes import FrozenClock
from tests.unit.analyst.test_llm import Session, ok, real, request

_exporter = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def provider() -> None:
    # A global provider can be set once per process; tests share this in-memory one.
    current = trace.get_tracer_provider()
    if not isinstance(current, TracerProvider):
        sdk = TracerProvider()
        sdk.add_span_processor(SimpleSpanProcessor(_exporter))
        trace.set_tracer_provider(sdk)
    else:
        current.add_span_processor(SimpleSpanProcessor(_exporter))


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    _exporter.clear()
    yield _exporter
    _exporter.clear()


def test_tracing_is_off_without_an_endpoint() -> None:
    assert configure_tracing("tallyproof-test", "") is False


def test_correlation_ids_are_distinct_and_capped() -> None:
    assert correlation_ids(["a", "b", "a", "", "c"]) == ["a", "b", "c"]
    assert len(correlation_ids(str(n) for n in range(500))) == MAX_IDS


def test_the_logging_correlation_id_is_visible_to_spans() -> None:
    before = current_correlation_id()
    with bound_contextvars(correlation_id="req-123"):
        assert current_correlation_id() == "req-123"
    assert current_correlation_id() == before


def test_a_model_call_is_one_span_with_its_model_and_tokens(spans: InMemorySpanExporter) -> None:
    real(Session(ok()), FrozenClock()).complete(request())
    (span,) = [s for s in spans.get_finished_spans() if s.name == "llm.complete"]
    attributes = dict(span.attributes or {})
    assert attributes["gen_ai.usage.input_tokens"] == 12
    assert attributes["gen_ai.usage.output_tokens"] == 5
    assert "gen_ai.request.model" in attributes
