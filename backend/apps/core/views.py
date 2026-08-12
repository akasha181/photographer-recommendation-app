"""Infrastructure endpoints (not part of the business API)."""

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health_check(request):
    """
    Liveness + dependency probe used by the load balancer and by `make check`.

    Returns 200 only when the database and cache both respond; anything else
    means the process is running but cannot actually serve traffic.
    """
    checks = {}
    healthy = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc.__class__.__name__}"
        healthy = False

    try:
        cache.set("__health__", "1", 10)
        checks["cache"] = "ok" if cache.get("__health__") == "1" else "error: no readback"
        healthy = healthy and checks["cache"] == "ok"
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = f"error: {exc.__class__.__name__}"
        healthy = False

    return JsonResponse(
        {
            "success": healthy,
            "message": "Healthy" if healthy else "Degraded",
            "data": {"status": "healthy" if healthy else "degraded", "checks": checks},
            "meta": {"request_id": getattr(request, "request_id", None)},
        },
        status=200 if healthy else 503,
    )
