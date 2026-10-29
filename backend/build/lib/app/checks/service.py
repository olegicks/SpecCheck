"""Orchestrates a check run: agent extraction -> quote verification -> rule decisions."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable

from app.agent.loop import AgentConfig, run_agent
from app.agent.schemas import AgentEvent, EventType, LLMClient
from app.checks.events import EventBus
from app.checks.models import (
    CheckRun,
    Override,
    OverrideRequest,
    RequirementResult,
    RunState,
    VerificationInfo,
    utcnow,
)
from app.core.requirements import Requirement, Status
from app.core.rules import decide
from app.datasheets.registry import Datasheet, DatasheetRegistry
from app.datasheets.store import TTLStore
from app.logging_utils import redact

log = logging.getLogger(__name__)

LLMFactory = Callable[[list[Requirement], Datasheet], LLMClient]


class CheckNotFound(LookupError):
    pass


class TooManyRuns(RuntimeError):
    pass


def evaluate(
    requirements: list[Requirement],
    findings: dict,
    verifications: dict,
    min_confidence: float,
) -> list[RequirementResult]:
    """Apply the deterministic rule engine to every requirement."""
    results = []
    for req in requirements:
        finding = findings.get(req.id)
        verification = verifications.get(req.id)
        decision = decide(req, finding, verification, min_confidence)
        results.append(
            RequirementResult(
                requirement=req,
                finding=finding,
                verification=VerificationInfo.of(verification) if verification else None,
                agent_status=decision.status,
                reason=decision.reason,
                found_display=decision.found_display,
            )
        )
    return results


class CheckService:
    def __init__(
        self,
        registry: DatasheetRegistry,
        llm_factory: LLMFactory,
        mode: str,
        agent_config: AgentConfig,
        min_confidence: float = 0.6,
        ttl_seconds: float = 7200,
        max_concurrent_runs: int = 4,
    ):
        self._registry = registry
        self._llm_factory = llm_factory
        self._mode = mode
        self._agent_config = agent_config
        self._min_confidence = min_confidence
        self._runs: TTLStore[CheckRun] = TTLStore(ttl_seconds, max_items=500)
        self._buses: TTLStore[EventBus] = TTLStore(ttl_seconds, max_items=500)
        self._max_concurrent = max_concurrent_runs
        self._active = 0
        self._tasks: set[asyncio.Task] = set()

    def get(self, check_id: str) -> CheckRun:
        run = self._runs.get(check_id)
        if run is None:
            raise CheckNotFound(check_id)
        return run

    def bus(self, check_id: str) -> EventBus:
        bus = self._buses.get(check_id)
        if bus is None:
            raise CheckNotFound(check_id)
        return bus

    def start(self, datasheet: Datasheet, requirements: list[Requirement]) -> CheckRun:
        """Create a run and execute it in the background. Raises TooManyRuns."""
        if self._active >= self._max_concurrent:
            raise TooManyRuns("Too many checks are running. Please retry in a moment.")
        llm = self._llm_factory(requirements, datasheet)
        run = CheckRun(
            id=f"chk_{uuid.uuid4().hex[:16]}",
            mode=self._mode,
            model=llm.model,
            datasheet=datasheet.summary(),
            requirements=requirements,
        )
        bus = EventBus()
        self._runs.put(run.id, run)
        self._buses.put(run.id, bus)
        self._active += 1
        task = asyncio.create_task(self._execute(run, bus, datasheet, llm))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    async def wait_all(self) -> None:
        """Await all background runs (used by tests and graceful shutdown)."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _execute(
        self, run: CheckRun, bus: EventBus, datasheet: Datasheet, llm: LLMClient
    ) -> None:
        async def publish(event: AgentEvent) -> None:
            # Model output (e.g. a search query) is echoed into events: scrub secrets.
            event = AgentEvent.model_validate_json(redact(event.model_dump_json()))
            event.seq = len(bus.events) + 1
            run.events.append(event)
            await bus.publish(event)

        try:
            self._registry.touch(datasheet.id)
            result = await run_agent(
                llm,
                datasheet.parsed,
                datasheet.index,
                run.requirements,
                datasheet.filename,
                self._agent_config,
                on_event=publish,
            )
            run.results = evaluate(
                run.requirements, result.findings, result.verifications, self._min_confidence
            )
            run.stop_reason = result.stop_reason.value
            run.error = result.error
            run.steps = result.steps
            run.tokens = result.usage.total_tokens
            for r in run.results:
                await publish(
                    AgentEvent(
                        type=EventType.DECIDE,
                        title=f"{r.requirement.id}: {r.agent_status.value}",
                        detail=r.reason,
                        data={"requirement_id": r.requirement.id, "status": r.agent_status.value},
                    )
                )
            run.state = RunState.COMPLETED
            s = run.summary
            await publish(
                AgentEvent(
                    type=EventType.RUN_COMPLETED,
                    title="Check completed",
                    detail=f"{s.passed} pass · {s.failed} fail · {s.unclear} unclear",
                    data={"state": run.state.value},
                )
            )
        except Exception as exc:  # never let a background task die silently
            log.exception("check run %s failed", run.id)
            run.state = RunState.FAILED
            run.error = redact(f"Internal error: {type(exc).__name__}")
            run.results = evaluate(run.requirements, {}, {}, self._min_confidence)
            await publish(
                AgentEvent(
                    type=EventType.ERROR,
                    title="Check failed",
                    detail=run.error,
                    data={"state": run.state.value},
                )
            )
        finally:
            run.completed_at = utcnow()
            self._active -= 1
            await bus.close()

    def override(
        self, check_id: str, requirement_id: str, request: OverrideRequest
    ) -> RequirementResult:
        run = self.get(check_id)
        result = run.result_for(requirement_id)
        if result is None:
            raise CheckNotFound(requirement_id)
        result.override = Override(status=request.status, comment=request.comment)
        return result

    def clear_override(self, check_id: str, requirement_id: str) -> RequirementResult:
        run = self.get(check_id)
        result = run.result_for(requirement_id)
        if result is None:
            raise CheckNotFound(requirement_id)
        result.override = None
        return result


__all__ = ["CheckNotFound", "CheckService", "Status", "TooManyRuns", "evaluate"]
