"""Requirement and finding models shared by the rule engine, agent and API."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.units import Dimension, UnitError, dimension_of, lookup_unit


class RequirementType(StrEnum):
    """Kinds of requirement the rule engine knows how to evaluate."""

    RANGE = "range"  # datasheet range must cover [min, max]
    MIN = "min"  # datasheet value >= min
    MAX = "max"  # datasheet value <= max
    EQUALS = "equals"  # |datasheet value - value| <= tolerance
    MIN_COUNT = "min_count"  # number of instances >= count
    PRESENCE = "presence"  # feature/qualification is present


class Priority(StrEnum):
    MUST = "must"
    SHOULD = "should"


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNCLEAR = "UNCLEAR"


RequirementId = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z][A-Za-z0-9_]*-\d{1,6}$")
]


class RequirementParameters(BaseModel):
    """Type-specific parameters. Which fields are required depends on the type."""

    model_config = ConfigDict(extra="forbid")

    min: float | None = None
    max: float | None = None
    value: float | None = None
    tolerance: float | None = Field(default=None, ge=0)
    unit: str | None = None
    count: int | None = Field(default=None, ge=1)
    feature: str | None = None


_REQUIRED_PARAMS: dict[RequirementType, tuple[str, ...]] = {
    RequirementType.RANGE: ("min", "max", "unit"),
    RequirementType.MIN: ("min", "unit"),
    RequirementType.MAX: ("max", "unit"),
    RequirementType.EQUALS: ("value", "unit"),
    RequirementType.MIN_COUNT: ("count", "feature"),
    RequirementType.PRESENCE: ("feature",),
}


class Requirement(BaseModel):
    """A single hardware requirement to verify against a datasheet."""

    model_config = ConfigDict(extra="forbid")

    id: RequirementId
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    type: RequirementType
    parameters: RequirementParameters = Field(default_factory=RequirementParameters)
    priority: Priority = Priority.MUST

    @model_validator(mode="after")
    def _check_parameters(self) -> Requirement:
        params = self.parameters
        missing = [name for name in _REQUIRED_PARAMS[self.type] if getattr(params, name) is None]
        if missing:
            raise ValueError(f"type '{self.type}' requires parameter(s): {', '.join(missing)}")
        if params.unit is not None and self.type is not RequirementType.MIN_COUNT:
            try:
                lookup_unit(params.unit)
            except UnitError as exc:
                raise ValueError(str(exc)) from exc
            if dimension_of(params.unit) is Dimension.COUNT and self.type in (
                RequirementType.RANGE,
                RequirementType.MIN,
                RequirementType.MAX,
                RequirementType.EQUALS,
            ):
                raise ValueError(f"type '{self.type}' needs a physical unit, e.g. V, °C, MHz, KB")
        if (
            self.type is RequirementType.RANGE
            and params.min is not None
            and params.max is not None
            and params.min > params.max
        ):
            raise ValueError("range parameter 'min' must be <= 'max'")
        return self

    def describe(self) -> str:
        """One-line, human-readable statement of what is required."""
        p = self.parameters
        match self.type:
            case RequirementType.RANGE:
                return f"must cover {p.min:g} … {p.max:g} {p.unit}"
            case RequirementType.MIN:
                return f">= {p.min:g} {p.unit}"
            case RequirementType.MAX:
                return f"<= {p.max:g} {p.unit}"
            case RequirementType.EQUALS:
                tol = f" ± {p.tolerance:g}" if p.tolerance else ""
                return f"= {p.value:g}{tol} {p.unit}"
            case RequirementType.MIN_COUNT:
                return f">= {p.count} × {p.feature}"
            case RequirementType.PRESENCE:
                return f"{p.feature} present"


FindingValue = float | int | bool | str | None


class Finding(BaseModel):
    """What the agent extracted from the datasheet. Deliberately has no status field."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    value: FindingValue = Field(
        default=None,
        description=(
            "Extracted value as printed: a number, a range like '-40 to 125', a count, "
            "true/false for presence, or null if not found."
        ),
    )
    unit: str | None = Field(default=None, max_length=20)
    page: int | None = Field(default=None, ge=1)
    quote: str | None = Field(default=None, max_length=600)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = Field(default=None, max_length=1000)
