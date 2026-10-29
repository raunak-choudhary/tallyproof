"""The LLM client: one interface, a scripted fake, a real client, a cache, and budgets.

Everything that talks to a model goes through :class:`LLMClient`. Module tests use
:class:`FakeClient` and never touch the network. The real client speaks the
OpenAI chat-completions protocol, which Gemini, Groq, OpenRouter, Together, and a
local Ollama all serve, so the provider is a matter of settings: base URL, key,
and model IDs, none of them in code.

Wrappers stack: ``CachingClient(BudgetedClient(OpenAICompatibleClient(...)))``.
A cache hit never reaches the budget or the network. The cache key is a hash of
the model ID, prompt version, prompt, and parameters, so changing a prompt
invalidates exactly the entries it affects.
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

import requests

if TYPE_CHECKING:
    from config.env import LLMSettings

log = logging.getLogger(__name__)

Role = Literal["system", "user", "assistant"]
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class Message:
    """One chat message."""

    role: Role
    content: str


@dataclass(frozen=True)
class LLMRequest:
    """Everything that determines a model's answer, and nothing else."""

    model: str
    prompt_version: str
    messages: tuple[Message, ...]
    max_tokens: int
    temperature: float = 0.0
    response_schema: dict[str, Any] | None = None
    """JSON Schema the answer must follow, sent as structured output when set."""
    reasoning_effort: str | None = None
    """For models that think before answering. Thinking counts against ``max_tokens``,
    so a high effort can leave no room for the answer itself."""

    def cache_key(self) -> str:
        """A stable hash of the request; any change to it is a new key."""
        body = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode()).hexdigest()


@dataclass(frozen=True)
class LLMResponse:
    """What came back, and what it cost in tokens and time."""

    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int = 0
    cached: bool = False


class LLMError(RuntimeError):
    """The provider failed or returned something unusable."""


class CacheMissError(LLMError):
    """A read-only cache had no entry for a request."""


class BudgetExceededError(LLMError):
    """A run reached its request or token budget; no call was made."""


class LLMClient(Protocol):
    """Anything that can complete a request."""

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the model's response to ``request``."""
        ...


