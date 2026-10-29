"""The agent loop: LLM <-> tools until every requirement has a finding or a budget runs out."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from app.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from app.agent.schemas import AgentEvent, EventType, LLMClient, LLMError, Message, Usage
from app.agent.tools import TOOL_SCHEMAS, BudgetExceeded, ToolArgumentError, ToolExecutor
from app.core.requirements import Finding, Requirement
from app.core.verification import VerificationResult
from app.datasheets.pdf import ParsedPdf
from app.datasheets.search import DatasheetIndex

_ICON_FOR_TOOL = {
    "search_datasheet": EventType.SEARCH,
    "get_page": EventType.READ_PAGE,
    "extract_parameter": EventType.EXTRACT,
    "submit_finding": EventType.SUBMIT,
}


class StopReason(StrEnum):
    COMPLETED = "completed"
    MAX_STEPS = "max_steps"
    TOKEN_BUDGET = "token_budget"
    TIME_BUDGET = "time_budget"
    PAGE_BUDGET = "page_budget"
    INVALID_OUTPUT = "invalid_output"
    MODEL_STOPPED = "model_stopped"
    LLM_ERROR = "llm_error"


@dataclass(frozen=True)
class AgentConfig:
    """Hard limits that cap the cost of a single run."""

    max_steps: int = 40
    max_tokens: int = 150_000
    timeout_seconds: float = 240.0
    max_pages_read: int = 40
    max_invalid_outputs: int = 4
    max_nudges: int = 2
    max_submissions_per_requirement: int = 3


@dataclass
class AgentResult:
    findings: dict[str, Finding]
    verifications: dict[str, VerificationResult]
    stop_reason: StopReason
    steps: int
    usage: Usage
    model: str
    error: str | None = None
    events: list[AgentEvent] = field(default_factory=list)


EventSink = Callable[[AgentEvent], Awaitable[None] | None]


class _Emitter:
    def __init__(self, sink: EventSink | None):
        self._sink = sink
        self._seq = 0
        self.events: list[AgentEvent] = []

    async def __call__(self, event: AgentEvent, step: int | None = None) -> None:
        self._seq += 1
        event.seq = self._seq
        if step is not None and event.step is None:
            event.step = step
        self.events.append(event)
        if self._sink is not None:
            maybe = self._sink(event)
            if asyncio.iscoroutine(maybe):
                await maybe


def _assistant_message(content: str | None, tool_calls: list) -> Message:
    message: Message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in tool_calls
        ]
    return message


async def run_agent(
    llm: LLMClient,
    parsed: ParsedPdf,
    index: DatasheetIndex,
    requirements: list[Requirement],
    filename: str,
    config: AgentConfig | None = None,
    on_event: EventSink | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> AgentResult:
    """Run the extraction agent. Never raises for model misbehaviour; see ``stop_reason``."""
    config = config or AgentConfig()
    emit = _Emitter(on_event)
    executor = ToolExecutor(
        parsed,
        index,
        {r.id: r for r in requirements},
        max_pages_read=config.max_pages_read,
        max_submissions_per_requirement=config.max_submissions_per_requirement,
    )
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(requirements, filename, parsed.page_count)},
    ]
    usage = Usage()
    started = clock()
    invalid_outputs = 0
    nudges = 0
    page_budget_hits = 0
    stop_reason = StopReason.MAX_STEPS
    error: str | None = None
    step = 0

    await emit(
        AgentEvent(
            type=EventType.RUN_STARTED,
            title=f"Agent started ({llm.model})",
            detail=f"{len(requirements)} requirements, {parsed.page_count} pages",
        )
    )

    for step in range(1, config.max_steps + 1):
        remaining = config.timeout_seconds - (clock() - started)
        if remaining <= 0:
            stop_reason = StopReason.TIME_BUDGET
            break
        if usage.total_tokens >= config.max_tokens:
            stop_reason = StopReason.TOKEN_BUDGET
            break

        t0 = clock()
        try:
            response = await asyncio.wait_for(llm.complete(messages, TOOL_SCHEMAS), remaining)
        except TimeoutError:
            stop_reason = StopReason.TIME_BUDGET
            break
        except LLMError as exc:
            stop_reason, error = StopReason.LLM_ERROR, str(exc)
            await emit(
                AgentEvent(type=EventType.ERROR, title="LLM request failed", detail=error), step
            )
            break
        llm_ms = int((clock() - t0) * 1000)
        usage.add(response.usage)
        messages.append(_assistant_message(response.content, response.tool_calls))

        if response.content and response.content.strip():
            await emit(
                AgentEvent(
                    type=EventType.THINKING,
                    title="Model note",
                    detail=response.content.strip()[:500],
                    duration_ms=llm_ms,
                ),
                step,
            )

        if not response.tool_calls:
            missing = executor.missing_requirements
            if not missing:
                stop_reason = StopReason.COMPLETED
                break
            if nudges >= config.max_nudges:
                stop_reason = StopReason.MODEL_STOPPED
                break
            nudges += 1
            messages.append(
                {
                    "role": "user",
                    "content": "You have not submitted findings for: "
                    f"{', '.join(missing)}. Continue with tool calls; submit value null "
                    "if the datasheet does not contain the information.",
                }
            )
            continue

        budget_hit = False
        for call in response.tool_calls:
            t_tool = clock()
            try:
                outcome = executor.execute(call.name, call.arguments)
                result = outcome.result
                for event in outcome.events:
                    if event.duration_ms is None and event.type is _ICON_FOR_TOOL.get(call.name):
                        event.duration_ms = int((clock() - t_tool) * 1000) + llm_ms
                    await emit(event, step)
                llm_ms = 0  # attribute model latency only to the first tool of this step
            except ToolArgumentError as exc:
                invalid_outputs += 1
                result = f"ERROR: {exc} Please retry with valid arguments."
                await emit(
                    AgentEvent(
                        type=EventType.WARNING,
                        title=f"Invalid call to {call.name}",
                        detail=str(exc),
                        data={"retry": invalid_outputs},
                    ),
                    step,
                )
            except BudgetExceeded as exc:
                result = f"ERROR: {exc}. Submit your remaining findings now."
                budget_hit = True
                await emit(
                    AgentEvent(type=EventType.WARNING, title="Budget limit", detail=str(exc)), step
                )
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

        if invalid_outputs > config.max_invalid_outputs:
            stop_reason = StopReason.INVALID_OUTPUT
            error = "Too many invalid tool calls from the model."
            break
        if budget_hit:
            page_budget_hits += 1
            if page_budget_hits > config.max_nudges:
                stop_reason = StopReason.PAGE_BUDGET
                break
        if not executor.missing_requirements and all(
            v.verified for v in executor.verifications.values()
        ):
            stop_reason = StopReason.COMPLETED
            break
    else:
        stop_reason = StopReason.MAX_STEPS

    if stop_reason not in (StopReason.COMPLETED, StopReason.LLM_ERROR):
        missing = executor.missing_requirements
        await emit(
            AgentEvent(
                type=EventType.WARNING,
                title=f"Agent stopped: {stop_reason.value.replace('_', ' ')}",
                detail=(
                    f"No finding for {', '.join(missing)} — marked UNCLEAR."
                    if missing
                    else "All requirements have a finding."
                ),
            ),
            step,
        )

    return AgentResult(
        findings=dict(executor.findings),
        verifications=dict(executor.verifications),
        stop_reason=stop_reason,
        steps=step,
        usage=usage,
        model=llm.model,
        error=error,
        events=emit.events,
    )
