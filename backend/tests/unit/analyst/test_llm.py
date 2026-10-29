"""LLM clients: no test here ever reaches the network."""

import json
from typing import Any

import pytest
import requests
from pydantic import SecretStr

from apps.analyst.llm import (
    Budget,
    BudgetedClient,
    BudgetExceededError,
    CacheMissError,
    CachingClient,
    FakeClient,
    LLMError,
    LLMRequest,
    Message,
    OpenAICompatibleClient,
    client_for,
)
from config.env import LLMSettings


def settings_from(values: dict[str, Any]) -> LLMSettings:
    """Settings from these values only, never from the developer's .env."""
    return LLMSettings(_env_file=None, **values)


BASE = "https://llm.invalid/v1beta/openai/"  # .invalid never resolves


def request(text: str = "How much?", **extra: Any) -> LLMRequest:
    return LLMRequest(
        model="model-a",
        prompt_version="router.v1",
        messages=(Message("system", "Answer in JSON."), Message("user", text)),
        max_tokens=100,
        **extra,
    )


class Reply:
    def __init__(self, status: int, body: object = None, headers: dict[str, str] | None = None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self) -> object:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Session:
    def __init__(self, *replies: object):
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> Any:
        self.calls.append({"url": url, **kwargs})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def ok(text: str = '{"shape": "list"}') -> Reply:
    return Reply(
        200,
        {
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        },
    )


class Clock:
    def __init__(self) -> None:
        self.now = 100.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def real(
    session: Session, clock: Clock, *, rpm: int = 60, retries: int = 2
) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        base_url=BASE,
        api_key="sk-test",
        timeout_seconds=5,
        max_retries=retries,
        requests_per_minute=rpm,
        session=session,
        sleep=clock.sleep,
        clock=clock.time,
    )


def test_the_real_client_sends_the_chat_protocol_with_structured_output():
    session, clock = Session(ok()), Clock()
    schema = {"type": "object", "properties": {"shape": {"type": "string"}}}
    response = real(session, clock).complete(request(response_schema=schema))
    assert response.text == '{"shape": "list"}'
    assert (response.input_tokens, response.output_tokens) == (12, 5)
    call = session.calls[0]
    assert call["url"] == BASE + "chat/completions"
    assert call["headers"]["Authorization"] == "Bearer sk-test"
    assert call["timeout"] == 5
    body = call["json"]
    assert body["model"] == "model-a"
    assert body["messages"][1] == {"role": "user", "content": "How much?"}
    assert body["temperature"] == 0.0
    assert body["response_format"]["json_schema"] == {
        "name": "router_v1",
        "schema": schema,
        "strict": False,
    }


def test_rate_limits_and_server_errors_are_retried_with_backoff():
    session, clock = Session(Reply(429, headers={"Retry-After": "7"}), Reply(503), ok()), Clock()
    assert real(session, clock, rpm=600).complete(request()).text
    assert len(session.calls) == 3
    assert 7.5 in clock.slept  # Retry-After, plus a little margin
    assert 2.0 in clock.slept


def test_fractional_retry_after_is_honored():
    session, clock = Session(Reply(429, headers={"Retry-After": "2.48"}), ok()), Clock()
    real(session, clock, rpm=600).complete(request())
    assert clock.slept == [2.98]


def test_a_wait_past_the_cap_fails_at_once_instead_of_holding_the_worker():
    session = Session(Reply(429, headers={"Retry-After": "86400"}), ok())
    clock = Clock()
    client = OpenAICompatibleClient(
        base_url=BASE, api_key="sk-test", timeout_seconds=5, max_retries=2,
        requests_per_minute=600, session=session, sleep=clock.sleep, clock=clock.time,
        max_retry_wait=10,
    )  # fmt: skip
    with pytest.raises(LLMError, match="wait"):
        client.complete(request())
    assert len(session.calls) == 1
    assert all(s < 10 for s in clock.slept)


def test_requests_are_paced_to_the_rate_limit():
    session, clock = Session(ok(), ok()), Clock()
    client = real(session, clock, rpm=10)
    client.complete(request())
    client.complete(request())
    assert clock.slept == [6.0]


