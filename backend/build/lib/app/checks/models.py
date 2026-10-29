"""API-facing models for check runs, results and human overrides."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, computed_field

from app.agent.schemas import AgentEvent
from app.core.requirements import Finding, Requirement, Status
from app.core.verification import VerificationResult


def utcnow() -> datetime:
    return datetime.now(UTC)


class RunState(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class VerificationInfo(BaseModel):
    verified: bool
    method: str
    score: float
    reason: str | None = None

    @classmethod
    def of(cls, v: VerificationResult) -> VerificationInfo:
        return cls(verified=v.verified, method=v.method.value, score=v.score, reason=v.reason)


class Override(BaseModel):
    status: Status
    comment: str
    created_at: datetime = Field(default_factory=utcnow)


class OverrideRequest(BaseModel):
    status: Status
    comment: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=1000),
    ] = Field(description="Mandatory justification for the override")


class RequirementResult(BaseModel):
    """Agent finding + verification + rule decision for one requirement.

    ``agent_status`` is never modified; an override is stored next to it so the
    original automated result stays auditable.
    """

    requirement: Requirement
    finding: Finding | None = None
    verification: VerificationInfo | None = None
    agent_status: Status
    reason: str
    found_display: str | None = None
    override: Override | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> Status:
        return self.override.status if self.override else self.agent_status

    @computed_field  # type: ignore[prop-decorator]
    @property
    def needs_review(self) -> bool:
        return self.override is None and self.agent_status is Status.UNCLEAR


class Summary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    unclear: int = 0
    overridden: int = 0


class CheckRun(BaseModel):
    id: str
    state: RunState = RunState.RUNNING
    mode: str
    model: str
    datasheet: dict
    requirements: list[Requirement]
    results: list[RequirementResult] = Field(default_factory=list)
    stop_reason: str | None = None
    error: str | None = None
    steps: int = 0
    tokens: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    events: list[AgentEvent] = Field(default_factory=list, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summary(self) -> Summary:
        s = Summary(total=len(self.results))
        for r in self.results:
            s.passed += r.status is Status.PASS
            s.failed += r.status is Status.FAIL
            s.unclear += r.status is Status.UNCLEAR
            s.overridden += r.override is not None
        return s

    def result_for(self, requirement_id: str) -> RequirementResult | None:
        return next((r for r in self.results if r.requirement.id == requirement_id), None)


class CheckRequest(BaseModel):
    datasheet_id: str = Field(min_length=1, max_length=64)
    requirements: list[Requirement] = Field(min_length=1, max_length=50)
