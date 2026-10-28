"""Liveness and readiness endpoints for orchestrators and load balancers."""

from django.http import HttpRequest, JsonResponse

from apps.health import checks


def healthz(request: HttpRequest) -> JsonResponse:
    """Report that the process is up. Touches no dependency."""
    return JsonResponse({"status": "ok"})


def readyz(request: HttpRequest) -> JsonResponse:
    """Report whether every dependency answers. Returns 503 naming any that don't."""
    results: dict[str, str] = {}
    for name, check in checks.CHECKS.items():
        try:
            check()
        except Exception:
            results[name] = "unavailable"
        else:
            results[name] = "ok"
    ready = all(status == "ok" for status in results.values())
    return JsonResponse(
        {"status": "ready" if ready else "not ready", "checks": results},
        status=200 if ready else 503,
    )
