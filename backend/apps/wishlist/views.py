"""Wishlist endpoints — the Saved screen and the heart icon."""

from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.mixins import MessageResponseMixin, MultiSerializerMixin
from apps.wishlist import selectors, services
from apps.wishlist.models import WishlistItem
from apps.wishlist.serializers import (
    SavedPhotographerSerializer,
    SavedProductSerializer,
    ToggleResultSerializer,
    ToggleSerializer,
    WishlistSerializer,
)


@extend_schema(tags=["Wishlist"])
class WishlistViewSet(MessageResponseMixin, MultiSerializerMixin, GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WishlistSerializer
    serializer_classes = {"toggle": ToggleSerializer}
    pagination_class = None
    queryset = WishlistItem.objects.none()  # schema inference only
    success_messages = {
        "list": "Wishlist retrieved",
        "photographers": "Saved photographers retrieved",
        "products": "Saved products retrieved",
        "toggle": "Wishlist updated",
        "destroy": "Removed from wishlist",
        "clear": "Wishlist cleared",
    }

    def get_serializer_context(self):
        """
        Everything on a saved card is already saved, so the flags are known
        without asking the database again.
        """
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            context["wishlisted_ids"] = selectors.wishlisted_photographer_ids(user)
            from apps.marketplace.selectors import owned_product_ids

            context["owned_ids"] = owned_product_ids(user)
        return context

    @extend_schema(summary="Everything saved, split by type", responses=WishlistSerializer)
    def list(self, request):
        user = request.user
        payload = {
            "photographers": list(selectors.saved_photographers(user)),
            "products": list(selectors.saved_products(user)),
            "counts": selectors.wishlist_counts(user),
        }
        return Response(
            WishlistSerializer(payload, context=self.get_serializer_context()).data
        )

    @extend_schema(summary="Saved photographers only")
    @action(detail=False, methods=["get"])
    def photographers(self, request):
        rows = selectors.saved_photographers(request.user)
        return Response(
            SavedPhotographerSerializer(
                rows, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(summary="Saved products only")
    @action(detail=False, methods=["get"])
    def products(self, request):
        rows = selectors.saved_products(request.user)
        return Response(
            SavedProductSerializer(
                rows, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        summary="Save or unsave — one endpoint for the heart icon",
        request=ToggleSerializer,
        responses=ToggleResultSerializer,
    )
    @action(detail=False, methods=["post"])
    def toggle(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get("photographer") is not None:
            from apps.profiles.selectors import visible_photographers

            target = visible_photographers().filter(pk=data["photographer"]).first()
            if target is None:
                raise NotFound("This photographer is not available.")
            is_saved = services.toggle_photographer(request.user, target)
        else:
            from apps.marketplace.selectors import purchasable_products

            target = purchasable_products().filter(pk=data["product"]).first()
            if target is None:
                raise NotFound("This product is not available.")
            is_saved = services.toggle_product(request.user, target)

        return Response(
            {
                "is_saved": is_saved,
                "counts": selectors.wishlist_counts(request.user),
            }
        )

    @extend_schema(summary="Remove one saved row by its wishlist id")
    def destroy(self, request, pk=None):
        services.remove_item(request.user, int(pk))
        return Response(status=204)

    @extend_schema(summary="Empty the wishlist")
    @action(detail=False, methods=["post"])
    def clear(self, request):
        services.clear(request.user)
        return Response({"counts": selectors.wishlist_counts(request.user)})
