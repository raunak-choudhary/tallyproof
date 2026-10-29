"""Wire the pipeline to the real database, model, and policy index, and store answers."""

from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from django.db import connections

from apps.analyst.answer import Evidence
from apps.analyst.llm import LLMClient, LLMError, LLMRequest, LLMResponse, OpenAICompatibleClient
from apps.analyst.models import AnalystAnswer
from apps.analyst.pipeline import COMPOSER_VERSION, FALLBACK_VERSION, Answer, Executor, Models, ask
from apps.analyst.retrieval import FastEmbedder, Hit, PolicyIndex, load_leaves
from apps.analyst.router import PROMPT_VERSION
from apps.ledger.models import LedgerBatch
from config.env import app_settings, llm_settings
from tallyproof_core.ids import new_id

REFUSAL_MESSAGES = {
    "forecast": "The records describe what happened; they can't say what will happen.",
    "personal_data": "This project holds no personal data and doesn't look it up.",
    "judgment_beyond_data": "The records can show what happened, not whether anyone did wrong.",
    "out_of_scope": "That isn't a question about federal contract records.",
    "no_data": "The ledger doesn't hold data that answers this.",
    "no_evidence": "No records in the ledger match this question.",
    "ambiguous": "More than one record matches; ask about a specific one.",
    "too_broad": "Answering would mean citing more records than one answer may carry.",
    "unsafe_query": "The question couldn't be turned into a query that's safe to run.",
    "unverifiable_claim": "The drafted answer didn't pass verification, so it isn't shown.",
    "budget_exceeded": "The analyst has reached its usage limit for now.",
    "model_unavailable": "The language model isn't available right now.",
    "no_checkpoint": "Nothing has been signed into the log yet.",
}


class AnalystConnection:
    """Runs SQL on the read-only analyst connection."""

    def __init__(self, alias: str = "analyst") -> None:
        """Use the database alias configured from ``DB_ANALYST_URL``."""
        self.alias = alias

    def run(self, sql: str, params: Sequence[Any]) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Execute one statement. Without parameters, ``%`` in the SQL stays literal."""
        with connections[self.alias].cursor() as cursor:
            cursor.execute(sql, list(params) if params else None)
            columns = [c.name for c in cursor.description or []]
            return columns, [tuple(r) for r in cursor.fetchall()]


class Unavailable:
    """Stands in when no model provider is configured; rule-only routes still work."""

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Always fail, so the pipeline refuses with ``model_unavailable``."""
        raise LLMError("no model provider is configured")


@lru_cache(maxsize=1)
def model_client() -> LLMClient:
    """The process's model client, built from settings once."""
    settings = llm_settings()
    if settings.llm_provider != "openai_compatible":
        return Unavailable()
    assert settings.llm_base_url is not None  # noqa: S101 - checked by LLMSettings
    assert settings.llm_api_key is not None  # noqa: S101 - checked by LLMSettings
    return OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        requests_per_minute=settings.llm_requests_per_minute,
    )


@lru_cache(maxsize=1)
def policy_index() -> PolicyIndex:
    """The FAR index, built on first use; chunk vectors are cached on disk."""
    settings = llm_settings()
    embedder = FastEmbedder(settings.embedding_model, settings.embedding_cache_dir / "models")
    return PolicyIndex(load_leaves(), embedder, cache_dir=settings.embedding_cache_dir)


def search_policy(question: str, k: int) -> Sequence[Hit]:
    """Search the FAR index."""
    return policy_index().search(question, k)


def agencies(executor: Executor) -> list[str]:
    """Agency names exactly as the data spells them, for the router's prompt."""
    _, rows = executor.run(
        "SELECT DISTINCT awarding_agency FROM analyst.awards "
        "WHERE awarding_agency IS NOT NULL ORDER BY 1",
        [],
    )
    return [r[0] for r in rows]


def models() -> Models:
    """Model IDs and limits from settings."""
    settings = llm_settings()
    return Models(
        router=settings.router_model or "none",
        answer=settings.llm_answer_model or "none",
        max_output_tokens=settings.llm_max_output_tokens,
        max_rows=app_settings().db_analyst_max_rows,
        reasoning_effort=settings.llm_reasoning_effort,
    )


def _body(answer: Answer, chosen: Models) -> dict[str, Any]:
    evidence = answer.evidence or Evidence()
    sources = evidence.sources
    return {
        "slots": [
            {
                "label": s.label,
                "kind": s.kind,
                "value": str(s.value),
                "display": s.rendered(),
                "meaning": s.words,
                "citation": s.citation,
            }
            for s in evidence.slots.values()
        ],
        "citations": [
            {
                "label": c.label,
                "meaning": c.words,
                "events": [
                    {"event_id": e, "leaf_index": i}
                    for e, i in zip(c.event_ids, c.leaf_indexes, strict=True)
                ],
            }
            for c in evidence.citations.values()
        ],
        "quotes": [
            {
                "source": q.source,
                "text": q.text,
                "event_id": sources[q.source].event_id,
                "leaf_index": sources[q.source].leaf_index,
                "section": sources[q.source].section,
                "title": sources[q.source].title,
            }
            for q in answer.quotes
        ],
        "versions": {
            "router_model": chosen.router,
            "answer_model": chosen.answer,
            "prompts": [PROMPT_VERSION, COMPOSER_VERSION, FALLBACK_VERSION],
        },
    }


def store(answer: Answer, chosen: Models, tree_size: int) -> AnalystAnswer:
    """Save an answer; the row is never changed afterwards."""
    evidence = answer.evidence
    return AnalystAnswer.objects.create(
        public_id=new_id("ans"),
        question=answer.question,
        status=answer.status,
        category=answer.category or "",
        refusal=answer.refusal or "",
        text=answer.text,
        tree_size=tree_size,
        assurance=evidence.assurance if evidence else "",
        filter_words=evidence.filter_words if evidence else "",
        body=_body(answer, chosen),
    )


def answer_question(
    question: str,
    *,
    executor: Executor | None = None,
    client: LLMClient | None = None,
    search: Any = None,  # noqa: ANN401 - a search callable, swapped in tests
) -> AnalystAnswer:
    """Answer as of the newest signed checkpoint and store the result."""
    latest = LedgerBatch.objects.order_by("-tree_size").values_list("tree_size", flat=True).first()
    chosen = models()
    if latest is None:
        refused = Answer(question, "refused", None, refusal="no_checkpoint")
        return store(refused, chosen, 0)
    runner = executor or AnalystConnection()
    result = ask(
        question,
        client=client or model_client(),
        executor=runner,
        search=search or search_policy,
        models=chosen,
        agencies=agencies(runner),
        tree_size=int(latest),
    )
    return store(result, chosen, int(latest))
