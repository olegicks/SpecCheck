import pytest

from app.core.requirements import Finding, Requirement, Status
from app.core.rules import decide
from app.core.verification import MatchMethod, VerificationResult

OK = VerificationResult(True, MatchMethod.EXACT, 100.0)
BAD = VerificationResult(False, MatchMethod.NONE, 40.0, "quote not found on cited page")


def req(type_: str, **params: object) -> Requirement:
    return Requirement(id="REQ-001", title="t", type=type_, parameters=params)


def finding(value: object, unit: str | None = None, quote: str = "", conf: float = 0.9) -> Finding:
    return Finding(
        requirement_id="REQ-001", value=value, unit=unit, page=1, quote=quote, confidence=conf
    )


# --- range -------------------------------------------------------------------

TEMP = req("range", min=-40, max=125, unit="°C")


@pytest.mark.parametrize(
    ("value", "quote", "status"),
    [
        ("-40 to 125", "TA -40 … +125 °C", Status.PASS),
        ("-40 to 150", "TJ -40 to 150 °C", Status.PASS),
        ("-40 to 105", "TA -40 to +105 °C", Status.FAIL),
        ("-20 to 125", "TA -20 to 125 °C", Status.FAIL),
        ("125 to -40", "TA -40 … +125 °C", Status.PASS),  # order does not matter
    ],
)
def test_range(value: str, quote: str, status: Status) -> None:
    assert decide(TEMP, finding(value, "°C", quote), OK).status is status


def test_range_converts_units_mv_to_v() -> None:
    r = req("range", min=3.0, max=5.5, unit="V")
    f = finding("2700 to 5500", "mV", "VDDIO 2700 mV to 5500 mV")
    d = decide(r, f, OK)
    assert d.status is Status.PASS
    assert d.found_display == "2.7 V … 5.5 V"


def test_range_needs_two_numbers() -> None:
    d = decide(TEMP, finding("125", "°C", "up to 125 °C"), OK)
    assert d.status is Status.UNCLEAR and "Ambiguous" in d.reason


# --- min / max / equals --------------------------------------------------------


def test_min_pass_and_fail() -> None:
    r = req("min", min=300, unit="MHz")
    assert decide(r, finding(400, "MHz", "up to 400 MHz"), OK).status is Status.PASS
    assert decide(r, finding(300, "MHz", "300 MHz"), OK).status is Status.PASS  # boundary
    assert decide(r, finding(250, "MHz", "250 MHz"), OK).status is Status.FAIL


def test_min_with_kb_vs_mb() -> None:
    r = req("min", min=4, unit="MB")
    assert decide(r, finding(4096, "KB", "4096 KB program flash"), OK).status is Status.PASS
    assert decide(r, finding("2 MB", None, "2 MB program flash"), OK).status is Status.FAIL


def test_max() -> None:
    r = req("max", max=3.6, unit="V")
    assert decide(r, finding(3.3, "V", "VDD 3.3 V"), OK).status is Status.PASS
    assert decide(r, finding(5000, "mV", "VDD 5000 mV"), OK).status is Status.FAIL


def test_equals_with_tolerance() -> None:
    r = req("equals", value=3.3, tolerance=0.1, unit="V")
    assert decide(r, finding(3300, "mV", "3300 mV"), OK).status is Status.PASS
    assert decide(r, finding(3.35, "V", "3.35 V"), OK).status is Status.PASS
    assert decide(r, finding(3.6, "V", "3.6 V"), OK).status is Status.FAIL


def test_equals_exact() -> None:
    r = req("equals", value=400, unit="MHz")
    assert decide(r, finding(0.4, "GHz", "0.4 GHz core"), OK).status is Status.PASS


def test_quote_in_other_unit_still_supports_value() -> None:
    r = req("min", min=3, unit="V")
    d = decide(r, finding(3.3, "V", "VDD = 3300 mV"), OK)
    assert d.status is Status.PASS


def test_table_quote_with_unit_in_header_supports_bare_number() -> None:
    d = decide(TEMP, finding("-40 to 125", "°C", "TA Ambient temperature -40 125"), OK)
    assert d.status is Status.PASS


def test_unit_mismatch_is_unclear() -> None:
    r = req("min", min=300, unit="MHz")
    d = decide(r, finding(400, "V", "400 V"), OK)
    assert d.status is Status.UNCLEAR and "Unit mismatch" in d.reason


def test_unit_from_value_string() -> None:
    r = req("min", min=300, unit="MHz")
    assert decide(r, finding("400 MHz", None, "400 MHz"), OK).status is Status.PASS


