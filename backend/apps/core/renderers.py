"""
Response renderer that wraps every successful payload in the standard
envelope. Errors are already shaped by core.exceptions, so they pass through
untouched.
"""

from rest_framework.renderers import JSONRenderer


class EnvelopeJSONRenderer(JSONRenderer):
    """
    Guarantees the client always receives:

        {"success": bool, "message": str, "data": ..., "meta": {...}}

    A view can control the message by returning
    ``Response({"message": "...", "data": {...}})`` or by setting
    ``response.success_message``.
    """

    def render(self, data, accepted_media_type=None, renderer_context=None):
        renderer_context = renderer_context or {}
        response = renderer_context.get("response")
        request = renderer_context.get("request")

        # Errors, and anything already enveloped, pass straight through.
        if isinstance(data, dict) and "success" in data and "message" in data:
            return super().render(data, accepted_media_type, renderer_context)

        # 204 NO CONTENT and 205 RESET CONTENT must not have a response body
        if response is not None and response.status_code in (204, 205):
            return b""

        if response is not None and response.status_code >= 400:
            return super().render(data, accepted_media_type, renderer_context)

        request_id = getattr(request, "request_id", None) if request else None
        message = getattr(response, "success_message", None) if response else None
        meta = {"request_id": request_id}

        # Paginators put their metadata under "meta" already (see pagination.py).
        if isinstance(data, dict) and set(data.keys()) >= {"data", "meta"}:
            payload = data["data"]
            meta = {**data["meta"], **meta}
        elif isinstance(data, dict) and "message" in data and "data" in data:
            message = data["message"]
            payload = data["data"]
        else:
            payload = data

        if message is None:
            message = self._default_message(request, response)

        return super().render(
            {"success": True, "message": message, "data": payload, "meta": meta},
            accepted_media_type,
            renderer_context,
        )

    @staticmethod
    def _default_message(request, response) -> str:
        method = getattr(request, "method", "GET")
        code = getattr(response, "status_code", 200)
        if code == 201:
            return "Created successfully"
        if code == 204:
            return "Deleted successfully"
        return {
            "GET": "Retrieved successfully",
            "POST": "Created successfully",
            "PUT": "Updated successfully",
            "PATCH": "Updated successfully",
            "DELETE": "Deleted successfully",
        }.get(method, "OK")
