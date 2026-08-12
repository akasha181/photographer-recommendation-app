"""View mixins that remove repetitive boilerplate from ViewSets."""

from rest_framework.response import Response


class MessageResponseMixin:
    """
    Lets a ViewSet set a human-readable success message per action:

        success_messages = {"create": "Booking request sent to the photographer"}
    """

    success_messages: dict[str, str] = {}

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        message = self.success_messages.get(getattr(self, "action", ""))
        if message and response.status_code < 400:
            response.success_message = message
        return response


class MultiSerializerMixin:
    """
    Different shapes for different actions without a pile of if-statements.

        serializer_classes = {
            "list": BookingListSerializer,
            "retrieve": BookingDetailSerializer,
            "create": BookingCreateSerializer,
        }

    List endpoints should return a *lean* serializer — sending the full nested
    photographer profile for 20 list rows is the top cause of slow mobile
    screens.
    """

    serializer_classes: dict[str, type] = {}

    def get_serializer_class(self):
        return self.serializer_classes.get(
            getattr(self, "action", ""), self.serializer_class
        )


class ActionPermissionsMixin:
    """
    Per-action permission classes.

        action_permissions = {
            "create": [IsBuyer],
            "accept": [IsPhotographer],
            "list": [IsAuthenticated],
        }
    """

    action_permissions: dict[str, list] = {}

    def get_permissions(self):
        classes = self.action_permissions.get(getattr(self, "action", ""))
        if classes is not None:
            return [cls() for cls in classes]
        return super().get_permissions()


class SoftDeleteMixin:
    """DELETE performs a soft delete and returns 204."""

    def perform_destroy(self, instance):
        instance.delete()  # SoftDeleteModel.delete() flips the flag

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=204)
