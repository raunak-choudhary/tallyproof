"""Bounds on how much one process, and one address, can ask of the model.

Answering a question takes tens of seconds of model time and spends tokens from a
daily allowance. Two limits keep that bounded:

- **In flight.** At most ``ANALYST_MAX_INFLIGHT`` questions are answered at once in
  one process. Past that, a question gets a 503 with ``Retry-After`` straight away,
  instead of waiting behind slow model calls and tying up a worker.
- **Per address.** Each client address may spend ``ANALYST_PER_IP_DAILY_TOKENS``
  model tokens a day. Tokens are charged after every model call, and no call is
  made once the address is past its budget, so a question stops midway and is
  refused with ``budget_exceeded``.
- **Per call.** No prompt longer than ``LLM_MAX_INPUT_TOKENS`` (estimated) is sent.

Both live in this process's memory (the in-flight count) and in Django's cache (the
token counts). With several processes each enforces its own share; a shared cache
such as Redis makes the token budget global.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache

from django.core.cache import cache

from apps.analyst.llm import (
    BudgetExceededError,
    LLMClient,
    LLMRequest,
    LLMResponse,
    estimate_tokens,
)
from config.env import app_settings

RETRY_AFTER_SECONDS = 30
DAY_SECONDS = 26 * 3600
"""A little over a day, so a count outlives the UTC day it belongs to."""


class BusyError(Exception):
    """Every answering slot in this process is taken."""


@lru_cache(maxsize=1)
def _slots() -> threading.BoundedSemaphore:
    return threading.BoundedSemaphore(app_settings().analyst_max_inflight)


@contextmanager
def answering_slot() -> Iterator[None]:
    """Hold one answering slot, or raise :class:`BusyError` at once if none is free."""
    slots = _slots()
    if not slots.acquire(blocking=False):
        raise BusyError
    try:
        yield
    finally:
        slots.release()


def _key(address: str) -> str:
    return f"analyst-tokens:{datetime.now(UTC).date().isoformat()}:{address}"


def tokens_spent(address: str) -> int:
    """Model tokens this address has spent today (UTC)."""
    return int(cache.get(_key(address), 0))


def over_budget(address: str) -> bool:
    """Whether this address has used up today's token budget."""
    return tokens_spent(address) >= app_settings().analyst_per_ip_daily_tokens


def spend(address: str, tokens: int) -> None:
    """Add tokens to this address's count for today."""
    if tokens <= 0:
        return
    key = _key(address)
    cache.add(key, 0, DAY_SECONDS)
    try:
        cache.incr(key, tokens)
    except ValueError:  # the key expired between add and incr
        cache.set(key, tokens, DAY_SECONDS)


@dataclass
class CountingClient:
    """Passes requests through, counts their tokens, and charges them to an address.

    Each call is refused before it is made if its prompt is past ``max_input_tokens``
    or the address is already past today's budget.
    """

    inner: LLMClient
    address: str | None = None
    max_input_tokens: int | None = None
    tokens: int = field(default=0)

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Check the limits, call the inner client, and charge the tokens it used."""
        if self.max_input_tokens is not None:
            prompt = estimate_tokens("".join(m.content for m in request.messages))
            if prompt > self.max_input_tokens:
                raise BudgetExceededError(
                    f"input of about {prompt} tokens is past the cap of {self.max_input_tokens}"
                )
        if self.address is not None and over_budget(self.address):
            raise BudgetExceededError("this address has used today's token budget")
        response = self.inner.complete(request)
        used = response.input_tokens + response.output_tokens
        self.tokens += used
        if self.address is not None:
            spend(self.address, used)
        return response
