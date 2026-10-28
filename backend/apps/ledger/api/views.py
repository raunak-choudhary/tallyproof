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
)
from apps.ledger.models import LedgerBatch, LedgerEvent
from config.env import app_settings
from tallyproof_core.events import EventType


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
