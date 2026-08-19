"""
Notification endpoints — Module 12.

    GET    /notifications/                  the bell list  (?unread=1&category=)
    GET    /notifications/unread-count/     badge numbers, one query
    POST   /notifications/mark-read/        some ids, or all when ids is empty
    POST   /notifications/{id}/unread/      undo
    DELETE /notifications/{id}/             remove one
    POST   /notifications/clear/            empty the read ones
    GET    /notifications/preferences/      channel switches
    PATCH  /notifications/preferences/      change them
    GET    /notifications/devices/          registered push tokens
    POST   /notifications/devices/          register (idempotent, every launch)
    POST   /notifications/devices/remove/   deactivate on logout

WHY THERE IS NO "SEND NOTIFICATION" ENDPOINT HERE
------------------------------------------------
Notifications are a consequence of domain events, never a request. Every one is
written by the app that caused it, through `services.notify()`. An endpoint that
let a client post a notification to somebody would be a spam vector with a
platform logo on it — the admin broadcast in Module 14 is the single exception
and it is admin-only, audited and fanned out by a task.

WHY THE LIST DOES NOT MARK ANYTHING READ
----------------------------------------
Opening the bell is not reading the items. Auto-clearing on GET means a badge
that vanishes when the user glances at the screen and then cannot find what it
was about; the app decides, and says so with an explicit POST.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.mixins import MessageResponseMixin, MultiSerializerMixin
from apps.notifications import selectors, services
from apps.notifications.models import Notification
from apps.notifications.serializers import (
    BadgeCountSerializer,
    MarkReadResponseSerializer,
    MarkReadSerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer,
    PushTokenRegisterSerializer,
    PushTokenSerializer,
)


@extend_schema(tags=["Notifications"])
class NotificationViewSet(MessageResponseMixin, MultiSerializerMixin, GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    serializer_classes = {
        "mark_read": MarkReadSerializer,
        "preferences": NotificationPreferenceSerializer,
        "devices": PushTokenRegisterSerializer,
    }
    queryset = Notification.objects.none()  # schema inference only
    success_messages = {
        "mark_read": "Marked as read",
        "clear": "Notifications cleared",
        "destroy": "Notification removed",
        "unread": "Marked as unread",
        "devices": "Device registered for push",
        "remove_device": "Device removed",
    }

    # ─── The bell list ───────────────────────────────────────────────────────
    @extend_schema(
        summary="Your notifications, newest first",
        parameters=[
            OpenApiParameter("unread", bool, description="Only unread ones"),
            OpenApiParameter(
                "category", str,
                description="bookings | messages | reviews | marketplace | "
                            "account | platform",
            ),
        ],
        responses=NotificationSerializer(many=True),
    )
    def list(self, request):
        queryset = selectors.inbox(
            request.user,
            unread_only=request.query_params.get("unread") in ("1", "true", "True"),
            category=request.query_params.get("category"),
        )
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset
        data = NotificationSerializer(
            rows, many=True, context=self.get_serializer_context()
        ).data
        if page is not None:
            response = self.get_paginated_response(data)
            # The badge belongs with the page the app just fetched: two
            # requests to draw one screen would let the list and the number
            # disagree for as long as the second one is in flight.
            response.data["meta"]["unread_count"] = selectors.unread_count(request.user)
            return response
        return Response(data)

    @extend_schema(summary="Unread badge counts", responses=BadgeCountSerializer)
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response(selectors.badge_counts(request.user))

    # ─── Read state ──────────────────────────────────────────────────────────
    @extend_schema(
        summary="Mark notifications read — all of them if ids is empty",
        request=MarkReadSerializer,
        responses=MarkReadResponseSerializer,
    )
    @action(detail=False, methods=["post"], url_path="mark-read")
    def mark_read(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.mark_read(request.user, serializer.validated_data.get("ids"))
        return Response(
            {"updated": updated, "unread_count": selectors.unread_count(request.user)}
        )

    @extend_schema(summary="Mark one back as unread", request=None)
    @action(detail=True, methods=["post"])
    def unread(self, request, pk=None):
        if not services.mark_unread(request.user, int(pk)):
            raise NotFound("Notification not found.")
        return Response(
            {"updated": 1, "unread_count": selectors.unread_count(request.user)}
        )

    @extend_schema(summary="Remove one notification", responses={204: None})
    def destroy(self, request, pk=None):
        if not services.delete_notification(request.user, int(pk)):
            raise NotFound("Notification not found.")
        return Response(status=http.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Clear the notifications you have already read", request=None
    )
    @action(detail=False, methods=["post"])
    def clear(self, request):
        removed = services.clear_inbox(request.user, read_only=True)
        return Response(
            {"removed": removed, "unread_count": selectors.unread_count(request.user)}
        )

    # ─── Preferences ─────────────────────────────────────────────────────────
    @extend_schema(
        summary="Your notification settings",
        request=NotificationPreferenceSerializer,
        responses=NotificationPreferenceSerializer,
    )
    @action(detail=False, methods=["get", "patch"])
    def preferences(self, request):
        prefs = selectors.preferences(request.user)
        if request.method == "GET":
            return Response(NotificationPreferenceSerializer(prefs).data)

        serializer = NotificationPreferenceSerializer(
            prefs, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        updated = services.update_preferences(request.user, **serializer.validated_data)
        return Response(NotificationPreferenceSerializer(updated).data)

    # ─── Devices ─────────────────────────────────────────────────────────────
    @extend_schema(
        summary="Register this device for push (safe to call on every launch)",
        request=PushTokenRegisterSerializer,
        responses={201: PushTokenSerializer},
    )
    @action(detail=False, methods=["get", "post"])
    def devices(self, request):
        if request.method == "GET":
            return Response(
                PushTokenSerializer(
                    selectors.active_push_tokens(request.user), many=True
                ).data
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token, created = services.register_push_token(
            request.user, **serializer.validated_data
        )
        return Response(
            PushTokenSerializer(token).data,
            status=http.HTTP_201_CREATED if created else http.HTTP_200_OK,
        )

    @extend_schema(summary="Stop pushing to this device (call on logout)")
    @action(detail=False, methods=["post"], url_path="devices/remove")
    def remove_device(self, request):
        token = (request.data.get("token") or "").strip()
        if not token:
            raise NotFound("No token supplied.")
        services.unregister_push_token(request.user, token)
        return Response({"removed": True})
