import pytest

from app.core.verification import MatchMethod, normalize_text, verify_quote

PAGE = (
    "3.1 Absolute and recommended operating conditions\n"
    "The device operates over the full automo-\ntive temperature range. "
    "TA ambient temperature −40 … +125 °C\n"
    "VDDIO I/O supply 2700 mV to 5500 mV\n"
    "Efﬁcient “low-power” modes are avail­able."
)


def test_normalize_text_handles_unicode_hyphenation_and_whitespace() -> None:
    norm = normalize_text(PAGE)
    assert "automotive temperature" in norm
    assert "-40" in norm
    assert "efficient" in norm  # ligature ﬁ
    assert '"low-power"' in norm  # curly quotes
    assert "available" in norm  # soft hyphen
    assert "  " not in norm


def test_exact_match() -> None:
    result = verify_quote("VDDIO I/O supply 2700 mV to 5500 mV", PAGE)
    assert result.verified and result.method is MatchMethod.EXACT


def test_match_across_line_break_hyphenation() -> None:
    result = verify_quote("operates over the full automotive temperature range", PAGE)
    assert result.verified and result.method is MatchMethod.EXACT


def test_hyphenated_compound_split_across_lines_keeps_hyphen() -> None:
    page = "protected by ECC with single-\nerror correction and double-error detection"
    result = verify_quote("ECC with single-error correction", page)
    assert result.verified and result.method is MatchMethod.EXACT


def test_match_with_ascii_minus_and_different_case() -> None:
    assert verify_quote("ta ambient temperature -40 … +125 °C", PAGE).verified


def test_degree_spacing_is_irrelevant() -> None:
    assert verify_quote("+125°C", PAGE.replace("+125 °C", "+125 °C")).verified


def test_fuzzy_match_tolerates_small_extraction_noise() -> None:
    result = verify_quote("VDDIO I/O suply 2700 mV to 5500 mV", PAGE)
    assert result.verified
    assert result.method is MatchMethod.FUZZY
    assert result.score >= 92


def test_fuzzy_match_never_tolerates_changed_numbers() -> None:
    page = "TA ambient operating temperature: -20 to 85 °C. Some other text follows here."
    result = verify_quote("TA ambient operating temperature: -40 to 125 °C", page)
    assert not result.verified
    assert "numbers differ" in (result.reason or "")


def test_fuzzy_alignment_is_expanded_to_whole_numbers() -> None:
    page = "Program flash size 4096 KB organised in banks"
    assert verify_quote("Program flash sise 4096 KB", page).verified


def test_fabricated_quote_is_rejected() -> None:
    result = verify_quote("VDDIO I/O supply 1800 mV to 3600 mV", PAGE)
    assert not result.verified
    assert "not found" in (result.reason or "")


def test_completely_unrelated_quote_is_rejected() -> None:
    assert not verify_quote("Supports 8 CAN FD controllers with ECC", PAGE).verified


@pytest.mark.parametrize("quote", [None, "", "   "])
def test_empty_quote(quote: str | None) -> None:
    result = verify_quote(quote, PAGE)
    assert not result.verified and result.reason == "no quote provided"


def test_missing_page() -> None:
    assert verify_quote("anything goes here", None).reason == "cited page does not exist"


def test_too_short_quote() -> None:
    assert verify_quote("125", PAGE).reason == "quote too short to verify"
