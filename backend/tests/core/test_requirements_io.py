import pytest
from pydantic import ValidationError

from app.core.requirements import Requirement, RequirementType
from app.core.requirements_io import (
    MAX_REQUIREMENTS,
    RequirementsImportError,
    parse_csv,
    parse_yaml,
    to_csv,
    to_yaml,
)
from app.core.templates import TEMPLATES, get_template


def test_template_is_valid_and_covers_all_types() -> None:
    reqs = get_template("vehicle-computer-mcu")
    assert len(reqs) == len(TEMPLATES["vehicle-computer-mcu"]["requirements"])
    assert {r.type for r in reqs} == set(RequirementType) - {
        RequirementType.MAX,
        RequirementType.EQUALS,
    }


def test_yaml_round_trip() -> None:
    reqs = get_template("vehicle-computer-mcu")
    assert parse_yaml(to_yaml(reqs)) == reqs


def test_csv_round_trip() -> None:
    reqs = get_template("vehicle-computer-mcu")
    assert parse_csv(to_csv(reqs)) == reqs


def test_yaml_plain_list() -> None:
    reqs = parse_yaml(
        "- id: REQ-1\n  title: Clock\n  type: min\n  parameters: {min: 100, unit: MHz}\n"
    )
    assert reqs[0].parameters.min == 100


def test_yaml_syntax_error_reports_line() -> None:
    with pytest.raises(RequirementsImportError, match="line"):
        parse_yaml("- id: REQ-1\n  title: [unclosed\n")


def test_yaml_wrong_shape() -> None:
    with pytest.raises(RequirementsImportError, match="list"):
        parse_yaml("just a string")


def test_yaml_collects_all_errors() -> None:
    text = """
requirements:
  - {id: REQ-1, title: A, type: range, parameters: {min: 1, unit: V}}
  - {id: REQ-2, title: B, type: min, parameters: {min: 1, unit: furlongs}}
  - {id: REQ-2, title: C, type: presence, parameters: {feature: ECC}}
  - {id: REQ-2, title: D, type: presence, parameters: {feature: ECC}}
  - "not a mapping"
"""
    with pytest.raises(RequirementsImportError) as exc:
        parse_yaml(text)
    errors = exc.value.errors
    assert len(errors) == 4
    assert "item 1 (REQ-1)" in errors[0] and "max" in errors[0]
    assert "Unknown unit" in errors[1]
    assert "duplicate id" in errors[2]
    assert "expected a mapping" in errors[3]


def test_empty_list_is_error() -> None:
    with pytest.raises(RequirementsImportError, match="no requirements"):
        parse_yaml("[]")


def test_too_many_requirements() -> None:
    items = "\n".join(
        f"- {{id: REQ-{i}, title: T, type: presence, parameters: {{feature: X}}}}"
        for i in range(MAX_REQUIREMENTS + 1)
    )
    with pytest.raises(RequirementsImportError, match="too many"):
        parse_yaml(items)


def test_csv_with_bom_blank_rows_and_case_insensitive_header() -> None:
    text = "﻿ID,Title,Type,Unit,Min\nREQ-1,Clock,min,MHz,300\n,,,,\n"
    reqs = parse_csv(text)
    assert len(reqs) == 1 and reqs[0].parameters.min == 300


def test_csv_missing_columns() -> None:
    with pytest.raises(RequirementsImportError, match="missing column"):
        parse_csv("id,title\nREQ-1,x\n")


def test_csv_unknown_columns() -> None:
    with pytest.raises(RequirementsImportError, match="unknown column"):
        parse_csv("id,title,type,colour\nREQ-1,x,presence,red\n")


def test_csv_empty() -> None:
    with pytest.raises(RequirementsImportError, match="empty"):
        parse_csv("")


def test_csv_row_errors_use_row_numbers() -> None:
    with pytest.raises(RequirementsImportError, match=r"row 1 \(REQ-1\)"):
        parse_csv("id,title,type,min\nREQ-1,x,min,abc\n")


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"id": "bad id", "title": "x", "type": "presence", "parameters": {"feature": "x"}}, "id"),
        ({"id": "REQ-1", "title": "", "type": "presence", "parameters": {"feature": "x"}}, "title"),
        ({"id": "REQ-1", "title": "x", "type": "unknown"}, "type"),
        ({"id": "REQ-1", "title": "x", "type": "range",
          "parameters": {"min": 5, "max": 1, "unit": "V"}}, "min"),
        ({"id": "REQ-1", "title": "x", "type": "min", "parameters": {"min": 5, "unit": ""}},
         "physical unit"),
        ({"id": "REQ-1", "title": "x", "type": "min_count",
          "parameters": {"count": 0, "feature": "CAN"}}, "count"),
    ],
)  # fmt: skip
def test_requirement_validation(data: dict, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Requirement.model_validate(data)


@pytest.mark.parametrize(
    ("data", "text"),
    [
        ({"type": "range", "parameters": {"min": -40, "max": 125, "unit": "°C"}},
         "must cover -40 … 125 °C"),
        ({"type": "min", "parameters": {"min": 300, "unit": "MHz"}}, ">= 300 MHz"),
        ({"type": "max", "parameters": {"max": 3.6, "unit": "V"}}, "<= 3.6 V"),
        ({"type": "equals", "parameters": {"value": 3.3, "tolerance": 0.1, "unit": "V"}},
         "= 3.3 ± 0.1 V"),
        ({"type": "min_count", "parameters": {"count": 2, "feature": "CAN FD"}}, ">= 2 × CAN FD"),
        ({"type": "presence", "parameters": {"feature": "ECC"}}, "ECC present"),
    ],
)  # fmt: skip
def test_describe(data: dict, text: str) -> None:
    assert Requirement.model_validate({"id": "REQ-1", "title": "x", **data}).describe() == text
