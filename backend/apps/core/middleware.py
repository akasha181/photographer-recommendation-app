"""Request-scoped middleware."""

import logging
import time
import uuid

logger = logging.getLogger("snapsphere")


class RequestIDMiddleware:
    """
    Attaches a unique id to every request.

    The id is echoed in the response header, in the response envelope's `meta`
    block, and in every log line produced while handling the request. When a
    user reports "booking failed at 3pm", you paste their request id into the
    log search and see the exact trace — instead of guessing.
    """

    HEADER = "HTTP_X_REQUEST_ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Honour a client-supplied id so mobile crash reports can be correlated.
        request.request_id = request.META.get(self.HEADER) or f"req_{uuid.uuid4().hex[:12]}"
        start = time.perf_counter()

        response = self.get_response(request)

        duration_ms = (time.perf_counter() - start) * 1000
        response["X-Request-ID"] = request.request_id

        if request.path.startswith("/api/"):
            user = getattr(request, "user", None)
            logger.info(
                "%s %s %s %.1fms",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
                extra={
                    "request_id": request.request_id,
                    "user_id": getattr(user, "id", None),
                    "duration_ms": round(duration_ms, 1),
                },
            )
        return response
