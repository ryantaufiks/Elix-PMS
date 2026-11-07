from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """DRF's handler, plus a readable 409 when a delete is blocked by related records."""
    if isinstance(exc, ProtectedError):
        names = sorted({str(obj._meta.verbose_name_plural) for obj in exc.protected_objects})
        return Response({"detail": f"Still in use by {', '.join(names)}. Remove or move those first."},
                        status=status.HTTP_409_CONFLICT)
    return drf_exception_handler(exc, context)
