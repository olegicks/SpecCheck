"""Deterministic rule engine: turns a requirement plus an extracted finding into a status.

This module is the *only* place where PASS / FAIL / UNCLEAR is decided. It is pure
(no I/O, no randomness, no LLM) so every decision is reproducible and unit-testable.

Gate order — the first failing gate yields UNCLEAR with a reason:

1. a finding with a value exists
2. the quote was verified on the cited page
3. the agent's confidence is at or above the threshold
4. the value can be parsed and its unit matches the requirement's dimension
5. the value actually appears in the quote (guards against a real quote plus a
   hallucinated number)

Only then is the type-specific comparison applied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core.requirements import Finding, Requirement, RequirementType, Status
from app.core.units import (
    Dimension,
    UnitError,
    extract_numbers,
    extract_quantities,
    format_base,
    is_known_unit,
    lookup_unit,
    make_quantity,
    normalize_symbols,
    word_to_count,
)
from app.core.verification import VerificationResult

DEFAULT_MIN_CONFIDENCE = 0.6
_REL_TOL = 1e-9
_ABS_TOL = 1e-9

_TRUE_WORDS = ("yes", "true", "supported", "present", "available", "qualified", "included")
_FALSE_WORDS = ("no", "false", "not", "none", "unsupported", "absent", "n/a")


@dataclass(frozen=True)
class Decision:
    """Result of evaluating one requirement."""

    status: Status
    reason: str
    found_display: str | None = None
    base_values: tuple[float, ...] = field(default_factory=tuple)


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)


def _le(a: float, b: float) -> bool:
    return a <= b or math.isclose(a, b, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


def _unclear(reason: str, found: str | None = None) -> Decision:
    return Decision(Status.UNCLEAR, reason, found)


def _raw(finding: Finding) -> str:
    """The value as the agent reported it, with its unit (for UNCLEAR results)."""
    return f"{finding.value} {finding.unit or ''}".strip()


def _finding_unit(finding: Finding) -> str | None:
    """Unit from the explicit field, or the first known unit inside the value string."""
    if finding.unit and finding.unit.strip():
        return finding.unit.strip()
    if isinstance(finding.value, str):
        for quantity in extract_quantities(finding.value):
            if quantity.unit:
                return quantity.unit
    return None


def _numbers(value: object) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, int | float):
        return [float(value)]
    if isinstance(value, str):
        return extract_numbers(value)
    return []


def _quote_supports(quote: str, raw: list[float], base: list[float], dim: Dimension) -> bool:
    """True if every extracted number appears in the quote (in any unit of that dimension).

    Bare numbers inherit the next unit in the quote, because datasheet table rows print
    the unit once in the last column ("VDDIO 2700 3300 5500 mV"). This lets the agent
    report the row either as printed (2700 mV) or converted (2.7 V).
    """
    quantities = extract_quantities(quote)
    candidates: list[float] = [q.base_value for q in quantities if q.dimension is dim]
    for i, q in enumerate(quantities):
        if q.dimension is not Dimension.COUNT:
            continue
        unit = next((n.unit for n in quantities[i + 1 :] if n.dimension is dim), None)
        if unit is not None:
            candidates.append(make_quantity(q.value, unit).base_value)
    bare = [q.value for q in quantities if q.dimension is Dimension.COUNT]
    return all(
        any(_close(c, base_value) for c in candidates) or any(_close(b, raw_value) for b in bare)
        for raw_value, base_value in zip(raw, base, strict=True)
    )


def _decide_numeric(requirement: Requirement, finding: Finding) -> Decision:
    params = requirement.parameters
    assert params.unit is not None  # guaranteed by Requirement validation
    req_spec = lookup_unit(params.unit)

    unit = _finding_unit(finding)
    if unit is None:
        return _unclear("Extracted value has no unit", _raw(finding))
    if not is_known_unit(unit):
        return _unclear(f"Unknown unit '{unit}' in extracted value", _raw(finding))
    spec = lookup_unit(unit)
    if spec.dimension is not req_spec.dimension:
        return _unclear(
            f"Unit mismatch: found {spec.dimension} ('{unit}'), "
            f"required {req_spec.dimension} ('{params.unit}')",
            f"{finding.value} {unit}",
        )

    raw = _numbers(finding.value)
    expected = 2 if requirement.type is RequirementType.RANGE else 1
    if len(raw) != expected:
        what = "a min and max value" if expected == 2 else "exactly one value"
        return _unclear(f"Ambiguous value: expected {what}, got {len(raw)}", _raw(finding))

    base = [spec.to_base(v) for v in raw]
    dim = spec.dimension
    found = " … ".join(format_base(b, dim) for b in sorted(base))
    if not _quote_supports(finding.quote or "", raw, base, dim):
        return _unclear("Extracted value does not appear in the verified quote", found)

    match requirement.type:
        case RequirementType.RANGE:
            assert params.min is not None and params.max is not None
            lo, hi = sorted(base)
            req_lo, req_hi = req_spec.to_base(params.min), req_spec.to_base(params.max)
            ok = _le(lo, req_lo) and _le(req_hi, hi)
            verdict = "covers" if ok else "does not cover"
            reason = (
                f"Datasheet range {found} {verdict} required "
                f"{params.min:g} … {params.max:g} {params.unit}"
            )
        case RequirementType.MIN:
            assert params.min is not None
            ok = _le(req_spec.to_base(params.min), base[0])
            reason = f"{found} {'>=' if ok else '<'} required {params.min:g} {params.unit}"
        case RequirementType.MAX:
            assert params.max is not None
            ok = _le(base[0], req_spec.to_base(params.max))
            reason = f"{found} {'<=' if ok else '>'} allowed {params.max:g} {params.unit}"
        case RequirementType.EQUALS:
            assert params.value is not None
            target = req_spec.to_base(params.value)
            tol = req_spec.factor * (params.tolerance or 0.0)
            ok = _le(abs(base[0] - target), tol)
            tol_text = f" ± {params.tolerance:g}" if params.tolerance else ""
            verdict = "matches" if ok else "differs from"
            reason = f"{found} {verdict} required {params.value:g}{tol_text} {params.unit}"
        case _:  # pragma: no cover - other types never reach here
            raise AssertionError(requirement.type)
    return Decision(Status.PASS if ok else Status.FAIL, reason, found, tuple(base))


def _decide_count(requirement: Requirement, finding: Finding) -> Decision:
    required = requirement.parameters.count
    assert required is not None
    value = finding.value
    count: int | None = None
    if isinstance(value, bool):
        count = None
    elif isinstance(value, int | float):
        count = int(value) if float(value).is_integer() else None
    elif isinstance(value, str):
        numbers = [n for n in extract_numbers(value) if n.is_integer()]
        count = int(numbers[0]) if len(numbers) == 1 else word_to_count(value)
    if count is None:
        return _unclear("Could not read an instance count from the extracted value", str(value))

    quote = finding.quote or ""
    in_quote = (
        any(_close(n, count) for n in extract_numbers(quote)) or word_to_count(quote) == count
    )
    if not in_quote:
        return _unclear("Extracted count does not appear in the verified quote", str(count))

    ok = count >= required
    op = ">=" if ok else "<"
    reason = f"{count} × {requirement.parameters.feature} {op} required {required}"
    return Decision(Status.PASS if ok else Status.FAIL, reason, str(count), (float(count),))


def _decide_presence(requirement: Requirement, finding: Finding) -> Decision:
    value = finding.value
    feature = requirement.parameters.feature
    present: bool | None = None
    if isinstance(value, bool):
        present = value
    elif isinstance(value, str):
        text = normalize_symbols(value).strip().lower()
        if text.startswith(_FALSE_WORDS):
            present = False
        elif text.startswith(_TRUE_WORDS) or (feature and feature.lower() in text):
            present = True
    if present is None:
        return _unclear(f"Could not interpret presence value {value!r}", str(value))
    if present:
        return Decision(Status.PASS, f"{feature} is stated in the datasheet", "present")
    return Decision(Status.FAIL, f"Datasheet states {feature} is not present", "not present")


def decide(
    requirement: Requirement,
    finding: Finding | None,
    verification: VerificationResult | None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> Decision:
    """Decide PASS / FAIL / UNCLEAR for one requirement. Pure and deterministic."""
    if finding is None or finding.value is None:
        note = f": {finding.notes}" if finding and finding.notes else ""
        return _unclear(f"No value found in the datasheet{note}")
    if verification is None or not verification.verified:
        why = verification.reason if verification else "not verified"
        return _unclear(f"Quote verification failed ({why})", _raw(finding))
    if finding.confidence < min_confidence:
        return _unclear(
            f"Low confidence {finding.confidence:.2f} < {min_confidence:.2f} — needs review",
            _raw(finding),
        )
    try:
        match requirement.type:
            case RequirementType.MIN_COUNT:
                return _decide_count(requirement, finding)
            case RequirementType.PRESENCE:
                return _decide_presence(requirement, finding)
            case _:
                return _decide_numeric(requirement, finding)
    except UnitError as exc:
        return _unclear(f"Could not parse value: {exc}", _raw(finding))
