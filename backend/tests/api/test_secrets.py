"""The API key must never appear in responses, events, exports or logs."""

import logging

import httpx

from app.agent.fake_llm import ScriptedLLM, respond, tool_call
from app.agent.schemas import LLMError
from app.logging_utils import redact
from tests.api.conftest import make_settings, run_check

SECRET = "sk-proj-THIS-IS-A-FAKE-TEST-KEY-" + "Z" * 32


async def test_key_never_leaks(app_factory, template_requirements, caplog) -> None:
    caplog.set_level(logging.DEBUG)

    def leaky_llm(_messages):
        # Simulate an SDK error message that echoes the key back.
        raise LLMError(redact(f"Incorrect API key provided: {SECRET}"))

    def crashing_llm(_messages):
        raise RuntimeError(f"connection failed for key {SECRET}")

    factories = iter(
        [
            lambda reqs, ds: ScriptedLLM([leaky_llm]),
            lambda reqs, ds: ScriptedLLM([crashing_llm]),
            lambda reqs, ds: ScriptedLLM(
                [respond(tool_call("search_datasheet", {"query": SECRET}))]
            ),
        ]
    )
    app = app_factory(
        make_settings(OPENAI_API_KEY=SECRET), llm_factory=lambda r, d: next(factories)(r, d)
    )
    bodies: list[str] = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        bodies.append((await c.get("/health")).text)
        bodies.append((await c.get("/openapi.json")).text)
        for _ in range(3):
            check_id = await run_check(c, template_requirements[:1])
            bodies.append((await c.get(f"/api/checks/{check_id}")).text)
            bodies.append((await c.get(f"/api/checks/{check_id}/events")).text)
            for fmt in ("md", "csv", "json"):
                bodies.append((await c.get(f"/api/checks/{check_id}/export?format={fmt}")).text)
        # Validation errors must not echo a key posted by mistake.
        bodies.append(
            (await c.post("/api/checks", json={"datasheet_id": SECRET, "requirements": "x"})).text
        )
        logging.getLogger("speccheck.test").error("key was %s", SECRET)

    leaks = [i for i, body in enumerate(bodies) if SECRET in body]
    assert leaks == [], leaks
    assert "Incorrect API key provided: [REDACTED]" in "".join(bodies)
    assert SECRET not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_dotenv_and_secrets_are_ignored_by_git_and_docker() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    for name in (".gitignore", ".dockerignore"):
        lines = (root / name).read_text(encoding="utf-8").splitlines()
        assert ".env" in lines, f"{name} must ignore .env"
    example = (root / ".env.example").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-your-key-here" in example
