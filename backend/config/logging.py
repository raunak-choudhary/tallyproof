"""Structured JSON logging shared by the API and every worker.

Each log line is one JSON object. A correlation ID bound with
:func:`bind_correlation_id` is added to every line logged in that context, so
one ID can be followed from the producer through ingestion, the ledger, and the
API (the event's ``correlation_id`` is stored with it in the ledger).

Secrets never reach a log line: fields named like a secret are replaced, and a
password inside a connection string is masked wherever it appears.
"""

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

REDACTED = "[redacted]"
SECRET_FIELD = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|private[_-]?key)", re.I
)
URL_CREDENTIALS = re.compile(
    r"(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<user>[^:/@\s]+):(?P<password>[^@/\s]+)@", re.I
)


def _mask(value: object) -> object:
    if isinstance(value, str):
        return URL_CREDENTIALS.sub(rf"\g<scheme>\g<user>:{REDACTED}@", value)
    return value


def redact_secrets(
    _logger: object, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Replace secret-named fields and passwords embedded in URLs."""
    for key, value in event_dict.items():
        event_dict[key] = REDACTED if SECRET_FIELD.search(key) else _mask(value)
    return event_dict


SHARED_PROCESSORS: list[structlog.typing.Processor] = [
    merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    redact_secrets,
]


def configure(level: str | None = None, fmt: str | None = None) -> None:
    """Send structlog and standard library logs to stdout.

    Args:
        level: A logging level name; ``LOG_LEVEL`` when omitted.
        fmt: ``json`` for one JSON object per line, or ``console`` for readable
            lines while developing; ``LOG_FORMAT`` when omitted.
    """
    if level is None or fmt is None:
        from config.env import app_settings

        settings = app_settings()
        level = level or settings.log_level
        fmt = fmt or settings.log_format
    renderer: structlog.typing.Processor = (
        structlog.dev.ConsoleRenderer(colors=False)
        if fmt == "console"
        else structlog.processors.JSONRenderer(sort_keys=True)
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            # Again after formatting: a traceback's text can carry a connection string.
            redact_secrets,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    structlog.configure(
        processors=[*SHARED_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


def bind_correlation_id(correlation_id: str) -> None:
    """Attach a correlation ID to every log line in the current context."""
    clear_contextvars()
    bind_contextvars(correlation_id=correlation_id)
