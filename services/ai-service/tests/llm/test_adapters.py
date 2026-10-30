"""T2.10: provider adapters. Anthropic's real SDK runs against a fake API (httpx2.MockTransport)."""

import io
import json
import logging
import uuid
from collections.abc import Iterator

import httpx2
import pytest

from ai_service.config import Settings
from ai_service.llm.anthropic_adapter import MAX_TOKENS, AnthropicAdapter
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.pricing import FAKE_MODEL
from ai_service.llm.types import LlmRequest, ProviderError
from ai_service.logging import configure_logging
from tests.llm.helpers import FAKE_KEY, SCHEMA, FakeAnthropicApi, answering, failing, make_request

MODEL = "claude-haiku-5-5"


def adapter_on(api: FakeAnthropicApi) -> AnthropicAdapter:
    return AnthropicAdapter(api_key=FAKE_KEY, http_client=api.client())


# --- Anthropic -------------------------------------------------------------------------------


def test_t210_anthropic_sends_instructions_as_system_and_data_as_the_user_message() -> None:
    # Red when: the data block is folded into the system prompt (ADR-0010: data never sits with
    # the instructions), or the schema is not sent and the output is free text.
    api = answering()
    request = make_request()
    adapter_on(api).complete(request, model=MODEL, timeout=5.0)
    body = api.body()
    assert body["model"] == MODEL
    assert body["system"] == request.system
    assert body["messages"] == [{"role": "user", "content": request.user}]
    assert body["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}


def test_g6_anthropic_caps_the_output_tokens() -> None:
    # Red when: max_tokens grows, and one call can cost more than the plan's ceiling (G6).
    api = answering()
    adapter_on(api).complete(make_request(), model=MODEL, timeout=5.0)
    assert api.body()["max_tokens"] == MAX_TOKENS == 800


def test_g6_anthropic_turns_thinking_off() -> None:
    # Red when: Haiku 5.5's default adaptive thinking stays on: thinking tokens count against
    # the 800-token cap, can cut the JSON short (grade_invalid) and stretch past 8 s (AC3).
    api = answering()
    adapter_on(api).complete(make_request(), model=MODEL, timeout=5.0)
    assert api.body()["thinking"] == {"type": "disabled"}
    assert "temperature" not in api.body()  # refused by the API since 2026-10-21


def test_t210_anthropic_params_are_what_it_sends() -> None:
    # Red when: params (written to llm_call) drift from the request the SDK actually sends.
    api = answering()
    adapter = adapter_on(api)
    adapter.complete(make_request(), model=MODEL, timeout=5.0)
    assert {key: api.body()[key] for key in adapter.params} == adapter.params


def test_t210_anthropic_returns_the_text_and_the_token_counts() -> None:
    result = adapter_on(answering('{"ok": false}')).complete(
        make_request(), model=MODEL, timeout=5.0
    )
    assert (result.text, result.input_tokens, result.output_tokens) == ('{"ok": false}', 1000, 200)


def test_t210_anthropic_sends_the_key_only_in_its_header() -> None:
    api = answering()
    adapter_on(api).complete(make_request(), model=MODEL, timeout=5.0)
    assert api.requests[0].headers["x-api-key"] == FAKE_KEY
    assert FAKE_KEY not in api.requests[0].content.decode()


@pytest.mark.parametrize("status", [429, 500, 529])
def test_t210_anthropic_sdk_does_not_retry_on_its_own(status: int) -> None:
    # Red when: max_retries is left at the SDK default (2): one grade could make three paid
    # calls, two of them never written to llm_call, and blow the 9 s deadline.
    api = failing(status)
    with pytest.raises(ProviderError):
        adapter_on(api).complete(make_request(), model=MODEL, timeout=5.0)
    assert len(api.requests) == 1


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "provider_rejected"),
        (401, "provider_rejected"),
        (429, "rate_limited"),
        (500, "provider_error"),
        (529, "provider_error"),
    ],
)
def test_t210_anthropic_errors_become_stable_codes(status: int, code: str) -> None:
    with pytest.raises(ProviderError) as raised:
        adapter_on(failing(status)).complete(make_request(), model=MODEL, timeout=5.0)
    assert raised.value.code == code