@pytest.mark.parametrize(
    ("replies", "message"),
    [
        ((Reply(401),), "HTTP 401"),
        ((Reply(429), Reply(429), Reply(429)), "HTTP 429"),
        ((Reply(200, ValueError("not json")),), "unreadable"),
        ((Reply(200, {"choices": []}),), "unreadable"),
        ((Reply(200, {"choices": [{"message": {"content": None}}]}),), "no text"),
        (
            (requests.ConnectionError(), requests.Timeout(), requests.ConnectionError()),
            "ConnectionError",
        ),
    ],
)
def test_failures_raise_without_leaking_the_key(replies, message):
    with pytest.raises(LLMError, match=message) as caught:
        real(Session(*replies), Clock()).complete(request())
    assert "sk-test" not in str(caught.value)


def test_the_fake_follows_its_script_and_runs_out_loudly():
    fake = FakeClient(["one", "two"])
    assert [fake.complete(request()).text for _ in range(2)] == ["one", "two"]
    with pytest.raises(LLMError, match="ran out"):
        fake.complete(request())
    assert FakeClient(lambda r: r.messages[-1].content.upper()).complete(request("hi")).text == "HI"


def test_a_budget_refuses_before_calling():
    fake = FakeClient(lambda r: "ok")
    budgeted = BudgetedClient(fake, Budget(max_requests=2, max_tokens=10_000))
    budgeted.complete(request())
    budgeted.complete(request())
    with pytest.raises(BudgetExceededError):
        budgeted.complete(request())
    assert len(fake.requests) == 2
    tight = BudgetedClient(FakeClient(lambda r: "ok"), Budget(max_requests=9, max_tokens=50))
    with pytest.raises(BudgetExceededError):
        tight.complete(request())  # 100 output tokens could exceed 50


def test_the_cache_records_replays_and_keys_on_everything_that_matters(tmp_path):
    fake = FakeClient(lambda r: "answer")
    live = CachingClient(tmp_path, fake)
    first = live.complete(request())
    again = live.complete(request())
    assert (first.cached, again.cached, again.text) == (False, True, "answer")
    assert len(fake.requests) == 1
    live.complete(request(temperature=0.5))
    live.complete(LLMRequest("model-b", "router.v1", request().messages, 100))
    live.complete(LLMRequest("model-a", "router.v2", request().messages, 100))
    assert len(fake.requests) == 4
    stored = json.loads(next(tmp_path.rglob("*.json")).read_text())
    assert stored["request"]["prompt_version"] in {"router.v1", "router.v2"}
    replay = CachingClient(tmp_path)
    assert replay.complete(request()).text == "answer"
    with pytest.raises(CacheMissError):
        replay.complete(request("something new"))


def test_client_for_builds_each_mode(tmp_path):
    settings = settings_from({"LLM_CACHE_DIR": str(tmp_path)})
    assert isinstance(client_for("fake", settings, lambda r: "x"), FakeClient)
    assert isinstance(client_for("cached", settings), CachingClient)
    with pytest.raises(ValueError, match="script"):
        client_for("fake", settings)
    with pytest.raises(LLMError, match="LLM_PROVIDER"):
        client_for("live", settings)
    live = settings_from(
        {
            "LLM_PROVIDER": "openai_compatible",
            "LLM_BASE_URL": BASE,
            "LLM_API_KEY": "sk-test",
            "LLM_ANSWER_MODEL": "model-a",
            "LLM_CACHE_DIR": str(tmp_path),
        }
    )
    client = client_for("live", live)
    assert isinstance(client, CachingClient)
    assert isinstance(client.inner, BudgetedClient)


def test_the_real_provider_needs_its_url_key_and_model(monkeypatch):
    for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_ANSWER_MODEL", "LLM_ROUTER_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="LLM_BASE_URL, LLM_API_KEY, LLM_ANSWER_MODEL"):
        settings_from({"LLM_PROVIDER": "openai_compatible"})
    settings = settings_from({"LLM_ANSWER_MODEL": "model-a", "LLM_API_KEY": SecretStr("k")})
    assert settings.router_model == settings.judge_model == "model-a"
