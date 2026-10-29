"""OpenAI client tests against a mocked HTTP transport — no network, no real key."""

import json
import logging
import os

import httpx
import pytest

from app.agent.loop import run_agent
from app.agent.openai_client import OpenAIChatClient, make_openai_embedder
from app.agent.schemas import LLMError
from app.agent.tools import TOOL_SCHEMAS
from app.config import LLMMode, load_settings
from app.core.templates import get_template
from app.datasheets.search import DatasheetIndex
from app.logging_utils import REDACTED, RedactingFilter, configure_logging, redact, register_secrets

FAKE_KEY = "sk-test-" + "x" * 40


def completion(message: dict, prompt_tokens: int = 50) -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 5, "total_tokens": 55},
    }


def client_with(handler) -> OpenAIChatClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAIChatClient(FAKE_KEY, model="gpt-4o-mini", max_retries=0, http_client=http)


async def test_maps_tool_calls_and_usage() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_page", "arguments": '{"page_number": 2}'},
                }
            ],
        }
        return httpx.Response(200, json=completion(msg))

    llm = client_with(handler)
    response = await llm.complete([{"role": "user", "content": "hi"}], TOOL_SCHEMAS)

    assert response.tool_calls[0].name == "get_page"
    assert response.tool_calls[0].arguments == '{"page_number": 2}'
    assert response.usage.total_tokens == 55
    assert seen["body"]["model"] == "gpt-4o-mini"
    assert seen["body"]["temperature"] == 0
    assert {t["function"]["name"] for t in seen["body"]["tools"]} == {
        "search_datasheet", "get_page", "extract_parameter", "submit_finding",
    }  # fmt: skip
    assert seen["auth"] == f"Bearer {FAKE_KEY}"


@pytest.mark.parametrize(
    ("status", "text"),
    [
        (401, "rejected the API key"),
        (403, "denied"),
        (404, "model not found"),
        (429, "rate limit"),
        (503, "server error"),
        (418, "API error (418)"),
    ],
)
async def test_http_errors_become_redacted_llm_errors(status: int, text: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"error": {"message": f"Incorrect API key provided: {FAKE_KEY}", "type": "x"}}
        return httpx.Response(status, json=body)

    with pytest.raises(LLMError) as exc:
        await client_with(handler).complete([{"role": "user", "content": "hi"}], [])
    assert text in str(exc.value)
    assert FAKE_KEY not in str(exc.value)
    assert exc.value.__cause__ is None  # original exception (with the key) is not chained


async def test_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(LLMError, match="Could not reach"):
        await client_with(handler).complete([{"role": "user", "content": "hi"}], [])


async def test_no_choices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        data = completion({"role": "assistant", "content": "x"})
        data["choices"] = []
        return httpx.Response(200, json=data)

    with pytest.raises(LLMError, match="no choices"):
        await client_with(handler).complete([{"role": "user", "content": "hi"}], [])


async def test_agent_runs_through_openai_client(sample_parsed) -> None:
    """Full loop through the real client class, with the HTTP layer mocked."""
    req = get_template("vehicle-computer-mcu")[0]
    replies = iter(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "submit_finding",
                            "arguments": json.dumps(
                                {
                                    "requirement_id": req.id,
                                    "value": "-40 to 125",
                                    "unit": "°C",
                                    "page": 5,
                                    "confidence": 0.9,
                                    "notes": None,
                                    "quote": "TA Ambient operating temperature -40 - 125 °C",
                                }
                            ),
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "Done."},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion(next(replies)))

    result = await run_agent(
        client_with(handler), sample_parsed, DatasheetIndex(sample_parsed.pages), [req], "s.pdf"
    )
    assert result.verifications[req.id].verified
    assert result.model == "gpt-4o-mini"


def test_embedder_batches(monkeypatch) -> None:
    calls = []

    class FakeEmbeddings:
        def create(self, model, input):
            calls.append(len(input))
            data = [type("D", (), {"embedding": [1.0, 0.0]}) for _ in input]
            return type("R", (), {"data": data})

    embed = make_openai_embedder(FAKE_KEY)
    monkeypatch.setattr(embed.__closure__[0].cell_contents, "embeddings", FakeEmbeddings())
    vectors = embed(["t"] * 300)
    assert len(vectors) == 300 and calls == [256, 44]


# --- settings & redaction -----------------------------------------------------------


def test_settings_mode_detection(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert load_settings().llm_mode is LLMMode.OFFLINE
    assert load_settings(OPENAI_API_KEY="sk-your-key-here").llm_mode is LLMMode.OFFLINE
    assert load_settings(OPENAI_API_KEY="  ").llm_mode is LLMMode.OFFLINE
    live = load_settings(OPENAI_API_KEY=FAKE_KEY)
    assert live.llm_mode is LLMMode.LIVE
    assert FAKE_KEY not in repr(live) and FAKE_KEY not in str(live.model_dump())
    assert load_settings(OPENAI_API_KEY=FAKE_KEY, SPECCHECK_FORCE_OFFLINE=True).llm_mode is (
        LLMMode.OFFLINE
    )


def test_cors_origins_from_comma_list(monkeypatch) -> None:
    monkeypatch.setenv("SPECCHECK_CORS_ORIGINS", "http://a.test, http://b.test")
    assert load_settings().cors_origins == ["http://a.test", "http://b.test"]


def test_tests_never_load_dotenv() -> None:
    assert os.environ.get("SPECCHECK_DISABLE_DOTENV") == "1"
    assert "OPENAI_API_KEY" not in os.environ


def test_redact_known_and_pattern_secrets() -> None:
    register_secrets(["plain-secret-value-123", ""])
    text = f"key={FAKE_KEY} other=plain-secret-value-123 auth=Bearer abc.def-ghi_jkl"
    out = redact(text)
    assert FAKE_KEY not in out and "plain-secret-value-123" not in out and "abc.def" not in out
    assert out.count(REDACTED) == 3


def test_redacting_filter_on_log_records(caplog) -> None:
    configure_logging()
    configure_logging()  # idempotent
    logger = logging.getLogger("speccheck.test")
    record = logger.makeRecord("x", logging.ERROR, "f", 1, "key %s", (FAKE_KEY,), None)
    RedactingFilter().filter(record)
    assert FAKE_KEY not in record.getMessage()

    try:
        raise RuntimeError(f"failed with {FAKE_KEY}")
    except RuntimeError:
        import sys

        record = logger.makeRecord("x", logging.ERROR, "f", 1, "oops", None, sys.exc_info())
    RedactingFilter().filter(record)
    assert FAKE_KEY not in record.getMessage() and "RuntimeError" in record.getMessage()