def test_t210_anthropic_timeout_is_a_provider_error() -> None:
    def time_out(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    with pytest.raises(ProviderError) as raised:
        adapter_on(FakeAnthropicApi(time_out)).complete(make_request(), model=MODEL, timeout=5.0)
    assert raised.value.code == "timeout"


def test_t210_anthropic_connection_failure_is_a_provider_error() -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    with pytest.raises(ProviderError) as raised:
        adapter_on(FakeAnthropicApi(refuse)).complete(make_request(), model=MODEL, timeout=5.0)
    assert raised.value.code == "connection_error"


def test_b2_anthropic_call_gets_the_time_left_as_its_timeout() -> None:
    # Red when: the SDK's 10-minute default applies, and a hung API holds the request past
    # core's 10 s cut (B2: the whole request has 9 s).
    api = answering()
    adapter_on(api).complete(make_request(), model=MODEL, timeout=3.5)
    timeouts = api.requests[0].extensions["timeout"]
    assert set(timeouts.values()) == {3.5}


@pytest.fixture
def debug_log() -> Iterator[io.StringIO]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    buffer = io.StringIO()
    configure_logging("ai-service", "DEBUG", stream=buffer)
    yield buffer
    root.handlers, root.level = saved


def test_adr0013_sdk_debug_logs_carry_neither_the_answer_nor_the_key(
    debug_log: io.StringIO,
) -> None:
    # Red when: the anthropic/httpx2 loggers are left alone at DEBUG: the SDK logs the whole
    # request body (the learner's answer) and response. llm_call keeps those, logs never do.
    request = make_request(user="<answer>learner-answer-text bí mật</answer>")
    api = answering('{"ok": "model-output-text bí mật"}')
    adapter_on(api).complete(request, model=MODEL, timeout=5.0)
    logged = debug_log.getvalue()
    for line in logged.splitlines():
        json.loads(line)  # still one object per line
    for secret in ("learner-answer-text", "model-output-text", "bí mật", "b\\u00ed", FAKE_KEY):
        assert secret not in logged, secret


def test_adr0013_sdk_lines_lose_their_data_even_if_its_logger_is_turned_up(
    debug_log: io.StringIO,
) -> None:
    # Second layer: someone sets the anthropic logger to DEBUG to debug a call. Its lines are
    # written, but as constant events, without the request (_DATA_IN_MESSAGE_LOGGERS).
    logging.getLogger("anthropic").setLevel(logging.DEBUG)
    try:
        request = make_request(user="<answer>learner-answer-text</answer>")
        adapter_on(answering()).complete(request, model=MODEL, timeout=5.0)
    finally:
        logging.getLogger("anthropic").setLevel(logging.WARNING)
    logged = debug_log.getvalue()
    assert '"logger": "anthropic' in logged, "the SDK logged nothing: the test proves nothing"
    assert "learner-answer-text" not in logged
    assert FAKE_KEY not in logged


# --- Fake ------------------------------------------------------------------------------------


def echo(request: LlmRequest) -> str:
    return json.dumps(request.payload, sort_keys=True)


def test_t210_fake_answers_with_the_task_responder_without_a_network() -> None:
    adapter = FakeAdapter({"grade": echo})
    result = adapter.complete(make_request(payload={"b": 2, "a": 1}), model=FAKE_MODEL, timeout=1)
    assert result.text == '{"a": 1, "b": 2}'
    assert (result.input_tokens, result.output_tokens) == (0, 0)


def test_t210_fake_is_deterministic() -> None:
    # Red when: the fake depends on time, order or randomness, and seed tests flicker.
    adapter = FakeAdapter({"grade": echo})
    request = make_request(payload={"answer": "x", "units": [1, 2, 3]})
    texts = {adapter.complete(request, model=FAKE_MODEL, timeout=1).text for _ in range(5)}
    assert len(texts) == 1


def test_t210_fake_without_a_responder_for_the_task_is_an_error() -> None:
    with pytest.raises(ProviderError):
        FakeAdapter({}).complete(make_request(), model=FAKE_MODEL, timeout=1)


# --- Request ---------------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["user_id", "subject_id", "pipeline_run_id"])
def test_t210_call_without_user_id_is_an_error(missing: str) -> None:
    # Red when: a call can be made for nobody, and its cost reaches no user's quota.
    values = make_request().model_dump()
    del values[missing]
    with pytest.raises(ValueError, match=missing):
        LlmRequest(**values)


def test_t210_settings_give_the_task_table_a_priced_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.llm_models == {
        "grade": MODEL,
        "extract_session": MODEL,
        "chunk_units": MODEL,
        "generate_questions": MODEL,
        "parse_command": MODEL,
    }


def test_t210_startup_refuses_a_model_without_a_price(monkeypatch: pytest.MonkeyPatch) -> None:
    # Red when: an unpriced model starts, and its calls are written with cost 0 (🟡c).
    monkeypatch.setenv("AI_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("AI_LLM_MODELS", json.dumps({"grade": "claude-unknown-9"}))
    with pytest.raises(ValueError, match="llm_models"):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_t210_startup_refuses_a_task_without_a_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_LLM_MODELS", json.dumps({}))
    with pytest.raises(ValueError, match="llm_models"):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_t210_request_ids_are_uuids() -> None:
    with pytest.raises(ValueError):
        make_request(user_id="not-a-uuid")
    assert isinstance(make_request().user_id, uuid.UUID)
