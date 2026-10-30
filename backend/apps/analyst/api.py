"""Ask the analyst a question, and read a stored answer.

Answers carry values, the filter in words, and the events behind every claim,
each with the URL of its inclusion proof. They never carry a verdict: the
client verifies each citation itself.
"""

from typing import Any
from urllib.parse import urlencode

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analyst.limits import RETRY_AFTER_SECONDS, BusyError, answering_slot
from apps.analyst.models import AnalystAnswer
from apps.analyst.service import REFUSAL_MESSAGES, answer_question
from apps.ledger.api.problems import Problem, not_found
from apps.ledger.api.throttling import ClientRateThrottle

MAX_QUESTION = 500


def _proof_url(event_id: str, tree_size: int) -> str:
    return f"/api/v1/events/{event_id}/proof?tree_size={tree_size}"


def _total_proof_url(total: dict[str, Any], tree_size: int) -> str:
    query = {"entity": total["entity"], "tree_size": tree_size}
    if total.get("agency") is not None:
        query["agency"] = total["agency"]
    if total.get("fiscal_year") is not None:
        query["fiscal_year"] = total["fiscal_year"]
    return f"/api/v1/totals/proof?{urlencode(query)}"


class QueryRateThrottle(ClientRateThrottle):
    """Questions cost model calls, so they have their own, tighter limit per IP."""

    scope = "queries"


class QuestionSerializer(serializers.Serializer[Any]):
    """The request body."""

    question = serializers.CharField(min_length=3, max_length=MAX_QUESTION, trim_whitespace=True)


class AnswerSerializer(serializers.Serializer[AnalystAnswer]):
    """A stored answer, shaped for the web app."""

    answer_id = serializers.CharField(source="public_id")
    question = serializers.CharField()
    status = serializers.ChoiceField(choices=["answered", "refused"])
    category = serializers.CharField(allow_blank=True)
    text = serializers.CharField(allow_blank=True)
    refusal = serializers.SerializerMethodField()
    assurance = serializers.CharField(allow_blank=True)
    filter_words = serializers.CharField(allow_blank=True)
    checkpoint_tree_size = serializers.IntegerField(source="tree_size")
    slots = serializers.SerializerMethodField()
    citations = serializers.SerializerMethodField()
    quotes = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_refusal(self, answer: AnalystAnswer) -> dict[str, str] | None:
        """The refusal code and a sentence a reader can understand."""
        if not answer.refusal:
            return None
        return {"code": answer.refusal, "message": REFUSAL_MESSAGES.get(answer.refusal, "")}

    def get_slots(self, answer: AnalystAnswer) -> list[dict[str, Any]]:
        """Each value in the answer, what it means, and the citation behind it."""
        return list(answer.body.get("slots", []))

    def get_citations(self, answer: AnalystAnswer) -> list[dict[str, Any]]:
        """Each citation's events, with where to fetch their proofs.

        A citation whose total can be proven as a whole also gets ``total_proof_url``.
        The service records that only when the answer's checkpoint has signed totals.
        """
        return [
            {
                **cite,
                "total_proof_url": _total_proof_url(cite["total"], answer.tree_size)
                if cite.get("total")
                else None,
                "events": [
                    {
                        **e,
                        "proof_url": _proof_url(e["event_id"], answer.tree_size),
                    }
                    for e in cite["events"]
                ],
            }
            for cite in answer.body.get("citations", [])
        ]

    def get_quotes(self, answer: AnalystAnswer) -> list[dict[str, Any]]:
        """Exact quotes and the policy leaf each one comes from."""
        return [
            {**q, "proof_url": _proof_url(q["event_id"], answer.tree_size)}
            for q in answer.body.get("quotes", [])
        ]


class QueryView(APIView):
    """Ask a question."""

    throttle_classes = (QueryRateThrottle,)

    @extend_schema(
        request=QuestionSerializer,
        responses={
            201: AnswerSerializer,
            400: OpenApiResponse(description="Invalid question"),
            503: OpenApiResponse(description="Every answering slot is taken; see Retry-After"),
        },
    )
    def post(self, request: Request) -> Response:
        """Answer the question as of the newest checkpoint, or refuse with a reason."""
        incoming = QuestionSerializer(data=request.data)
        if not incoming.is_valid():
            raise Problem(
                400,
                "invalid-question",
                "Invalid question",
                f"Send a question of 3 to {MAX_QUESTION} characters.",
            )
        address = QueryRateThrottle().get_ident(request)
        try:
            with answering_slot():
                stored = answer_question(incoming.validated_data["question"], address=address)
        except BusyError as error:
            busy = Problem(
                503,
                "analyst-busy",
                "The analyst is busy",
                "Every answering slot is taken; try again shortly.",
            )
            busy.wait = RETRY_AFTER_SECONDS  # DRF turns this into a Retry-After header
            raise busy from error
        return Response(
            AnswerSerializer(stored).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": f"/api/v1/answers/{stored.public_id}"},
        )


class AnswerView(APIView):
    """One stored answer."""

    @extend_schema(responses=AnswerSerializer)
    def get(self, request: Request, answer_id: str) -> Response:
        """Return the answer."""
        stored = AnalystAnswer.objects.filter(public_id=answer_id[:64]).first()
        if stored is None:
            raise not_found(f"Answer {answer_id[:64]}")
        return Response(AnswerSerializer(stored).data)
