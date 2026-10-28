"""Read-only API for reconciliation breaks."""

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ledger.api.problems import Problem, not_found
from apps.reconciliation.models import ReconBreak
from apps.reconciliation.serializers import BreakSerializer
from tallyproof_core.reconciliation import BreakType


class BreakPages(CursorPagination):
    """Breaks in the order they were found."""

    ordering = "leaf_index"
    page_size = 50
    page_size_query_param = "limit"
    max_page_size = 200


@extend_schema(
    parameters=[
        OpenApiParameter("break_type", str, enum=[t.value for t in BreakType]),
        OpenApiParameter("award_key", str),
    ]
)
class BreakListView(generics.ListAPIView[ReconBreak]):
    """Breaks, optionally filtered by type or award."""

    serializer_class = BreakSerializer
    pagination_class = BreakPages

    def get_queryset(self) -> QuerySet[ReconBreak]:
        """Apply the optional filters."""
        breaks = ReconBreak.objects.all()
        break_type = self.request.query_params.get("break_type")
        if break_type is not None:
            if break_type not in {t.value for t in BreakType}:
                raise Problem(400, "invalid-parameter", "Invalid parameter", "Unknown break_type.")
            breaks = breaks.filter(break_type=break_type)
        award_key = self.request.query_params.get("award_key")
        if award_key is not None:
            breaks = breaks.filter(award_key=award_key[:200])
        return breaks


class BreakDetailView(APIView):
    """One break."""

    @extend_schema(responses=BreakSerializer)
    def get(self, request: Request, break_id: str) -> Response:
        """Return the break and its events."""
        recon_break = ReconBreak.objects.filter(public_id=break_id[:64]).first()
        if recon_break is None:
            raise not_found(f"Break {break_id[:64]}")
        return Response(BreakSerializer(recon_break).data)
