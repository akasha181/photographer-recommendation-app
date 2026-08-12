"""
Marketplace endpoints — Module 8.

Browsing is public for the same reason photographer discovery is: making
someone sign up before they can see what is for sale loses them at the top of
the funnel. Everything that touches money or files requires authentication.

THE DOWNLOAD ENDPOINT IS THE ONLY WAY TO PRODUCT BYTES
------------------------------------------------------
`ProductFile.file` lives on private storage with no URL. `download` mints a
single-use token; `download_file` redeems it and streams. In production the
streaming is handed to Nginx via X-Accel-Redirect so Python is not tied up for
the length of a 500 MB transfer; in development Django serves it directly.
"""

import logging
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status as http
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet

from apps.core.mixins import MessageResponseMixin, MultiSerializerMixin
from apps.marketplace import selectors, services
from apps.marketplace.filters import ProductFilterSet
from apps.marketplace.models import CartItem, DigitalProduct, ProductFile
from apps.marketplace.serializers import (
    AddToCartSerializer,
    CartSerializer,
    CheckoutSerializer,
    DownloadRequestSerializer,
    DownloadTokenSerializer,
    OrderItemSerializer,
    OrderSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    SellerProductSerializer,
    SellerSummarySerializer,
)

logger = logging.getLogger("snapsphere")


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Marketplace"])
class ProductViewSet(MessageResponseMixin, MultiSerializerMixin, ReadOnlyModelViewSet):
    """Browse and search digital products."""

    permission_classes = [AllowAny]
    serializer_class = ProductListSerializer
    serializer_classes = {"retrieve": ProductDetailSerializer}
    filter_backends = [DjangoFilterBackend]
    filterset_class = ProductFilterSet
    lookup_field = "slug"
    throttle_scope = "search"
    success_messages = {
        "list": "Products retrieved",
        "retrieve": "Product retrieved",
        "featured": "Featured products retrieved",
        "bestsellers": "Best sellers retrieved",
        "filters": "Filter options retrieved",
    }

    def get_queryset(self):
        return selectors.products_for_list().order_by("-is_featured", "-sales_count")

    def get_serializer_context(self):
        """
        Load ownership, wishlist and cart membership once per request.

        Three queries for the whole page instead of three per card. For an
        anonymous caller they cost nothing at all.
        """
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            from apps.wishlist.models import WishlistItem

            from apps.marketplace.models import CartItem

            context["owned_ids"] = selectors.owned_product_ids(user)
            context["wishlisted_ids"] = set(
                WishlistItem.objects.filter(
                    user=user, product__isnull=False
                ).values_list("product_id", flat=True)
            )
            context["cart_ids"] = set(
                CartItem.objects.filter(user=user).values_list("product_id", flat=True)
            )
        return context

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Search title, description, tags"),
            OpenApiParameter("product_type", str),
            OpenApiParameter("category", str, description="Category slug"),
            OpenApiParameter("license_type", str),
            OpenApiParameter("min_price", float),
            OpenApiParameter("max_price", float),
            OpenApiParameter("on_sale", bool),
            OpenApiParameter(
                "affordable", bool,
                description="Only products the caller's wallet can already cover",
            ),
            OpenApiParameter(
                "ordering", str,
                description="price | popularity | rating | newest | views "
                            "(prefix with '-' to reverse)",
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Resolved here rather than in the FilterSet because this is the only
        # layer that knows who is asking and what their balance is.
        if request.query_params.get("affordable") in ("true", "True", "1"):
            if request.user.is_authenticated:
                queryset = queryset.filter(
                    price__lte=selectors.wallet_balance(request.user)
                )

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        product = selectors.product_detail(kwargs["slug"])
        if product is None:
            raise NotFound("This product is not available.")

        # Fire-and-forget view counter. F() avoids a read-modify-write race
        # when several buyers open the same product at once.
        from django.db.models import F

        DigitalProduct.objects.filter(pk=product.pk).update(
            view_count=F("view_count") + 1
        )
        return Response(self.get_serializer(product).data)

    @extend_schema(summary="Editorially featured products")
    @action(detail=False, methods=["get"], pagination_class=None)
    def featured(self, request):
        rows = selectors.featured_products(limit=10)
        return Response(self.get_serializer(rows, many=True).data)

    @extend_schema(summary="Best selling products")
    @action(detail=False, methods=["get"], pagination_class=None)
    def bestsellers(self, request):
        rows = selectors.bestsellers(limit=10)
        return Response(self.get_serializer(rows, many=True).data)

    @extend_schema(summary="Filter values available to the shop UI")
    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def filters(self, request):
        return Response(selectors.filter_options())


# ═══════════════════════════════════════════════════════════════════════════
# CART
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Marketplace"])
class CartViewSet(MessageResponseMixin, MultiSerializerMixin, GenericViewSet):
    """The server-side basket — it survives reinstalling the app."""

    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer
    serializer_classes = {"add": AddToCartSerializer}
    pagination_class = None
    # Never queried — declared only so drf-spectacular can infer the model
    # without calling get_queryset() with an AnonymousUser.
    queryset = CartItem.objects.none()
    success_messages = {
        "list": "Cart retrieved",
        "add": "Added to cart",
        "remove": "Removed from cart",
        "clear": "Cart cleared",
    }

    def _cart_response(self, request, status_code=http.HTTP_200_OK) -> Response:
        summary = selectors.cart_summary(request.user)
        return Response(
            CartSerializer(summary, context=self.get_serializer_context()).data,
            status=status_code,
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            context["owned_ids"] = selectors.owned_product_ids(user)
            context["cart_ids"] = set(
                selectors.get_cart(user).values_list("product_id", flat=True)
            )
        return context

    @extend_schema(summary="What is in the basket", responses=CartSerializer)
    def list(self, request):
        return self._cart_response(request)

    @extend_schema(summary="Add a product", request=AddToCartSerializer)
    @action(detail=False, methods=["post"])
    def add(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.add_to_cart(request.user, serializer.validated_data["product"])
        return self._cart_response(request, http.HTTP_201_CREATED)

    @extend_schema(summary="Remove one product")
    @action(detail=False, methods=["post"], url_path=r"remove/(?P<product_id>\d+)")
    def remove(self, request, product_id=None):
        services.remove_from_cart(request.user, int(product_id))
        return self._cart_response(request)

    @extend_schema(summary="Empty the basket")
    @action(detail=False, methods=["post"])
    def clear(self, request):
        services.clear_cart(request.user)
        return self._cart_response(request)


# ═══════════════════════════════════════════════════════════════════════════
# ORDERS, CHECKOUT AND DOWNLOADS
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Marketplace"])
class OrderViewSet(MessageResponseMixin, MultiSerializerMixin, GenericViewSet):
    """Checkout, receipts and the buyer's download library."""

    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    serializer_classes = {
        "checkout": CheckoutSerializer,
        "purchases": OrderItemSerializer,
        "download": DownloadRequestSerializer,
    }
    success_messages = {
        "list": "Orders retrieved",
        "retrieve": "Order retrieved",
        "checkout": "Purchase complete — your downloads are ready",
        "purchases": "Purchases retrieved",
        "download": "Download link ready",
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            from apps.marketplace.models import Order

            return Order.objects.none()
        return selectors.get_orders(self.request.user)

    def get_throttles(self):
        self.throttle_scope = "booking_create" if self.action == "checkout" else None
        return super().get_throttles()

    @extend_schema(summary="Past orders")
    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(
            OrderSerializer(page, many=True, context=self.get_serializer_context()).data
        )

    @extend_schema(summary="One receipt")
    def retrieve(self, request, pk=None):
        order = selectors.get_order(request.user, pk)
        if order is None:
            raise NotFound("Order not found.")
        return Response(
            OrderSerializer(order, context=self.get_serializer_context()).data
        )

    @extend_schema(
        summary="Buy everything in the cart with the wallet",
        description=(
            "Send an `Idempotency-Key` header — any unique string per attempt. "
            "A retry carrying the same key returns the order the first call "
            "created instead of charging twice."
        ),
        request=CheckoutSerializer,
        responses={201: OrderSerializer},
    )
    @action(detail=False, methods=["post"])
    def checkout(self, request):
        key = (request.headers.get("Idempotency-Key") or "").strip()[:64]
        order = services.checkout(request.user, idempotency_key=key)
        return Response(
            OrderSerializer(order, context=self.get_serializer_context()).data,
            status=http.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Everything the buyer owns, ready to download",
        responses=OrderItemSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def purchases(self, request):
        page = self.paginate_queryset(selectors.get_purchases(request.user))
        return self.get_paginated_response(
            OrderItemSerializer(
                page, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        summary="Mint a single-use download link",
        request=DownloadRequestSerializer,
        responses=DownloadTokenSerializer,
    )
    @action(detail=False, methods=["post"], url_path=r"items/(?P<item_id>\d+)/download")
    def download(self, request, item_id=None):
        purchase = selectors.get_purchase(request.user, int(item_id))
        if purchase is None:
            raise NotFound("Purchase not found.")

        files = list(purchase.product.files.all())
        if not files:
            raise NotFound("This product has no downloadable files yet.")

        requested = request.data.get("file")
        product_file = files[0]
        if requested:
            product_file = next((f for f in files if f.pk == int(requested)), None)
            if product_file is None:
                raise ValidationError({"file": "That file is not part of this product."})

        token = services.issue_download_token(request.user, purchase, product_file)
        purchase.refresh_from_db()

        return Response(
            {
                "download_url": request.build_absolute_uri(
                    f"/api/v1/marketplace/download/{token.token}/"
                ),
                "expires_at": token.expires_at,
                "file_name": product_file.name,
                "downloads_remaining": purchase.downloads_remaining,
            }
        )


@extend_schema(
    tags=["Marketplace"],
    summary="Redeem a download token and stream the file",
    responses={200: None},
)
@api_view(["GET"])
@permission_classes([AllowAny])
def download_file(request, token: str):
    """
    Unauthenticated on purpose — the token IS the credential.

    A download often continues in the platform's download manager rather than
    in the app's HTTP client, where the Authorization header is not available.
    Requiring both would break the thing this endpoint exists to do; the token
    is single-use, expires in 15 minutes and is bound to one order item, which
    is a tighter grant than the session it replaces.
    """
    granted = services.redeem_download_token(
        token, ip_address=request.META.get("REMOTE_ADDR")
    )
    product_file = granted.product_file

    # Behind Nginx, hand the bytes off: Django answers in milliseconds instead
    # of holding a worker for the length of a 500 MB transfer. Gated on an
    # explicit setting rather than `not DEBUG`, because a deployment without a
    # reverse proxy would otherwise return an empty body plus a header nothing
    # acts on — and that failure is invisible until a real buyer downloads.
    if settings.PRIVATE_MEDIA_X_ACCEL:
        response = HttpResponse()
        response["Content-Type"] = ""
        response["X-Accel-Redirect"] = (
            f"{settings.PRIVATE_MEDIA_X_ACCEL_PREFIX}{product_file.file.name}"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{product_file.name}"'
        )
        return response

    path = Path(settings.PRIVATE_MEDIA_ROOT) / product_file.file.name
    if not path.exists():
        raise NotFound("The file is missing from storage.")
    return FileResponse(open(path, "rb"), as_attachment=True, filename=product_file.name)


# ═══════════════════════════════════════════════════════════════════════════
# SELLER VIEW (read-only)
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Marketplace"])
class SellerProductViewSet(MessageResponseMixin, GenericViewSet):
    """
    A photographer's own catalogue and sales.

    Read-only for now: uploading products needs private-file handling and an
    admin moderation gate, which is scoped separately. Sellers can still see
    what is live and what it earned.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SellerProductSerializer
    pagination_class = None
    queryset = DigitalProduct.objects.none()  # schema inference only
    success_messages = {
        "list": "Your products retrieved",
        "summary": "Sales summary retrieved",
    }

    def _profile(self):
        profile = getattr(self.request.user, "photographer_profile", None)
        if profile is None:
            raise NotFound("Only photographer accounts have a product catalogue.")
        return profile

    @extend_schema(summary="Products this photographer sells, including drafts")
    def list(self, request):
        rows = selectors.products_by_seller(self._profile())
        return Response(
            SellerProductSerializer(
                rows, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(summary="Sales and earnings totals", responses=SellerSummarySerializer)
    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response(
            SellerSummarySerializer(
                selectors.seller_sales_summary(self._profile())
            ).data
        )
