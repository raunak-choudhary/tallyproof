"""Structured JSON logging shared by the API and every worker.

Each log line is one JSON object. A correlation ID bound with
:func:`bind_correlation_id` is added to every line logged in that context, so
one ID can be followed from the producer through ingestion, the ledger, and the
API (the event's ``correlation_id`` is stored with it in the ledger).
"""

import logging
import sys

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

SHARED_PROCESSORS: list[structlog.typing.Processor] = [
    merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]


def configure(level: int = logging.INFO) -> None:
    """Send structlog and standard library logs to stdout as JSON lines."""
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    structlog.configure(
        processors=[*SHARED_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def bind_correlation_id(correlation_id: str) -> None:
    """Attach a correlation ID to every log line in the current context."""
    clear_contextvars()
    bind_contextvars(correlation_id=correlation_id)
