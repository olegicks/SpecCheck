"""Quote verification: does the cited quote really appear on the cited page?

LLMs paraphrase and occasionally invent quotes. Before a finding is allowed to
influence a PASS/FAIL decision we check it against the extracted page text:

1. Normalise both texts (unicode NFKC, dashes, soft hyphens, line-break hyphenation,
   whitespace, case).
2. Exact substring match.
3. Otherwise a strict fuzzy match (``rapidfuzz.fuzz.partial_ratio``) to tolerate
   PDF-extraction noise such as ligatures or table-cell ordering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from rapidfuzz import fuzz

from app.core.units import normalize_symbols

DEFAULT_FUZZY_THRESHOLD = 92.0
MIN_QUOTE_LENGTH = 6


class MatchMethod(StrEnum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    NONE = "none"


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying one quote."""

    verified: bool
    method: MatchMethod
    score: float
    reason: str | None = None


_SOFT_HYPHEN = "­"
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"), None)
_LINEBREAK_HYPHEN_RE = re.compile(r"(\w)-\s*\n\s*(\w)")
_QUOTE_CHARS = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "‚": "'"})


def normalize_text(text: str, keep_linebreak_hyphens: bool = False) -> str:
    """Canonical form used for quote comparison.

    By default words split across lines are joined ("tempera-\\nture" -> "temperature").
    With ``keep_linebreak_hyphens`` the hyphen is kept ("single-\\nerror" -> "single-error"),
    because a line break can also fall inside a genuinely hyphenated compound.
    """
    text = text.replace(_SOFT_HYPHEN, "").translate(_ZERO_WIDTH)
    text = normalize_symbols(text).translate(_QUOTE_CHARS)
    text = _LINEBREAK_HYPHEN_RE.sub(r"\1-\2" if keep_linebreak_hyphens else r"\1\2", text)
    text = re.sub(r"\s+", " ", text)
    # "- 40 °C" and "-40 °C" / "125 °C" and "125°C" should compare equal.
    text = re.sub(r"\s*°\s*", "°", text)
    text = re.sub(r"(?<![\w])-\s+(?=\d)", "-", text)
    return text.strip().casefold()


def verify_quote(
    quote: str | None, page_text: str | None, threshold: float = DEFAULT_FUZZY_THRESHOLD
) -> VerificationResult:
    """Check that ``quote`` appears on ``page_text`` (exactly or with a strict fuzzy match)."""
    if not quote or not quote.strip():
        return VerificationResult(False, MatchMethod.NONE, 0.0, "no quote provided")
    if page_text is None:
        return VerificationResult(False, MatchMethod.NONE, 0.0, "cited page does not exist")

    q = normalize_text(quote).strip(" .\"'…")
    if len(q) < MIN_QUOTE_LENGTH:
        return VerificationResult(False, MatchMethod.NONE, 0.0, "quote too short to verify")
    variants = {normalize_text(page_text), normalize_text(page_text, keep_linebreak_hyphens=True)}
    if any(q in page for page in variants):
        return VerificationResult(True, MatchMethod.EXACT, 100.0)

    best_score = 0.0
    for page in variants:
        alignment = fuzz.partial_ratio_alignment(q, page)
        if alignment is None:
            continue
        score = float(alignment.score)
        best_score = max(best_score, score)
        if score < threshold:
            continue
        segment = _expand_to_words(page, alignment.dest_start, alignment.dest_end)
        if _numbers(q) == _numbers(segment):
            return VerificationResult(True, MatchMethod.FUZZY, score)
        return VerificationResult(
            False,
            MatchMethod.NONE,
            score,
            "quote text matches the page but its numbers differ from the page",
        )
    return VerificationResult(
        False,
        MatchMethod.NONE,
        best_score,
        f"quote not found on cited page (best fuzzy score {best_score:.0f} < {threshold:.0f})",
    )


_DIGITS_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> list[str]:
    """Numeric tokens; fuzzy matching may tolerate typos in words but never in numbers."""
    return _DIGITS_RE.findall(text)


def _expand_to_words(text: str, start: int, end: int) -> str:
    """Grow an aligned slice so it does not cut a word or number in half."""
    while start > 0 and text[start - 1].isalnum():
        start -= 1
    while end < len(text) and text[end].isalnum():
        end += 1
    return text[start:end]
