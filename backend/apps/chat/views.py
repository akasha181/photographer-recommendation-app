"""
Chat endpoints — Module 13.

    GET    /chat/conversations/                     the Messages tab
    POST   /chat/conversations/                     open or find a thread
    GET    /chat/conversations/{id}/                one thread's header
    GET    /chat/conversations/{id}/messages/       ?after= | ?before= | ?limit=
    POST   /chat/conversations/{id}/messages/       send  (client_id = idempotent)
    POST   /chat/conversations/{id}/read/           move the read watermark
    POST   /chat/conversations/{id}/mute/           toggle
    POST   /chat/conversations/{id}/block/          toggle, silent to the blocked
    POST   /chat/conversations/{id}/archive/        toggle
    POST   /chat/conversations/{id}/leave/          stop participating
    GET    /chat/conversations/unread-count/        Messages tab badge
    GET    /chat/conversations/contacts/            who you may message
    PATCH  /chat/messages/{id}/                     edit your own
    DELETE /chat/messages/{id}/                     withdraw your own
    POST   /chat/messages/{id}/report/              into the moderation queue

WHY REST EXISTS ALONGSIDE THE WEBSOCKET
--------------------------------------
The socket is for the seconds a thread is open. Everything else — the list, the
history, the badge after a cold start, the send that has to survive a network
switch — is HTTP. Building only the socket is how a chat app loses messages the
moment a phone changes network; building only REST is how it feels dead.

Both write through `services.send_message`, so there is exactly one definition
of what sending a message does.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, Throttled
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.chat import selectors, services
from apps.chat.models import Conversation, Message
from apps.chat.serializers import (
    ContactSerializer,
    ConversationDetailSerializer,
    ConversationSerializer,
    ConversationStartSerializer,
    ConversationReadSerializer,
    MessageEditSerializer,
    MessageSendSerializer,
    MessageSerializer,
    ReportMessageSerializer,
)
from apps.core.mixins import MessageResponseMixin, MultiSerializerMixin


@extend_schema(tags=["Chat"])
class ConversationViewSet(
    MessageResponseMixin, MultiSerializerMixin, GenericViewSet
):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer
    serializer_classes = {
        "create": ConversationStartSerializer,
        "messages": MessageSendSerializer,
        "read": ConversationReadSerializer,
    }
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    queryset = Conversation.objects.none()  # schema inference only
    success_messages = {
        "create": "Conversation ready",
        "messages": "Message sent",
        "read": "Marked as read",
        "leave": "You have left this conversation",
    }

    def _conversation(self, pk) -> Conversation:
        conversation = selectors.get_conversation(self.request.user, pk)
        if conversation is None:
            # 404, not 403: telling a stranger that conversation 51 exists is
            # itself a leak.
            raise NotFound("Conversation not found.")
        return conversation

    def _context_with_presence(self, conversations):
        """
        One Redis round trip for every "online" dot on the screen.

        `get_many` over the whole page instead of a `cache.get` per row — the
        list screen would otherwise make one call per thread.
        """
        context = self.get_serializer_context()
        user_ids = []
        for conversation in conversations:
            for link in conversation.participant_links.all():
                if link.user_id != self.request.user.id:
                    user_ids.append(link.user_id)
        context["presence"] = selectors.presence_for(user_ids)
        return context

    # ─── The Messages tab ────────────────────────────────────────────────────
    @extend_schema(
        summary="Your conversations, most recent first",
        parameters=[
            OpenApiParameter("archived", bool, description="Archived threads instead"),
            OpenApiParameter("unread", bool, description="Only threads with unread"),
        ],
        responses=ConversationSerializer(many=True),
    )
    def list(self, request):
        queryset = selectors.conversations_for(
            request.user,
            archived=request.query_params.get("archived") in ("1", "true", "True"),
            unread_only=request.query_params.get("unread") in ("1", "true", "True"),
        )
        page = self.paginate_queryset(queryset)
        rows = list(page if page is not None else queryset)
        data = ConversationSerializer(
            rows, many=True, context=self._context_with_presence(rows)
        ).data
        if page is not None:
            response = self.get_paginated_response(data)
            response.data["meta"]["unread_total"] = services.unread_total(request.user)
            return response
        return Response(data)

    @extend_schema(summary="One conversation", responses=ConversationDetailSerializer)
    def retrieve(self, request, pk=None):
        conversation = self._conversation(pk)
        return Response(
            ConversationDetailSerializer(
                conversation, context=self._context_with_presence([conversation])
            ).data
        )

    @extend_schema(
        summary="Open a conversation, or find the existing one",
        request=ConversationStartSerializer,
        responses={201: ConversationDetailSerializer},
    )
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        conversation, created = services.get_or_create_conversation(
            request.user, data["user"], booking=data.get("booking")
        )
        first_message = (data.get("message") or "").strip()
        if first_message:
            if services.rate_limited(request.user):
                raise Throttled(detail="You're sending messages too quickly.")
            services.send_message(conversation, request.user, body=first_message)

        conversation = self._conversation(conversation.pk)
        return Response(
            ConversationDetailSerializer(
                conversation, context=self._context_with_presence([conversation])
            ).data,
            # 200 when the thread already existed: the app tapped "Message" and
            # got the thread it asked for, which is not a creation.
            status=http.HTTP_201_CREATED if created else http.HTTP_200_OK,
        )

    # ─── Messages ────────────────────────────────────────────────────────────
    @extend_schema(
        summary="Messages in a thread, or send one",
        parameters=[
            OpenApiParameter("after", int, description="Only newer than this id"),
            OpenApiParameter("before", int, description="Scroll-back from this id"),
            OpenApiParameter("limit", int, description="Up to 100, default 50"),
        ],
        request=MessageSendSerializer,
        responses=MessageSerializer(many=True),
    )
    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        conversation = self._conversation(pk)

        if request.method == "GET":
            after = request.query_params.get("after")
            before = request.query_params.get("before")
            rows = selectors.messages_in(
                conversation,
                after=int(after) if after and after.isdigit() else None,
                before=int(before) if before and before.isdigit() else None,
                limit=int(request.query_params.get("limit") or 50),
            )
            return Response(
                MessageSerializer(
                    rows, many=True, context=self.get_serializer_context()
                ).data
            )

        if services.rate_limited(request.user):
            raise Throttled(detail="You're sending messages too quickly.")

        serializer = MessageSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = services.send_message(
            conversation, request.user, **serializer.validated_data
        )
        return Response(
            MessageSerializer(message, context=self.get_serializer_context()).data,
            status=http.HTTP_201_CREATED,
        )

    @extend_schema(summary="Move your read watermark", request=ConversationReadSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = self._conversation(pk)
        services.mark_read(
            conversation, request.user, up_to=serializer.validated_data.get("up_to")
        )
        return Response({"unread_count": 0})

    # ─── Per-thread settings ─────────────────────────────────────────────────
    @extend_schema(summary="Mute or unmute this thread", request=None)
    @action(detail=True, methods=["post"])
    def mute(self, request, pk=None):
        conversation = self._conversation(pk)
        link = selectors.participant_link(conversation, request.user)
        updated = services.set_muted(
            conversation, request.user, muted=not link.is_muted
        )
        return Response({"is_muted": updated.is_muted})

    @extend_schema(summary="Block or unblock the other participant", request=None)
    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):
        conversation = self._conversation(pk)
        link = selectors.participant_link(conversation, request.user)
        updated = services.set_blocked(
            conversation, request.user, blocked=not link.is_blocked
        )
        return Response({"is_blocked": updated.is_blocked})

    @extend_schema(summary="Archive or unarchive this thread", request=None)
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        conversation = self._conversation(pk)
        updated = services.set_archived(
            conversation, request.user, archived=not conversation.is_archived
        )
        return Response({"is_archived": updated.is_archived})

    @extend_schema(summary="Leave this conversation", request=None)
    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        services.leave_conversation(self._conversation(pk), request.user)
        return Response({"left": True})

    # ─── Tab badge & contacts ────────────────────────────────────────────────
    @extend_schema(summary="Total unread messages across all threads")
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"unread_total": services.unread_total(request.user)})

    @extend_schema(
        summary="Who you may start a conversation with",
        parameters=[OpenApiParameter("q", str, description="Name search")],
        responses=ContactSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def contacts(self, request):
        rows = selectors.searchable_contacts(
            request.user, (request.query_params.get("q") or "").strip()
        )
        return Response(
            ContactSerializer(
                rows, many=True, context=self.get_serializer_context()
            ).data
        )


@extend_schema(tags=["Chat"])
class MessageViewSet(MessageResponseMixin, MultiSerializerMixin, GenericViewSet):
    """Operations on a single message, addressed without its thread."""

    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer
    serializer_classes = {
        "partial_update": MessageEditSerializer,
        "report": ReportMessageSerializer,
    }
    queryset = Message.objects.none()  # schema inference only
    success_messages = {
        "partial_update": "Message edited",
        "destroy": "Message deleted",
        "report": "Reported — our team will take a look",
    }

    def _message(self, pk) -> Message:
        message = selectors.get_message(self.request.user, pk)
        if message is None:
            raise NotFound("Message not found.")
        return message

    @extend_schema(summary="Edit your own message", request=MessageEditSerializer)
    def partial_update(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = services.edit_message(
            self._message(pk), request.user, serializer.validated_data["body"]
        )
        return Response(
            MessageSerializer(message, context=self.get_serializer_context()).data
        )

    @extend_schema(summary="Withdraw your own message", responses={200: None})
    def destroy(self, request, pk=None):
        services.delete_message(self._message(pk), request.user)
        return Response(
            {"message": "Message deleted", "data": {"deleted": True}},
            status=http.HTTP_200_OK,
        )

    @extend_schema(summary="Report a message", request=ReportMessageSerializer)
    @action(detail=True, methods=["post"])
    def report(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        flag = services.report_message(
            self._message(pk),
            request.user,
            reason=serializer.validated_data["reason"],
            detail=serializer.validated_data.get("detail", ""),
        )
        return Response({"flag_id": flag.pk, "status": flag.status})
