"""Ledger API views. They return proofs and signed data, never verdicts."""

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ledger.api import proofs
from apps.ledger.api.problems import Problem, not_found
from apps.ledger.api.serializers import (
    CheckpointSerializer,
    ConsistencyProofSerializer,
    EventSerializer,
    InclusionProofSerializer,
    LogKeySerializer,
    TotalProofSerializer,
    TotalsSerializer,
)
from apps.ledger.models import LedgerBatch, LedgerEvent, LedgerTotals
from config.env import app_settings
from tallyproof_core.events import EventType
from tallyproof_core.sum_tree import proof_to_json, verify_total
from tallyproof_core.totals import OBLIGATIONS, OUTLAYS, prefix


class _Pages(CursorPagination):
    page_size = 50
    page_size_query_param = "limit"
    max_page_size = 200


class EventPages(_Pages):
    """Events in log order."""

    ordering = "leaf_index"


class CheckpointPages(_Pages):
    """Checkpoints, newest first."""

    ordering = "-tree_size"


def _bad_request(detail: str) -> Problem:
    return Problem(status.HTTP_400_BAD_REQUEST, "invalid-parameter", "Invalid parameter", detail)


def _int_param(request: Request, name: str) -> int | None:
    raw = request.query_params.get(name)
    if raw is None:
        return None
    if not raw.isdigit() or len(raw) > 16:
        raise _bad_request(f"{name} must be a non-negative integer.")
    return int(raw)


def _checkpoint(tree_size: int) -> LedgerBatch:
    batch = LedgerBatch.objects.filter(tree_size=tree_size).first()
    if batch is None:
        raise not_found(f"A signed checkpoint of size {tree_size}")
    return batch


def _latest_checkpoint() -> LedgerBatch:
    batch = LedgerBatch.objects.order_by("-tree_size").first()
    if batch is None:
        raise not_found("A signed checkpoint")
    return batch


class LogKeyView(APIView):
    """The public key every checkpoint is signed with."""

    @extend_schema(responses=LogKeySerializer)
    def get(self, request: Request) -> Response:
        """Return the log origin and verifier key."""
        env = app_settings()
        return Response(
            {"origin": env.merkle_log_origin, "verifier_key": env.checkpoint_public_key}
        )


class CheckpointListView(generics.ListAPIView[LedgerBatch]):
    """Signed checkpoints, newest first."""

    serializer_class = CheckpointSerializer
    pagination_class = CheckpointPages
    queryset = LedgerBatch.objects.all()


class LatestCheckpointView(APIView):
    """The newest signed checkpoint."""

    @extend_schema(responses=CheckpointSerializer)
    def get(self, request: Request) -> Response:
        """Return the newest checkpoint."""
        return Response(CheckpointSerializer(_latest_checkpoint()).data)


class CheckpointDetailView(APIView):
    """The checkpoint signed at one tree size."""

    @extend_schema(responses=CheckpointSerializer)
    def get(self, request: Request, tree_size: int) -> Response:
        """Return the checkpoint of this size."""
        return Response(CheckpointSerializer(_checkpoint(tree_size)).data)


@extend_schema(
    parameters=[
        OpenApiParameter("event_type", str, enum=[t.value for t in EventType]),
        OpenApiParameter("account_id", str),
    ]
)
class EventListView(generics.ListAPIView[LedgerEvent]):
    """Events in log order, optionally filtered by type or account."""

    serializer_class = EventSerializer
    pagination_class = EventPages

    def get_queryset(self) -> QuerySet[LedgerEvent]:
        """Apply the optional filters."""
        events = LedgerEvent.objects.all()
        event_type = self.request.query_params.get("event_type")
        if event_type is not None:
            if event_type not in {t.value for t in EventType}:
                raise _bad_request("event_type is not a known event type.")
            events = events.filter(event_type=event_type)
        account_id = self.request.query_params.get("account_id")
        if account_id is not None:
            events = events.filter(account_id=account_id[:200])
        return events


def _event(event_id: str) -> LedgerEvent:
    event = LedgerEvent.objects.filter(public_id=event_id[:64]).first()
    if event is None:
        raise not_found(f"Event {event_id[:64]}")
    return event


class EventDetailView(APIView):
    """One event, with the exact bytes its leaf hash covers."""

    @extend_schema(responses=EventSerializer)
    def get(self, request: Request, event_id: str) -> Response:
        """Return the event."""
        return Response(EventSerializer(_event(event_id)).data)


class InclusionProofView(APIView):
    """An inclusion proof for one event against a signed checkpoint."""

    @extend_schema(
        parameters=[OpenApiParameter("tree_size", int, description="Defaults to the newest.")],
        responses=InclusionProofSerializer,
    )
    def get(self, request: Request, event_id: str) -> Response:
        """Return the audit path and the checkpoint it leads to."""
        event = _event(event_id)
        requested = _int_param(request, "tree_size")
        batch = _latest_checkpoint() if requested is None else _checkpoint(requested)
        if event.leaf_index >= batch.tree_size:
            raise Problem(
                status.HTTP_409_CONFLICT,
                "not-yet-checkpointed",
                "Not yet checkpointed",
                f"Event {event.public_id} is leaf {event.leaf_index}; checkpoint "
                f"{batch.tree_size} does not cover it yet. Checkpoints close within seconds.",
            )
        tree = proofs.tree_covering(batch.tree_size)
        path = tree.inclusion_proof(event.leaf_index, batch.tree_size)
        return Response(
            {
                "event_id": event.public_id,
                "leaf_index": event.leaf_index,
                "tree_size": batch.tree_size,
                "leaf_hash_hex": bytes(event.leaf_hash).hex(),
                "audit_path_hex": [node.hex() for node in path],
                "checkpoint_note": batch.checkpoint_note,
            }
        )