def test_missing_unit_is_unclear() -> None:
    r = req("min", min=300, unit="MHz")
    assert "no unit" in decide(r, finding(400, None, "400"), OK).reason


def test_unknown_unit_is_unclear() -> None:
    r = req("min", min=300, unit="MHz")
    assert "Unknown unit" in decide(r, finding(400, "rpm", "400 rpm"), OK).reason


def test_several_values_for_min_is_unclear() -> None:
    r = req("min", min=1, unit="MB")
    d = decide(r, finding("512 KB or 1 MB", None, "512 KB or 1 MB depending on variant"), OK)
    assert d.status is Status.UNCLEAR and "Ambiguous" in d.reason


def test_hallucinated_value_not_in_quote_is_unclear() -> None:
    r = req("min", min=300, unit="MHz")
    d = decide(r, finding(500, "MHz", "CPU runs at up to 400 MHz"), OK)
    assert d.status is Status.UNCLEAR and "does not appear" in d.reason


def test_boolean_value_for_numeric_requirement_is_unclear() -> None:
    r = req("min", min=300, unit="MHz")
    assert decide(r, finding(True, "MHz", "400 MHz"), OK).status is Status.UNCLEAR


# --- min_count ------------------------------------------------------------------

CAN = req("min_count", count=4, feature="CAN FD controller")


@pytest.mark.parametrize(
    ("value", "quote", "status"),
    [
        (4, "4x CAN FD controllers", Status.PASS),
        ("6", "6 CAN FD controllers", Status.PASS),
        (3, "3 CAN FD controllers (MCAN0..MCAN2)", Status.FAIL),
        ("dual", "dual CAN FD", Status.FAIL),
    ],
)
def test_min_count(value: object, quote: str, status: Status) -> None:
    assert decide(CAN, finding(value, None, quote), OK).status is status


def test_min_count_value_must_be_in_quote() -> None:
    d = decide(CAN, finding(4, None, "3 CAN FD controllers"), OK)
    assert d.status is Status.UNCLEAR


@pytest.mark.parametrize("value", [2.5, True, "several"])
def test_min_count_unreadable(value: object) -> None:
    assert decide(CAN, finding(value, None, "several CAN FD controllers"), OK).status is (
        Status.UNCLEAR
    )


# --- presence --------------------------------------------------------------------

AEC = req("presence", feature="AEC-Q100")


@pytest.mark.parametrize(
    ("value", "status"),
    [
        (True, Status.PASS),
        ("yes", Status.PASS),
        ("AEC-Q100 Grade 1", Status.PASS),
        (False, Status.FAIL),
        ("not qualified", Status.FAIL),
        ("maybe", Status.UNCLEAR),
        (3, Status.UNCLEAR),
    ],
)
def test_presence(value: object, status: Status) -> None:
    assert decide(AEC, finding(value, None, "Qualified according to AEC-Q100"), OK).status is (
        status
    )


# --- gates -------------------------------------------------------------------------


def test_no_finding_is_unclear() -> None:
    assert decide(TEMP, None, None).status is Status.UNCLEAR


def test_null_value_is_unclear_and_keeps_notes() -> None:
    f = Finding(requirement_id="REQ-001", value=None, confidence=0.2, notes="not mentioned")
    d = decide(TEMP, f, None)
    assert d.status is Status.UNCLEAR and "not mentioned" in d.reason


def test_failed_verification_is_unclear_even_if_value_would_pass() -> None:
    d = decide(TEMP, finding("-40 to 125", "°C", "TA -40 … +125 °C"), BAD)
    assert d.status is Status.UNCLEAR and "verification failed" in d.reason


def test_missing_verification_is_unclear() -> None:
    assert decide(TEMP, finding("-40 to 125", "°C", "x"), None).status is Status.UNCLEAR


def test_low_confidence_is_unclear() -> None:
    d = decide(TEMP, finding("-40 to 125", "°C", "TA -40 … +125 °C", conf=0.5), OK)
    assert d.status is Status.UNCLEAR and "Low confidence" in d.reason


def test_confidence_threshold_is_configurable() -> None:
    f = finding("-40 to 125", "°C", "TA -40 … +125 °C", conf=0.5)
    assert decide(TEMP, f, OK, min_confidence=0.4).status is Status.PASS


def test_decide_is_deterministic() -> None:
    f = finding("-40 to 125", "°C", "TA -40 … +125 °C")
    assert {decide(TEMP, f, OK) for _ in range(5)} == {decide(TEMP, f, OK)}
