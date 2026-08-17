"""
Chat routes — mounted at /api/v1/chat/

Two viewsets: threads under `conversations/`, single-message operations under
`messages/`. A message is addressed on its own rather than nested under its
thread because the app edits, deletes and reports from a long-press menu that
holds a message id and nothing else.
"""

from rest_framework.routers import DefaultRouter

from apps.chat.views import ConversationViewSet, MessageViewSet

app_name = "chat"

router = DefaultRouter()
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("messages", MessageViewSet, basename="message")

urlpatterns = router.urls
