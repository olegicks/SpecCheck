"""End-to-end: full pipeline on the built-in sample datasheet (offline demo agent).

Exercises PDF parsing, BM25 search, the agent loop, quote verification against the
real extracted page text, and the rule engine — everything except the real LLM.
"""

import pytest

from tests.api.conftest import run_check

EXPECTED = {
    "REQ-001": ("PASS", "-40 °C … 125 °C"),  # values only in a table
    "REQ-002": ("PASS", "2.7 V … 5.5 V"),  # given in mV
    "REQ-003": ("PASS", "400 MHz"),
    "REQ-004": ("PASS", "4 MB"),  # 4096 KB == 4 MB (JEDEC)
    "REQ-005": ("UNCLEAR", "1 MB"),  # variant dependent -> low confidence
    "REQ-006": ("FAIL", "3"),  # only 3 CAN FD controllers
    "REQ-007": ("PASS", "1"),
    "REQ-008": ("PASS", "present"),  # only in a footnote
    "REQ-009": ("PASS", "present"),
}


@pytest.fixture
async def sample_run(client, template_requirements) -> dict:
    check_id = await run_check(client, template_requirements)
    return (await client.get(f"/api/checks/{check_id}")).json()


async def test_every_preset_requirement_has_expected_status(sample_run) -> None:
    actual = {
        r["requirement"]["id"]: (r["status"], r["found_display"]) for r in sample_run["results"]
    }
    assert actual == EXPECTED


async def test_every_decided_result_is_traceable(sample_run) -> None:
    for r in sample_run["results"]:
        if r["status"] in ("PASS", "FAIL"):
            assert r["finding"]["page"] >= 1
            assert r["finding"]["quote"]
            assert r["verification"]["verified"] is True


async def test_unclear_result_explains_why(sample_run) -> None:
    sram = next(r for r in sample_run["results"] if r["requirement"]["id"] == "REQ-005")
    assert "Low confidence" in sram["reason"]
    assert "512 KB" in sram["finding"]["notes"]
    assert sram["needs_review"] is True


async def test_changing_a_threshold_changes_only_the_decision(
    client, template_requirements
) -> None:
    """Python decides: the same extracted value flips to FAIL when the requirement is stricter."""
    stricter = [
        {**r, "parameters": {"min": 500, "unit": "MHz"}} if r["id"] == "REQ-003" else r
        for r in template_requirements
    ]
    check_id = await run_check(client, stricter)
    run = (await client.get(f"/api/checks/{check_id}")).json()
    clock = next(r for r in run["results"] if r["requirement"]["id"] == "REQ-003")
    assert clock["status"] == "FAIL" and clock["found_display"] == "400 MHz"
