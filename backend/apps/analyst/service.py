"""Wire the pipeline to the real database, model, and policy index, and store answers."""

from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from django.core.cache import cache
from django.db import connections

from apps.analyst import limits
from apps.analyst.answer import Evidence
from apps.analyst.llm import LLMClient, LLMError, LLMRequest, LLMResponse, OpenAICompatibleClient
from apps.analyst.models import AnalystAnswer
from apps.analyst.pipeline import COMPOSER_VERSION, FALLBACK_VERSION, Answer, Executor, Models, ask
from apps.analyst.retrieval import FastEmbedder, Hit, PolicyIndex, load_leaves
from apps.analyst.router import PROMPT_VERSION
from apps.ledger.models import LedgerBatch, LedgerTotals
from config.env import app_settings, llm_settings
from config.tracing import current_correlation_id, tracer
from tallyproof_core.ids import new_id

REFUSAL_MESSAGES = {
    "forecast": "The records describe what happened; they can't say what will happen.",
    "personal_data": "This project holds no personal data and doesn't look it up.",
    "judgment_beyond_data": "The records can show what happened, not whether anyone did wrong.",
    "out_of_scope": "That isn't a question about federal contract records.",
    "no_data": "The ledger doesn't hold data that answers this.",
    "no_evidence": "No records in the ledger match this question.",
    "ambiguous": "More than 10 records match; ask about a specific one.",
    "too_broad": "That list has more records than one answer may carry; narrow the question.",
    "unsafe_query": "The question couldn't be turned into a query that's safe to run.",
    "unverifiable_claim": "The drafted answer didn't pass verification, so it isn't shown.",
    "budget_exceeded": "This address has used today's share of the analyst; try again tomorrow.",
    "model_unavailable": "The language model isn't available right now.",
    "no_checkpoint": "Nothing has been signed into the log yet.",
    "not_expressible": "The analyst can't express this as a query it knows how to check.",
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
        max_retry_wait=app_settings().analyst_max_retry_wait_seconds,
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


MAX_AGENCIES = 200
"""Most agency names the router's prompt lists, so the prompt stays bounded."""
AGENCY_CACHE_SECONDS = 300


def agencies(executor: Executor, *, tree_size: int | None = None) -> list[str]:
    """Agency names exactly as the data spells them, for the router's prompt.

    With ``tree_size``, the list is cached for that checkpoint, so a question doesn't
    pay for a scan of every award.
    """
    key = f"analyst-agencies:{tree_size}"
    if tree_size is not None and (cached := cache.get(key)) is not None:
        return list(cached)
    _, rows = executor.run(
        "SELECT DISTINCT awarding_agency FROM analyst.awards "
        "WHERE awarding_agency IS NOT NULL ORDER BY 1 LIMIT %s",
        [MAX_AGENCIES],
    )
    names = [r[0] for r in rows]
    if tree_size is not None:
        cache.set(key, names, AGENCY_CACHE_SECONDS)
    return names


def models() -> Models:
    """Model IDs and limits from settings."""
    settings = llm_settings()
    return Models(
        router=settings.router_model or "none",
        answer=settings.llm_answer_model or "none",
        max_output_tokens=settings.llm_max_output_tokens,
        max_rows=app_settings().db_analyst_max_rows,
        reasoning_effort=settings.llm_reasoning_effort,
        allow_fallback=app_settings().analyst_sql_fallback,
    )


def _body(answer: Answer, chosen: Models, totals_signed: bool = False) -> dict[str, Any]:
    """The stored answer's body.

    ``totals_signed`` says the answer's checkpoint has signed totals, so a citation
    that can be proven as a whole records which total; otherwise none does.
    """
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
                "sample_of": c.sample_of,
                "total": None
                if c.total is None or not totals_signed
                else {
                    "entity": c.total.entity,
                    "agency": c.total.agency,
                    "fiscal_year": c.total.fiscal_year,
                },
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


def pinned_size() -> int | None:
    """The checkpoint new answers are pinned to: the newest with signed totals, if any."""
    totals = LedgerTotals.objects.order_by("-tree_size").values_list("tree_size", flat=True)
    newest_totals = totals.first()
    if newest_totals is not None:
        return int(newest_totals)
    latest = LedgerBatch.objects.order_by("-tree_size").values_list("tree_size", flat=True).first()
    return None if latest is None else int(latest)


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
        body=_body(
            answer,
            chosen,
            totals_signed=LedgerTotals.objects.filter(tree_size=tree_size).exists(),
        ),
    )


def answer_question(
    question: str,
    *,
    executor: Executor | None = None,
    client: LLMClient | None = None,
    search: Any = None,  # noqa: ANN401 - a search callable, swapped in tests
    chosen: Models | None = None,
    address: str | None = None,
) -> AnalystAnswer:
    """Answer as of the newest checkpoint whose totals are signed, and store the result.

    Pinning to signed totals lets a total in the answer be proven as a whole
    (ADR-0024). They are signed at every checkpoint while the log is small, so on a
    small log this is simply the newest checkpoint; with no totals yet, it is too.

    With ``address``, the answer counts against that address's daily token budget,
    and a question from an address past its budget is refused without a model call.
    The whole answer is one span, tagged with the request's correlation ID.
    """
    with tracer().start_as_current_span("analyst.answer") as span:
        span.set_attribute("tallyproof.correlation_id", current_correlation_id() or "")
        stored = _answer_question(
            question,
            executor=executor,
            client=client,
            search=search,
            chosen=chosen,
            address=address,
        )
        span.set_attribute("tallyproof.status", stored.status)
        span.set_attribute("tallyproof.refusal", stored.refusal)
        span.set_attribute("tallyproof.tree_size", stored.tree_size)
        return stored


def _answer_question(
    question: str,
    *,
    executor: Executor | None,
    client: LLMClient | None,
    search: Any,  # noqa: ANN401
    chosen: Models | None,
    address: str | None,
) -> AnalystAnswer:
    latest = pinned_size()
    chosen = chosen or models()
    if latest is None:
        refused = Answer(question, "refused", None, refusal="no_checkpoint")
        return store(refused, chosen, 0)
    if address is not None and limits.over_budget(address):
        return store(
            Answer(question, "refused", None, refusal="budget_exceeded"), chosen, int(latest)
        )
    runner = executor or AnalystConnection()
    # Charges each model call as it returns, so a question that fails midway still counts.
    counting = limits.CountingClient(
        client or model_client(),
        address=address,
        max_input_tokens=llm_settings().llm_max_input_tokens,
    )
    result = ask(
        question,
        client=counting,
        executor=runner,
        search=search or search_policy,
        models=chosen,
        agencies=agencies(runner, tree_size=int(latest)),
        tree_size=int(latest),
    )
    return store(result, chosen, int(latest))
