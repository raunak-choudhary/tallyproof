"""OpenTelemetry tracing across ingest, checkpoint, and the analyst.

Off unless ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set: with no endpoint, the tracer is
OpenTelemetry's no-op one and a span costs almost nothing. With one, spans go over
OTLP HTTP in batches to a collector, such as the Jaeger service in compose
(``docker compose --profile tracing``).

Every span carries the correlation ID the logs carry (:mod:`config.logging`), so
a trace and its log lines can be found from each other.
"""

from collections.abc import Iterable

from opentelemetry import trace
from structlog.contextvars import get_contextvars

TRACER_NAME = "tallyproof"
MAX_IDS = 50
"""Correlation IDs recorded on one batch span; a batch can hold hundreds of events."""


def configure_tracing(service: str, endpoint: str | None = None) -> bool:
    """Send this process's spans to ``endpoint``. Returns whether tracing is on."""
    if endpoint is None:
        from config.env import app_settings

        endpoint = app_settings().otel_exporter_otlp_endpoint
    if not endpoint:
        return False
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return True


def tracer() -> trace.Tracer:
    """The project's tracer; a no-op one when tracing is off."""
    return trace.get_tracer(TRACER_NAME)


def current_correlation_id() -> str | None:
    """The correlation ID bound for logging in this context, if any."""
    value = get_contextvars().get("correlation_id")
    return None if value is None else str(value)


def correlation_ids(ids: Iterable[str]) -> list[str]:
    """Distinct IDs in first-seen order, at most ``MAX_IDS`` of them, for a span attribute."""
    seen: dict[str, None] = {}
    for value in ids:
        if value and value not in seen:
            seen[value] = None
            if len(seen) == MAX_IDS:
                break
    return list(seen)
