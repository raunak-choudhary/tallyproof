"""Request middleware."""

import re
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from config.logging import bind_correlation_id

HEADER = "X-Correlation-ID"
_SAFE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class CorrelationIdMiddleware:
    """Use the caller's correlation ID, or make one, and echo it on the response.

    Only short, plain IDs are accepted from callers, so a header can't inject
    anything into the logs.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Wrap the next handler."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Bind the ID for this request's logs and return it to the caller."""
        given = request.headers.get(HEADER, "")
        correlation_id = given if _SAFE.match(given) else f"req-{uuid.uuid4().hex}"
        bind_correlation_id(correlation_id)
        response = self.get_response(request)
        response[HEADER] = correlation_id
        return response
