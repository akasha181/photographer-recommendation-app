"""
Administration endpoints — Module 14. Mounted at /api/v1/admin/.

    GET  /admin/dashboard/                      queues + totals + trend
    GET  /admin/approvals/                      ?status=PENDING
    POST /admin/approvals/{id}/approve|reject|more-info/
    GET  /admin/flags/                          ?status=OPEN&content_type=REVIEW
    POST /admin/flags/{id}/claim|resolve/
    GET  /admin/users/                          ?role=&blocked=&q=
    GET  /admin/users/{id}/                     + cross-app stats
    POST /admin/users/{id}/block|unblock|adjust-wallet/
    GET  /admin/topups/                         ?status=PENDING
    POST /admin/topups/{id}/approve|reject/
    GET  /admin/products/                       the copyright queue
    POST /admin/products/{id}/approve|remove/
    POST /admin/bookings/{id}/force-cancel/
    GET  /admin/audit/                          append-only, read-only
    GET  /admin/settings/  ·  PATCH /admin/settings/{key}/
    GET  /admin/settings/public/                unauthenticated app config
    POST /admin/broadcasts/                     announcement, fanned out by a task

WHY THERE IS NO WEB DASHBOARD IN THIS REPO
-----------------------------------------
Stated plainly rather than left as a gap: the proposal's admin surface is
delivered as this API plus the Django admin at /django-admin/ (which registers
`AuditLog` read-only). A React admin SPA would be a second frontend with its own
auth, build and deploy story, for an audience of one — and none of the rules
above live in it, because every one of them is enforced here.

EVERY ENDPOINT IS `IsAdmin`, EXCEPT ONE
--------------------------------------
`settings/public/` is `AllowAny` because the app reads it before login — it
carries only rows explicitly marked `is_public`. Everything else requires the
ADMIN role: `IsAdmin` checks `user.role`, so a photographer with a valid token
gets 403, not a filtered view.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.administration import selectors, services
from apps.administration.models import ApprovalRequest, ModerationFlag, PlatformSetting
from apps.administration.serializers import (
    AdminDashboardSerializer,
    AdminProductSerializer,
    AdminTopUpSerializer,
    AdminUserDetailSerializer,
    AdminUserSerializer,
    ApprovalDecisionSerializer,
    ApprovalRequestSerializer,
    AuditLogSerializer,
    BlockUserSerializer,
    BroadcastSerializer,
    FlagResolutionSerializer,
    ForceCancelSerializer,
    ModerationFlagSerializer,
    PlatformSettingSerializer,
    RejectionSerializer,
    SettingWriteSerializer,
    TopUpDecisionSerializer,
    TopUpRejectionSerializer,
    UnblockUserSerializer,
    WalletAdjustmentSerializer,
)
from apps.core.mixins import (
    ActionPermissionsMixin,
    MessageResponseMixin,
    MultiSerializerMixin,
)
from apps.core.pagination import LargePagination
from apps.core.permissions import IsAdmin


class _AdminViewSet(
    MessageResponseMixin, MultiSerializerMixin, ActionPermissionsMixin, GenericViewSet
):
    """Shared base: admin-only, larger pages, uniform helpers."""

    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = LargePagination

    def _page(self, queryset, serializer_class):
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset
        data = serializer_class(
            rows, many=True, context=self.get_serializer_context()
        ).data
        return (
            self.get_paginated_response(data) if page is not None else Response(data)
        )


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Admin"])
class AdminDashboardViewSet(_AdminViewSet):
    serializer_class = AdminDashboardSerializer
    queryset = PlatformSetting.objects.none()  # schema inference only
    pagination_class = None

    @extend_schema(
        summary="Queue depths, platform totals and a daily trend",
        parameters=[OpenApiParameter("days", int, description="Trend window, max 365")],
        responses=AdminDashboardSerializer,
    )
    def list(self, request):
        days = request.query_params.get("days")
        return Response(
            selectors.dashboard(days=int(days) if days and days.isdigit() else 30)
        )


# ═══════════════════════════════════════════════════════════════════════════
# PHOTOGRAPHER APPROVALS
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Admin"])
class ApprovalViewSet(_AdminViewSet):
    serializer_class = ApprovalRequestSerializer
    serializer_classes = {
        "approve": ApprovalDecisionSerializer,
        "reject": RejectionSerializer,
        "more_info": RejectionSerializer,
    }
    queryset = ApprovalRequest.objects.none()
    success_messages = {
        "approve": "Photographer approved and notified",
        "reject": "Application rejected and the reason sent",
        "more_info": "More information requested",
    }

    def _request_row(self, pk) -> ApprovalRequest:
        row = selectors.get_approval_request(pk)
        if row is None:
            raise NotFound("Application not found.")
        return row

    @extend_schema(
        summary="The approval queue, oldest first",
        parameters=[
            OpenApiParameter(
                "status", str, description="PENDING | APPROVED | REJECTED | MORE_INFO"
            )
        ],
        responses=ApprovalRequestSerializer(many=True),
    )
    def list(self, request):
        return self._page(
            selectors.approval_queue(status=request.query_params.get("status")),
            ApprovalRequestSerializer,
        )

    @extend_schema(summary="One application", responses=ApprovalRequestSerializer)
    def retrieve(self, request, pk=None):
        return Response(
            ApprovalRequestSerializer(
                self._request_row(pk), context=self.get_serializer_context()
            ).data
        )

    @extend_schema(summary="Approve — the profile goes live immediately")
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.approve_photographer(
            self._request_row(pk),
            request.user,
            note=serializer.validated_data.get("note", ""),
            request=request,
        )
        return Response(ApprovalRequestSerializer(row, context=self.get_serializer_context()).data)

    @extend_schema(summary="Reject, with a reason the applicant is sent")
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.reject_photographer(
            self._request_row(pk),
            request.user,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(ApprovalRequestSerializer(row, context=self.get_serializer_context()).data)

    @extend_schema(summary="Ask for more information instead of deciding")
    @action(detail=True, methods=["post"], url_path="more-info")
    def more_info(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.request_more_info(
            self._request_row(pk),
            request.user,
            note=serializer.validated_data["reason"],
            request=request,
        )
        return Response(ApprovalRequestSerializer(row, context=self.get_serializer_context()).data)


# ═══════════════════════════════════════════════════════════════════════════
# CONTENT MODERATION
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Admin"])
class ModerationViewSet(_AdminViewSet):
    serializer_class = ModerationFlagSerializer
    serializer_classes = {"resolve": FlagResolutionSerializer}
    queryset = ModerationFlag.objects.none()
    success_messages = {
        "claim": "Report claimed — it is now under review",
        "resolve": "Report resolved",
    }

    def _flag(self, pk) -> ModerationFlag:
        flag = selectors.get_flag(pk)
        if flag is None:
            raise NotFound("Report not found.")
        return flag

    @extend_schema(
        summary="The moderation queue",
        parameters=[
            OpenApiParameter(
                "status", str, description="OPEN | REVIEWING | ACTIONED | DISMISSED"
            ),
            OpenApiParameter(
                "content_type", str,
                description="REVIEW | MESSAGE | PRODUCT | PORTFOLIO_IMAGE | PROFILE",
            ),
        ],
        responses=ModerationFlagSerializer(many=True),
    )
    def list(self, request):
        return self._page(
            selectors.moderation_queue(
                status=request.query_params.get("status"),
                content_type=request.query_params.get("content_type"),
            ),
            ModerationFlagSerializer,
        )

    @extend_schema(summary="One report, with a preview of what was reported")
    def retrieve(self, request, pk=None):
        return Response(
            ModerationFlagSerializer(
                self._flag(pk), context=self.get_serializer_context()
            ).data
        )

    @extend_schema(summary="Claim a report so two admins do not both act", request=None)
    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        flag = services.start_review(self._flag(pk), request.user)
        return Response(
            ModerationFlagSerializer(flag, context=self.get_serializer_context()).data
        )

    @extend_schema(
        summary="Resolve — ACTIONED also takes the content down",
        request=FlagResolutionSerializer,
    )
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        flag = services.resolve_flag(
            self._flag(pk),
            request.user,
            action=serializer.validated_data["action"],
            note=serializer.validated_data.get("note", ""),
            request=request,
        )
        return Response(
            ModerationFlagSerializer(flag, context=self.get_serializer_context()).data
        )


# ═══════════════════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Admin"])
class AdminUserViewSet(_AdminViewSet):
    serializer_class = AdminUserSerializer
    serializer_classes = {
        "block": BlockUserSerializer,
        "unblock": UnblockUserSerializer,
        "adjust_wallet": WalletAdjustmentSerializer,
    }
    success_messages = {
        "block": "Account blocked, sessions revoked and open bookings cancelled",
        "unblock": "Account restored",
        "adjust_wallet": "Wallet adjusted and logged",
    }

    def get_queryset(self):
        from django.contrib.auth import get_user_model

        if getattr(self, "swagger_fake_view", False):
            return get_user_model().objects.none()
        return selectors.users()

    def _user(self, pk):
        user = selectors.get_user(pk)
        if user is None:
            raise NotFound("User not found.")
        return user

    @extend_schema(
        summary="The user table",
        parameters=[
            OpenApiParameter("role", str, description="BUYER | PHOTOGRAPHER | ADMIN"),
            OpenApiParameter("blocked", bool),
            OpenApiParameter("q", str, description="Email or name"),
        ],
        responses=AdminUserSerializer(many=True),
    )
    def list(self, request):
        blocked = request.query_params.get("blocked")
        return self._page(
            selectors.users(
                role=request.query_params.get("role"),
                blocked=(blocked in ("1", "true", "True"))
                if blocked is not None
                else None,
                term=(request.query_params.get("q") or "").strip(),
            ),
            AdminUserSerializer,
        )

    @extend_schema(
        summary="One user, with bookings / orders / reviews / balance",
        responses=AdminUserDetailSerializer,
    )
    def retrieve(self, request, pk=None):
        return Response(
            AdminUserDetailSerializer(
                self._user(pk), context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        summary="Block an account — revokes tokens, cancels open bookings",
        request=BlockUserSerializer,
    )
    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.block_user(
            self._user(pk),
            request.user,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(
            AdminUserDetailSerializer(user, context=self.get_serializer_context()).data
        )

    @extend_schema(summary="Restore a blocked account", request=UnblockUserSerializer)
    @action(detail=True, methods=["post"])
    def unblock(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.unblock_user(
            self._user(pk),
            request.user,
            reason=serializer.validated_data.get("reason", ""),
            request=request,
        )
        return Response(
            AdminUserDetailSerializer(user, context=self.get_serializer_context()).data
        )

    @extend_schema(
        summary="Credit or debit a wallet — always with a ledger row",
        request=WalletAdjustmentSerializer,
    )
    @action(detail=True, methods=["post"], url_path="adjust-wallet")
    def adjust_wallet(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        balance = services.adjust_wallet(
            self._user(pk),
            request.user,
            amount=serializer.validated_data["amount"],
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response({"balance": str(balance)})


# ═══════════════════════════════════════════════════════════════════════════
# TOP-UPS
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Admin"])
class AdminTopUpViewSet(_AdminViewSet):
    serializer_class = AdminTopUpSerializer
    serializer_classes = {
        "approve": TopUpDecisionSerializer,
        "reject": TopUpRejectionSerializer,
    }
    success_messages = {
        "approve": "Top-up approved and the wallet credited",
        "reject": "Top-up rejected and the reason sent",
    }

    def get_queryset(self):
        from apps.profiles.models import TopUpRequest

        if getattr(self, "swagger_fake_view", False):
            return TopUpRequest.objects.none()
        return selectors.topup_queue()

    def _topup(self, pk):
        topup = selectors.get_topup(pk)
        if topup is None:
            raise NotFound("Top-up request not found.")
        return topup

    @extend_schema(
        summary="Top-up requests awaiting verification",
        parameters=[
            OpenApiParameter("status", str, description="PENDING | APPROVED | REJECTED")
        ],
        responses=AdminTopUpSerializer(many=True),
    )
    def list(self, request):
        return self._page(
            selectors.topup_queue(
                status=request.query_params.get("status", "PENDING")
            ),
            AdminTopUpSerializer,
        )

    @extend_schema(summary="Approve — this is the only thing that credits a wallet")
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        topup = services.approve_topup(
            self._topup(pk),
            request.user,
            note=serializer.validated_data.get("note", ""),
            request=request,
        )
        return Response(
            AdminTopUpSerializer(topup, context=self.get_serializer_context()).data
        )

    @extend_schema(summary="Reject, with a reason")
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        topup = services.reject_topup(
            self._topup(pk),
            request.user,
            note=serializer.validated_data["note"],
            request=request,
        )
        return Response(
            AdminTopUpSerializer(topup, context=self.get_serializer_context()).data
        )


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Admin"])
class AdminProductViewSet(_AdminViewSet):
    serializer_class = AdminProductSerializer
    serializer_classes = {"remove": RejectionSerializer}
    success_messages = {
        "approve": "Product approved and listed",
        "remove": "Product pulled from the shop",
    }

    def get_queryset(self):
        from apps.marketplace.models import DigitalProduct

        if getattr(self, "swagger_fake_view", False):
            return DigitalProduct.objects.none()
        return selectors.product_queue()

    @extend_schema(
        summary="Published products still awaiting the copyright gate",
        parameters=[
            OpenApiParameter(
                "approved", bool, description="Show already-approved ones instead"
            )
        ],
        responses=AdminProductSerializer(many=True),
    )
    def list(self, request):
        approved = request.query_params.get("approved") in ("1", "true", "True")
        return self._page(
            selectors.product_queue(approved=approved), AdminProductSerializer
        )

    @extend_schema(summary="Clear a product for sale", request=None)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        product = services.approve_product(int(pk), request.user, request=request)
        return Response(
            AdminProductSerializer(product, context=self.get_serializer_context()).data
        )

    @extend_schema(
        summary="Pull a product — buyers keep what they already paid for",
        request=RejectionSerializer,
    )
    @action(detail=True, methods=["post"])
    def remove(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = services.unpublish_product(
            int(pk),
            request.user,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(
            AdminProductSerializer(product, context=self.get_serializer_context()).data
        )


# ═══════════════════════════════════════════════════════════════════════════
# BOOKINGS
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Admin"])
class AdminBookingViewSet(_AdminViewSet):
    serializer_class = ForceCancelSerializer
    success_messages = {"force_cancel": "Booking cancelled and both parties notified"}

    def get_queryset(self):
        from apps.bookings.models import Booking

        return Booking.objects.none()  # only the action below is exposed

    @extend_schema(
        summary="Force-cancel a booking through the state machine",
        request=ForceCancelSerializer,
    )
    @action(detail=True, methods=["post"], url_path="force-cancel")
    def force_cancel(self, request, pk=None):
        from apps.bookings.models import Booking

        booking = (
            Booking.objects.select_related("photographer", "photographer__user", "buyer")
            .filter(pk=pk)
            .first()
        )
        if booking is None:
            raise NotFound("Booking not found.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.force_cancel_booking(
            booking,
            request.user,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        booking.refresh_from_db()
        return Response({"id": booking.pk, "status": booking.status})


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Admin"])
class AuditLogViewSet(_AdminViewSet):
    """
    Read-only by construction.

    No create, update or destroy action exists on this viewset, and there is no
    service function that modifies an `AuditLog` row. That is the guarantee, not
    a `readonly_fields` list somebody can widen.
    """

    serializer_class = AuditLogSerializer

    def get_queryset(self):
        from apps.administration.models import AuditLog

        if getattr(self, "swagger_fake_view", False):
            return AuditLog.objects.none()
        return selectors.audit_log()

    @extend_schema(
        summary="Every privileged action, newest first",
        parameters=[
            OpenApiParameter("action", str),
            OpenApiParameter("actor", int),
            OpenApiParameter("target_type", str),
        ],
        responses=AuditLogSerializer(many=True),
    )
    def list(self, request):
        actor = request.query_params.get("actor")
        return self._page(
            selectors.audit_log(
                action=request.query_params.get("action"),
                actor_id=int(actor) if actor and actor.isdigit() else None,
                target_type=(request.query_params.get("target_type") or "").strip(),
            ),
            AuditLogSerializer,
        )


# ═══════════════════════════════════════════════════════════════════════════
# PLATFORM SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Admin"])
class PlatformSettingViewSet(_AdminViewSet):
    serializer_class = PlatformSettingSerializer
    serializer_classes = {"partial_update": SettingWriteSerializer}
    action_permissions = {"public": [AllowAny]}
    lookup_field = "key"
    lookup_value_regex = "[^/]+"
    pagination_class = None
    success_messages = {"partial_update": "Setting updated and logged"}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PlatformSetting.objects.none()
        return selectors.settings_list()

    @extend_schema(
        summary="All runtime-tunable settings",
        parameters=[OpenApiParameter("group", str)],
        responses=PlatformSettingSerializer(many=True),
    )
    def list(self, request):
        return Response(
            PlatformSettingSerializer(
                selectors.settings_list(group=request.query_params.get("group")),
                many=True,
            ).data
        )

    @extend_schema(
        summary="Change one setting — declared keys only",
        request=SettingWriteSerializer,
        responses=PlatformSettingSerializer,
    )
    def partial_update(self, request, key=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        setting = services.set_setting(
            key, serializer.validated_data["value"], request.user, request=request
        )
        return Response(PlatformSettingSerializer(setting).data)

    @extend_schema(
        summary="The subset the mobile app may read before login",
        responses={200: dict},
    )
    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def public(self, request):
        return Response(selectors.public_settings())


# ═══════════════════════════════════════════════════════════════════════════
# BROADCASTS
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Admin"])
class BroadcastViewSet(_AdminViewSet):
    serializer_class = BroadcastSerializer
    success_messages = {"create": "Announcement queued for delivery"}

    def get_queryset(self):
        from apps.notifications.models import Broadcast

        if getattr(self, "swagger_fake_view", False):
            return Broadcast.objects.none()
        return Broadcast.objects.select_related("created_by").order_by("-created_at")

    @extend_schema(summary="Past announcements", responses=BroadcastSerializer(many=True))
    def list(self, request):
        return self._page(self.get_queryset(), BroadcastSerializer)

    @extend_schema(
        summary="Send an announcement to a filtered audience",
        request=BroadcastSerializer,
        responses={201: BroadcastSerializer},
    )
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        broadcast = services.create_broadcast(
            request.user, request=request, **serializer.validated_data
        )
        return Response(
            BroadcastSerializer(broadcast, context=self.get_serializer_context()).data,
            status=201,
        )
