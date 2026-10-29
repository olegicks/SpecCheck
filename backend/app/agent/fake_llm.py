"""Deterministic LLM stand-ins.

* :class:`ScriptedLLM` replays a fixed list of responses — used by unit tests.
* :class:`DemoLLM` drives a plausible agent session without any API call — used by
  the end-to-end test and as the "Offline demo" mode when no API key is configured.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import re
from collections.abc import Callable, Sequence
from typing import Any

from app.agent.schemas import LLMResponse, Message, ToolCall, Usage
from app.core.requirements import Requirement

_ids = itertools.count(1)


def tool_call(name: str, arguments: dict[str, Any] | str) -> ToolCall:
    """Build a ToolCall; pass a string to simulate malformed JSON."""
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return ToolCall(id=f"call_{next(_ids)}", name=name, arguments=raw)


def respond(*calls: ToolCall, content: str | None = None, tokens: int = 100) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=list(calls),
        usage=Usage(prompt_tokens=tokens, completion_tokens=10),
    )


ScriptStep = LLMResponse | Callable[[list[Message]], LLMResponse]


class ScriptedLLM:
    """Returns pre-defined responses in order, then a final 'done' message."""

    def __init__(
        self, script: Sequence[ScriptStep], model: str = "scripted-fake", delay: float = 0
    ):
        self.model = model
        self._script = list(script)
        self._delay = delay
        self.calls: list[list[Message]] = []

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        self.calls.append([dict(m) for m in messages])
        if self._delay:
            await asyncio.sleep(self._delay)
        if not self._script:
            return respond(content="Done.")
        step = self._script.pop(0)
        return step(messages) if callable(step) else step


# Facts for the built-in fictional SC-MCU-100 datasheet. Each entry is matched against a
# requirement's title/feature by keywords (most specific first, so "ECC on flash" is ECC),
# and edited thresholds still work in demo mode.
SAMPLE_FACTS: list[tuple[tuple[str, ...], str, dict[str, Any]]] = [
    (("aec",), "AEC-Q100 qualified", {
        "value": True, "unit": None, "page": 4, "confidence": 0.85,
        "quote": 'Devices with the suffix "-Q" are qualified according to AEC-Q100 Grade 1.',
        "notes": "Only stated in footnote 1; applies to -Q devices.",
    }),
    (("ecc",), "ECC error correction flash SRAM", {
        "value": True, "unit": None, "page": 2, "confidence": 0.95,
        "quote": "All flash and SRAM arrays are protected by error correction code (ECC)",
        "notes": None,
    }),
    (("temperature",), "ambient operating temperature TA", {
        "value": "-40 to 125", "unit": "°C", "page": 5, "confidence": 0.95,
        "quote": "TA Ambient operating temperature -40 - 125 °C",
        "notes": "From Table 5-1 (recommended operating conditions).",
    }),
    (("supply", "voltage", "vddio"), "VDDIO I/O supply voltage", {
        "value": "2700 to 5500", "unit": "mV", "page": 5, "confidence": 0.92,
        "quote": "VDDIO I/O supply voltage 2700 3300 5500 mV",
        "notes": "Table 5-1 gives min/typ/max in mV.",
    }),
    (("clock", "frequency", "cpu"), "fCPU CPU clock frequency", {
        "value": 400, "unit": "MHz", "page": 5, "confidence": 0.93,
        "quote": "fCPU CPU clock frequency - - 400 MHz",
        "notes": "Maximum CPU frequency from Table 5-1.",
    }),
    (("flash",), "program flash size", {
        "value": 4096, "unit": "KB", "page": 2, "confidence": 0.95,
        "quote": "Program flash: 4096 KB organised in four banks of 1024 KB",
        "notes": None,
    }),
    (("sram", "ram"), "SRAM size variant", {
        "value": "1", "unit": "MB", "page": 1, "confidence": 0.45,
        "quote": "Up to 1 MB SRAM with ECC, depending on device variant",
        "notes": "Variant dependent: SC-MCU-100A has only 512 KB (Table 7-1, page 7).",
    }),
    (("can",), "CAN FD controllers", {
        "value": 3, "unit": None, "page": 3, "confidence": 0.95,
        "quote": "The device contains 3 CAN FD controllers (MCAN0 to MCAN2).",
        "notes": None,
    }),
    (("ethernet",), "Ethernet MAC 100BASE-T1", {
        "value": 1, "unit": None, "page": 1, "confidence": 0.9,
        "quote": "1 Ethernet MAC (10/100 Mbit/s) with RMII interface for 100BASE-T1 PHYs",
        "notes": None,
    }),
]  # fmt: skip


def _facts_for(requirement: Requirement) -> tuple[str, dict[str, Any]] | None:
    text = f"{requirement.title} {requirement.parameters.feature or ''}".lower()
    words = set(re.findall(r"[a-z0-9]+", text))
    for keywords, query, facts in SAMPLE_FACTS:
        if any(k in words for k in keywords):
            return query, facts
    return None


class DemoLLM:
    """Plays a realistic search -> read -> submit session for each requirement.

    On the built-in sample it submits the known facts; on any other datasheet it
    honestly reports that offline mode cannot extract values.
    """

    model = "offline-demo"

    def __init__(self, requirements: list[Requirement], is_sample: bool, delay: float = 0.25):
        self._plan: list[LLMResponse] = []
        self._delay = delay
        for req in requirements:
            matched = _facts_for(req) if is_sample else None
            query = matched[0] if matched else req.title
            self._plan.append(respond(tool_call("search_datasheet", {"query": query, "top_k": 3})))
            if matched:
                facts = matched[1]
                self._plan.append(respond(tool_call("get_page", {"page_number": facts["page"]})))
                finding = {"requirement_id": req.id, **facts}
            else:
                note = (
                    "Offline demo can only analyse the built-in sample datasheet. "
                    "Configure OPENAI_API_KEY for live extraction."
                    if not is_sample
                    else "Offline demo has no scripted answer for this requirement."
                )
                finding = {
                    "requirement_id": req.id, "value": None, "unit": None, "page": None,
                    "quote": None, "confidence": 0.0, "notes": note,
                }  # fmt: skip
            self._plan.append(respond(tool_call("submit_finding", finding)))
        self._plan.append(respond(content="All requirements have a finding."))

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._plan.pop(0) if self._plan else respond(content="Done.")
