"""Liveness and readiness endpoints for orchestrators and load balancers."""

from django.core.cache import cache
from django.http import HttpRequest, JsonResponse

from apps.health import checks

READY_CACHE_SECONDS = 5
"""How long a readiness result is reused. The endpoint is public and unthrottled,
and each check opens a connection, so a flood of requests runs the checks once."""


def healthz(request: HttpRequest) -> JsonResponse:
    """Report that the process is up. Touches no dependency."""
    return JsonResponse({"status": "ok"})


def readyz(request: HttpRequest) -> JsonResponse:
    """Report whether every dependency answers. Returns 503 naming any that don't."""
    results: dict[str, str] | None = cache.get("readyz")
    if results is None:
        results = {}
        for name, check in checks.CHECKS.items():
            try:
                check()
            except Exception:
                results[name] = "unavailable"
            else:
                results[name] = "ok"
        cache.set("readyz", results, READY_CACHE_SECONDS)
    ready = all(status == "ok" for status in results.values())
    return JsonResponse(
        {"status": "ready" if ready else "not ready", "checks": results},
        status=200 if ready else 503,
    )
