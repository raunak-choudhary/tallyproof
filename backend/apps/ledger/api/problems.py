"""RFC 9457 problem details for every API error.

Clients get a stable machine-readable ``type`` and a short human ``detail``,
never stack traces or database messages.
"""

from typing import Any

from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

PROBLEM_BASE = "tag:tallyproof.dev,2026:problem/"
CONTENT_TYPE = "application/problem+json"


class Problem(exceptions.APIException):
    """An API error with its own problem type."""

    def __init__(self, status_code: int, code: str, title: str, detail: str) -> None:
        """Describe the problem; ``code`` becomes the last segment of its type URI."""
        super().__init__(detail=detail, code=code)
        self.status_code = status_code
        self.title = title


def not_found(what: str) -> Problem:
    """A 404 naming what was missing."""
    return Problem(status.HTTP_404_NOT_FOUND, "not-found", "Not found", f"{what} does not exist.")


def handler(error: Exception, context: dict[str, Any]) -> Response | None:
    """Turn any DRF or Django error into a problem response."""
    if isinstance(error, Http404):
        error = not_found("The requested resource")
    response = exception_handler(error, context)
    if response is None:
        return None
    if isinstance(error, Problem):
        problem_type, title = PROBLEM_BASE + str(error.get_codes()), error.title
    else:
        problem_type, title = "about:blank", response.status_text
    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    body: dict[str, Any] = {
        "type": problem_type,
        "title": title,
        "status": response.status_code,
        "detail": str(detail) if detail is not None else title,
        "instance": context["request"].path,
    }
    if isinstance(response.data, dict) and detail is None:
        body["errors"] = response.data  # field validation errors
    response.data = body
    response.content_type = CONTENT_TYPE
    return response
