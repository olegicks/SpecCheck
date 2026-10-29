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


def normalize_text(text: str) -> str:
    """Canonical form used for quote comparison."""
    text = text.replace(_SOFT_HYPHEN, "").translate(_ZERO_WIDTH)
    text = normalize_symbols(text).translate(_QUOTE_CHARS)
    # Join words split across lines: "tempera-\nture" -> "temperature".
    text = _LINEBREAK_HYPHEN_RE.sub(r"\1\2", text)
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
    page = normalize_text(page_text)
    if len(q) < MIN_QUOTE_LENGTH:
        return VerificationResult(False, MatchMethod.NONE, 0.0, "quote too short to verify")
    if q in page:
        return VerificationResult(True, MatchMethod.EXACT, 100.0)

    score = float(fuzz.partial_ratio(q, page))
    if score >= threshold:
        return VerificationResult(True, MatchMethod.FUZZY, score)
    return VerificationResult(
        False,
        MatchMethod.NONE,
        score,
        f"quote not found on cited page (best fuzzy score {score:.0f} < {threshold:.0f})",
    )
