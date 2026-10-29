"""Import and export of requirement lists as YAML and CSV with readable errors."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from typing import Any

import yaml
from pydantic import ValidationError

from app.core.requirements import Requirement

CSV_COLUMNS = (
    "id", "title", "type", "priority", "min", "max", "value", "tolerance", "unit", "count",
    "feature",
)  # fmt: skip
_PARAM_COLUMNS = ("min", "max", "value", "tolerance", "unit", "count", "feature")
MAX_REQUIREMENTS = 200


class RequirementsImportError(ValueError):
    """Raised with one human-readable message per problem found."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        msg = err["msg"].removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


def validate_requirements(items: Iterable[Any], label: str = "item") -> list[Requirement]:
    """Validate raw dicts into requirements, collecting all errors instead of stopping early."""
    requirements: list[Requirement] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(items, start=1):
        if index > MAX_REQUIREMENTS:
            errors.append(f"too many requirements (max {MAX_REQUIREMENTS})")
            break
        ident = raw.get("id") if isinstance(raw, dict) else None
        where = f"{label} {index}" + (f" ({ident})" if ident else "")
        if not isinstance(raw, dict):
            errors.append(f"{where}: expected a mapping, got {type(raw).__name__}")
            continue
        try:
            req = Requirement.model_validate(raw)
        except ValidationError as exc:
            errors.append(f"{where}: {_format_validation_error(exc)}")
            continue
        if req.id in seen:
            errors.append(f"{where}: duplicate id '{req.id}'")
            continue
        seen.add(req.id)
        requirements.append(req)
    if errors:
        raise RequirementsImportError(errors)
    if not requirements:
        raise RequirementsImportError(["no requirements found"])
    return requirements


def parse_yaml(text: str) -> list[Requirement]:
    """Parse a YAML list of requirements (or a mapping with a ``requirements`` key)."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark else ""
        raise RequirementsImportError([f"invalid YAML{where}"]) from exc
    if isinstance(data, dict) and "requirements" in data:
        data = data["requirements"]
    if not isinstance(data, list):
        raise RequirementsImportError(["YAML must be a list of requirements"])
    return validate_requirements(data, label="item")


def _csv_cell(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def parse_csv(text: str) -> list[Requirement]:
    """Parse CSV with the columns in :data:`CSV_COLUMNS` (header row required)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        raise RequirementsImportError(["CSV is empty"])
    header = [h.strip().lower() for h in reader.fieldnames]
    missing = [c for c in ("id", "title", "type") if c not in header]
    if missing:
        raise RequirementsImportError([f"CSV header is missing column(s): {', '.join(missing)}"])
    unknown = [h for h in header if h not in CSV_COLUMNS]
    if unknown:
        raise RequirementsImportError([f"CSV has unknown column(s): {', '.join(unknown)}"])
    reader.fieldnames = header

    rows: list[dict[str, Any]] = []
    for row in reader:
        cells = {k: _csv_cell(v) for k, v in row.items() if k is not None}
        if not any(cells.values()):
            continue
        item: dict[str, Any] = {k: cells.get(k) for k in ("id", "title", "type")}
        if cells.get("priority"):
            item["priority"] = cells["priority"]
        item["parameters"] = {k: cells[k] for k in _PARAM_COLUMNS if cells.get(k) is not None}
        rows.append(item)
    return validate_requirements(rows, label="row")


def to_yaml(requirements: list[Requirement]) -> str:
    """Serialise requirements to YAML (only non-empty parameters)."""
    data = [r.model_dump(mode="json", exclude_none=True) for r in requirements]
    return yaml.safe_dump({"requirements": data}, sort_keys=False, allow_unicode=True)


def to_csv(requirements: list[Requirement]) -> str:
    """Serialise requirements to CSV with a fixed header."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for r in requirements:
        params = r.parameters.model_dump(exclude_none=True)
        writer.writerow(
            {"id": r.id, "title": r.title, "type": r.type.value, "priority": r.priority.value}
            | {k: (f"{v:g}" if isinstance(v, float) else v) for k, v in params.items()}
        )
    return out.getvalue()
