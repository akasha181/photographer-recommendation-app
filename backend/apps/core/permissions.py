"""
Reusable permission classes.

Authorisation happens in three escalating checks:

  1. ROLE      — is this user even the right kind of account?  (IsBuyer, ...)
  2. OWNERSHIP — does this specific object belong to them?      (IsOwner, ...)
  3. STATE     — is the object in a state that allows this?     (services.py)

Checks 1 and 2 live here. Check 3 belongs to the service layer, because it is
business logic, not access control.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.constants import UserRole


class _RolePermission(BasePermission):
    role: str = ""
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == self.role)


class IsBuyer(_RolePermission):
    role = UserRole.BUYER
    message = "Only buyers can perform this action."


class IsPhotographer(_RolePermission):
    role = UserRole.PHOTOGRAPHER
    message = "Only photographers can perform this action."


class IsAdmin(_RolePermission):
    role = UserRole.ADMIN
    message = "Administrator access required."


class IsApprovedPhotographer(BasePermission):
    """
    A photographer who has registered but not yet been approved may edit their
    own profile and portfolio, but must not appear in search or receive
    bookings. Endpoints that expose them publicly use this class.
    """

    message = "Your photographer account is awaiting admin approval."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == UserRole.PHOTOGRAPHER
            and getattr(user, "photographer_profile", None)
            and user.photographer_profile.is_approved
        )


class IsOwner(BasePermission):
    """
    Object-level ownership.

    Prevents the single most common API vulnerability: authenticated user A
    fetching /bookings/999/ which belongs to user B. Every detail view that
    returns user-scoped data must include this.
    """

    message = "You do not own this resource."
    owner_field = "user"

    def has_object_permission(self, request, view, obj):
        owner_field = getattr(view, "owner_field", self.owner_field)
        owner = obj
        for part in owner_field.split("."):
            owner = getattr(owner, part, None)
            if owner is None:
                return False
        return owner == request.user


class IsOwnerOrReadOnly(IsOwner):
    """Anyone may read; only the owner may write."""

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return super().has_object_permission(request, view, obj)


class IsAdminOrReadOnly(BasePermission):
    """Public catalogue data: everyone reads, only admins change it."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        return bool(user and user.is_authenticated and user.role == UserRole.ADMIN)


class IsBookingParticipant(BasePermission):
    """Either side of a booking may view it; nobody else may."""

    message = "You are not a participant in this booking."

    def has_object_permission(self, request, view, obj):
        user = request.user
        return obj.buyer_id == user.id or obj.photographer.user_id == user.id


class IsConversationParticipant(BasePermission):
    message = "You are not a participant in this conversation."

    def has_object_permission(self, request, view, obj):
        return obj.participants.filter(pk=request.user.pk).exists()


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
