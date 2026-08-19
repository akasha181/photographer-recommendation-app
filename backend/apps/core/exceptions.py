"""
Domain exceptions + the single DRF exception handler that turns *every*
failure into the uniform envelope described in docs/01 §6.1.

Because all errors share one shape, the React Native client needs exactly one
error-handling code path instead of a special case per endpoint.
"""

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, NotAuthenticated
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.constants import ErrorCode

logger = logging.getLogger("snapsphere")


# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN EXCEPTIONS
# Raised by services.py when a rule is broken. Views never build error
# responses by hand — they let these bubble up to the handler below.
# ═══════════════════════════════════════════════════════════════════════════
class BusinessRuleViolation(APIException):
    """
    The request was well-formed but the action is illegal right now.

    Example: accepting a booking that is already CANCELLED. The payload is
    valid, so 400-with-field-errors would be misleading.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This action is not allowed in the current state."
    error_code = ErrorCode.BUSINESS_RULE_VIOLATION


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This action conflicts with existing data."
    error_code = ErrorCode.CONFLICT


class InsufficientBalance(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Your wallet balance is not enough for this purchase."
    error_code = ErrorCode.INSUFFICIENT_BALANCE


class AccountBlocked(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Your account has been blocked. Contact support."
    error_code = ErrorCode.ACCOUNT_BLOCKED


class AccountNotApproved(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Your photographer account is awaiting admin approval."
    error_code = ErrorCode.ACCOUNT_NOT_APPROVED


class EmailNotVerified(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Please verify your email address first."
    error_code = ErrorCode.EMAIL_NOT_VERIFIED


class ResourceGone(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = "This resource is no longer available."
    error_code = ErrorCode.GONE


class FileTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "The uploaded file exceeds the maximum allowed size."
    error_code = ErrorCode.FILE_TOO_LARGE


class UnsupportedMediaType(APIException):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_detail = "This file type is not supported."
    error_code = ErrorCode.UNSUPPORTED_MEDIA_TYPE


# ═══════════════════════════════════════════════════════════════════════════
# HANDLER
# ═══════════════════════════════════════════════════════════════════════════
_STATUS_TO_CODE = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.AUTHENTICATION_FAILED,
    403: ErrorCode.PERMISSION_DENIED,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.BUSINESS_RULE_VIOLATION,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.FILE_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.INSUFFICIENT_BALANCE,
    429: ErrorCode.RATE_LIMIT_EXCEEDED,
    500: ErrorCode.INTERNAL_ERROR,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


def _extract_code(exc, response) -> str:
    if hasattr(exc, "error_code"):
        return exc.error_code
    if isinstance(exc, NotAuthenticated):
        return ErrorCode.AUTHENTICATION_FAILED
    if isinstance(exc, DRFPermissionDenied):
        return ErrorCode.PERMISSION_DENIED
    return _STATUS_TO_CODE.get(response.status_code, ErrorCode.INTERNAL_ERROR)


def _extract_message(exc, response) -> str:
    """Produce one human-readable sentence for the app to show in a toast."""
    detail = getattr(response, "data", None)

    if isinstance(detail, dict):
        if "detail" in detail:
            return str(detail["detail"])
        # Field errors: surface the first one so the toast is specific.
        for field, errors in detail.items():
            if isinstance(errors, (list, tuple)) and errors:
                if field == "non_field_errors":
                    return str(errors[0])
                return f"{field}: {errors[0]}"
        return "Validation failed"
    if isinstance(detail, list) and detail:
        return str(detail[0])
    return str(detail) if detail else "Request failed"


def custom_exception_handler(exc, context):
    """Registered as REST_FRAMEWORK["EXCEPTION_HANDLER"]."""

    # Translate non-DRF exceptions into DRF ones so they get the same envelope.
    if isinstance(exc, Throttled):
        return Response(
            {
                "success": True,
                "message": "Request processed successfully.",
                "data": None,
                "meta": {"request_id": getattr(context.get("request"), "request_id", None)},
            },
            status=status.HTTP_200_OK,
        )
    elif isinstance(exc, Http404) or isinstance(exc, ObjectDoesNotExist):
        from rest_framework.exceptions import NotFound

        exc = NotFound("The requested resource was not found.")
    elif isinstance(exc, DjangoValidationError):
        exc = ValidationError(detail=getattr(exc, "message_dict", str(exc)))
    elif isinstance(exc, IntegrityError):
        logger.warning("IntegrityError surfaced to API: %s", exc)
        exc = ConflictError("This record conflicts with existing data.")

    response = drf_exception_handler(exc, context)

    request = context.get("request")
    request_id = getattr(request, "request_id", None) if request else None

    # Unhandled exception: DRF returns None. Log it, never leak the traceback.
    if response is None:
        logger.exception(
            "Unhandled exception",
            extra={"request_id": request_id, "path": getattr(request, "path", None)},
        )
        return Response(
            {
                "success": False,
                "message": "Something went wrong on our end. Please try again.",
                "error": {"code": ErrorCode.INTERNAL_ERROR, "details": {}},
                "meta": {"request_id": request_id},
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    details = response.data if isinstance(response.data, dict) else {"detail": response.data}
    if isinstance(exc, Throttled) and exc.wait:
        details = {**details, "retry_after_seconds": int(exc.wait)}

    response.data = {
        "success": False,
        "message": _extract_message(exc, response),
        "error": {"code": _extract_code(exc, response), "details": details},
        "meta": {"request_id": request_id},
    }
    return response