class ConsistencyProofView(APIView):
    """Proof that one signed checkpoint extends another."""

    @extend_schema(
        parameters=[
            OpenApiParameter("first", int, required=True),
            OpenApiParameter("second", int, description="Defaults to the newest."),
        ],
        responses=ConsistencyProofSerializer,
    )
    def get(self, request: Request) -> Response:
        """Return the consistency proof between two signed sizes."""
        first_size = _int_param(request, "first")
        if first_size is None:
            raise _bad_request("first is required.")
        second_size = _int_param(request, "second")
        second = _latest_checkpoint() if second_size is None else _checkpoint(second_size)
        first = _checkpoint(first_size)
        if first.tree_size > second.tree_size:
            raise _bad_request("first must not be larger than second.")
        tree = proofs.tree_covering(second.tree_size)
        proof = tree.consistency_proof(first.tree_size, second.tree_size)
        return Response(
            {
                "first_size": first.tree_size,
                "second_size": second.tree_size,
                "proof_hex": [node.hex() for node in proof],
                "first_note": first.checkpoint_note,
                "second_note": second.checkpoint_note,
            }
        )


class BatchConsistencyView(APIView):
    """Proof that a batch's checkpoint extends the checkpoint before it."""

    @extend_schema(responses=ConsistencyProofSerializer)
    def get(self, request: Request, batch_id: str) -> Response:
        """Return the consistency proof from the previous checkpoint to this batch's."""
        batch = LedgerBatch.objects.filter(public_id=batch_id[:64]).first()
        if batch is None:
            raise not_found(f"Batch {batch_id[:64]}")
        previous = (
            LedgerBatch.objects.filter(tree_size__lt=batch.tree_size).order_by("-tree_size").first()
        )
        if previous is None:
            raise Problem(
                status.HTTP_409_CONFLICT,
                "first-batch",
                "No earlier checkpoint",
                "This is the first checkpoint; there is nothing earlier to prove it extends.",
            )
        tree = proofs.tree_covering(batch.tree_size)
        proof = tree.consistency_proof(previous.tree_size, batch.tree_size)
        return Response(
            {
                "first_size": previous.tree_size,
                "second_size": batch.tree_size,
                "proof_hex": [node.hex() for node in proof],
                "first_note": previous.checkpoint_note,
                "second_note": batch.checkpoint_note,
            }
        )


def _totals(tree_size: int | None) -> LedgerTotals:
    rows = LedgerTotals.objects.order_by("-tree_size")
    totals = rows.first() if tree_size is None else rows.filter(tree_size=tree_size).first()
    if totals is None:
        what = "Signed totals" if tree_size is None else f"Signed totals for checkpoint {tree_size}"
        raise not_found(what)
    return totals


class LatestTotalsView(APIView):
    """The newest signed Merkle-sum tree root."""

    @extend_schema(responses=TotalsSerializer)
    def get(self, request: Request) -> Response:
        """Return the newest signed totals."""
        totals = _totals(None)
        return Response(
            {
                "tree_size": totals.tree_size,
                "records": totals.records,
                "root_hash_hex": bytes(totals.root_hash).hex(),
                "totals_note": totals.totals_note,
            }
        )


class TotalProofView(APIView):
    """A proof of one total against a signed sum tree, without listing its records."""

    @extend_schema(
        parameters=[
            OpenApiParameter("entity", str, required=True, enum=[OBLIGATIONS, OUTLAYS]),
            OpenApiParameter("agency", str, description="Awarding agency, exactly as recorded."),
            OpenApiParameter("fiscal_year", int, description="Needs an agency."),
            OpenApiParameter("tree_size", int, description="Defaults to the newest signed totals."),
        ],
        responses=TotalProofSerializer,
    )
    def get(self, request: Request) -> Response:
        """Return the proof, the signed note it checks against, and what it establishes."""
        entity = request.query_params.get("entity")
        if entity not in (OBLIGATIONS, OUTLAYS):
            raise _bad_request(f"entity must be {OBLIGATIONS} or {OUTLAYS}.")
        agency = request.query_params.get("agency")
        year = _int_param(request, "fiscal_year")
        if agency is not None and (len(agency) > 200 or "\x00" in agency):
            raise _bad_request("agency is too long or not text.")
        if year is not None and agency is None:
            raise _bad_request("fiscal_year needs an agency.")
        totals = _totals(_int_param(request, "tree_size"))
        tree = proofs.sum_tree(totals.tree_size)
        proof = tree.prove(prefix(entity, agency, year))
        proven = verify_total(proof, bytes(totals.root_hash))
        if proven is None:  # the stored root and the rebuilt tree disagree: say so loudly
            raise Problem(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "totals-mismatch",
                "Totals don't match their signature",
                f"The sum tree rebuilt for checkpoint {totals.tree_size} doesn't match"
                " its signed root.",
            )
        return Response(
            {
                "tree_size": totals.tree_size,
                "totals_note": totals.totals_note,
                "total_cents": str(proven.total),
                "count": proven.count,
                "proof": proof_to_json(proof),
            }
        )
