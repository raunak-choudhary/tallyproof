"""Bounds on how much one process, and one address, can ask of the model.

Answering a question takes tens of seconds of model time and spends tokens from a
daily allowance. Two limits keep that bounded:

- **In flight.** At most ``ANALYST_MAX_INFLIGHT`` questions are answered at once in
  one process. Past that, a question gets a 503 with ``Retry-After`` straight away,
  instead of waiting behind slow model calls and tying up a worker.
- **Per address.** Each client address may spend ``ANALYST_PER_IP_DAILY_TOKENS``
  model tokens a day. Past that, questions are refused with ``budget_exceeded``
  without calling the model.

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

from apps.analyst.llm import LLMClient, LLMRequest, LLMResponse
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
    """Passes requests through and counts the tokens they used."""

    inner: LLMClient
    tokens: int = field(default=0)

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Call the inner client and add up the tokens."""
        response = self.inner.complete(request)
        self.tokens += response.input_tokens + response.output_tokens
        return response
