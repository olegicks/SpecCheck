"""Optional live smoke test against the real OpenAI API.

Skipped by default (pytest addopts exclude the ``live`` marker). Run explicitly with:

    $env:SPECCHECK_LIVE_TESTS = "1"; pytest -m live      # PowerShell
    SPECCHECK_LIVE_TESTS=1 pytest -m live                # bash

The key is read from the environment / .env by the app's settings, never from this file.
"""

import os

import pytest

pytestmark = pytest.mark.live


@pytest.mark.skipif(os.environ.get("SPECCHECK_LIVE_TESTS") != "1", reason="live tests disabled")
async def test_live_agent_on_sample(sample_parsed) -> None:
    os.environ.pop("SPECCHECK_DISABLE_DOTENV", None)
    from app.agent.loop import AgentConfig, StopReason, run_agent
    from app.agent.openai_client import OpenAIChatClient
    from app.config import load_settings
    from app.core.templates import get_template
    from app.datasheets.search import DatasheetIndex

    settings = load_settings()
    assert settings.openai_api_key is not None, "OPENAI_API_KEY not configured"
    llm = OpenAIChatClient(settings.openai_api_key.get_secret_value(), settings.openai_model)
    reqs = get_template("vehicle-computer-mcu")[:3]
    result = await run_agent(
        llm, sample_parsed, DatasheetIndex(sample_parsed.pages), reqs, "sample.pdf",
        AgentConfig(max_steps=20),
    )  # fmt: skip
    assert result.stop_reason is StopReason.COMPLETED
    assert set(result.findings) == {r.id for r in reqs}