def estimate_tokens(text: str) -> int:
    """A rough token count for budgets and fakes: about four characters per token."""
    return max(1, len(text) // 4)


@dataclass
class FakeClient:
    """Scripted responses for tests and harness checks. Never touches the network.

    ``script`` is either a list of responses returned in order or a function from
    request to response text. Every request is kept in ``requests``.
    """

    script: Sequence[str] | Callable[[LLMRequest], str]
    requests: list[LLMRequest] = field(default_factory=list)

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the next scripted response."""
        self.requests.append(request)
        if callable(self.script):
            text = self.script(request)
        else:
            if len(self.requests) > len(self.script):
                raise LLMError("the fake client ran out of scripted responses")
            text = self.script[len(self.requests) - 1]
        prompt = "".join(m.content for m in request.messages)
        return LLMResponse(text, estimate_tokens(prompt), estimate_tokens(text))


class _Session(Protocol):
    def post(self, url: str, **kwargs: Any) -> requests.Response: ...  # noqa: ANN401


class OpenAICompatibleClient:
    """A client for any provider that serves ``/chat/completions``.

    Requests are paced to ``requests_per_minute`` so a free tier's rate limit isn't
    tripped, and 429 or 5xx answers are retried with exponential backoff,
    honoring ``Retry-After``. The key travels only in the Authorization header and
    is never logged.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        max_retries: int,
        requests_per_minute: int,
        session: _Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Set up the client; nothing is sent until :meth:`complete`."""
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._timeout = timeout_seconds
        self._retries = max_retries
        self._interval = 60.0 / requests_per_minute
        self._session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last_sent: float | None = None

    def _pace(self) -> None:
        if self._last_sent is not None:
            wait = self._interval - (self._clock() - self._last_sent)
            if wait > 0:
                self._sleep(wait)
        self._last_sent = self._clock()

    def _body(self, request: LLMRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.reasoning_effort is not None:
            body["reasoning_effort"] = request.reasoning_effort
        if request.response_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.prompt_version.replace(".", "_").replace("-", "_"),
                    "schema": request.response_schema,
                    # Strict mode demands every field be required, which optional
                    # spec parts can't meet; the server validates the result anyway.
                    "strict": False,
                },
            }
        return body

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Send the request, retrying rate limits and server errors."""
        body = self._body(request)
        for attempt in range(self._retries + 1):
            self._pace()
            started = self._clock()
            try:
                reply = self._session.post(
                    self._url, json=body, headers=self._headers, timeout=self._timeout
                )
            except requests.RequestException as error:
                if attempt == self._retries:
                    raise LLMError(f"request failed: {type(error).__name__}") from error
                self._sleep(2.0**attempt)
                continue
            if reply.status_code in RETRY_STATUSES and attempt < self._retries:
                retry_after = reply.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 2.0**attempt
                log.warning("llm retry", extra={"status": reply.status_code, "delay": delay})
                self._sleep(delay)
                continue
            if reply.status_code != 200:
                raise LLMError(f"provider returned HTTP {reply.status_code}")
            return self._parse(reply, started)
        raise LLMError("retries exhausted")  # pragma: no cover - the loop always returns or raises

    def _parse(self, reply: requests.Response, started: float) -> LLMResponse:
        try:
            data = reply.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise LLMError("provider returned an unreadable response") from error
        if not isinstance(text, str):
            raise LLMError("provider returned no text")
        return LLMResponse(
            text=text,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=int((self._clock() - started) * 1000),
        )


@dataclass(frozen=True)
class Budget:
    """Caps for one run. A call is refused before it is made, never after."""

    max_requests: int
    max_tokens: int


@dataclass
class BudgetedClient:
    """Counts requests and tokens, and refuses to call past the budget."""

    inner: LLMClient
    budget: Budget
    requests: int = 0
    tokens: int = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Call the inner client if the budget allows this request in full."""
        prompt = "".join(m.content for m in request.messages)
        worst_case = self.tokens + estimate_tokens(prompt) + request.max_tokens
        if self.requests >= self.budget.max_requests or worst_case > self.budget.max_tokens:
            raise BudgetExceededError(
                f"run budget reached: {self.requests} requests, {self.tokens} tokens"
            )
        response = self.inner.complete(request)
        self.requests += 1
        self.tokens += response.input_tokens + response.output_tokens
        return response


@dataclass
class CachingClient:
    """Stores responses as reviewable JSON files keyed by :meth:`LLMRequest.cache_key`.

    With ``inner=None`` the cache is read-only: a miss raises
    :class:`CacheMissError`, which is how CI replays recorded responses without a
    key. Otherwise misses go to ``inner`` and are written back.
    """

    directory: Path
    inner: LLMClient | None = None
    hits: int = 0
    misses: int = 0

    def _path(self, key: str) -> Path:
        return self.directory / key[:2] / f"{key}.json"

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the stored response, or fetch and store a new one."""
        key = request.cache_key()
        path = self._path(key)
        if path.exists():
            self.hits += 1
            stored = json.loads(path.read_text(encoding="utf-8"))["response"]
            return LLMResponse(**{**stored, "cached": True})
        self.misses += 1
        if self.inner is None:
            raise CacheMissError(f"no cached response for {request.prompt_version}")
        response = self.inner.complete(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "request": {
                "model": request.model,
                "prompt_version": request.prompt_version,
                "messages": [asdict(m) for m in request.messages],
            },
            "response": {
                "text": response.text,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "latency_ms": response.latency_ms,
            },
        }
        path.write_text(json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return response


Mode = Literal["fake", "cached", "live"]


def client_for(
    mode: Mode, settings: "LLMSettings", script: Callable[[LLMRequest], str] | None = None
) -> LLMClient:
    """Build the client for a run.

    ``fake`` answers from ``script``. ``cached`` replays recorded responses and
    raises on a miss, which is what CI uses. ``live`` calls the provider within
    the run budget and records every response.
    """
    if mode == "fake":
        if script is None:
            raise ValueError("fake mode needs a script")
        return FakeClient(script)
    if mode == "cached":
        return CachingClient(settings.llm_cache_dir)
    if settings.llm_provider != "openai_compatible":
        raise LLMError("live mode needs LLM_PROVIDER=openai_compatible and its settings")
    assert settings.llm_base_url is not None  # noqa: S101 - checked by LLMSettings
    assert settings.llm_api_key is not None  # noqa: S101 - checked by LLMSettings
    real = OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        requests_per_minute=settings.llm_requests_per_minute,
    )
    budget = Budget(settings.llm_run_max_requests, settings.llm_run_max_tokens)
    return CachingClient(settings.llm_cache_dir, BudgetedClient(real, budget))
