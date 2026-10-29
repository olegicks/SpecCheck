"""Shared fixtures. Tests never talk to the real OpenAI API."""

from __future__ import annotations

import os

import pytest

# Make sure no test can accidentally pick up a developer's real key from .env.
os.environ["SPECCHECK_DISABLE_DOTENV"] = "1"
os.environ.pop("OPENAI_API_KEY", None)

from app.datasheets.pdf import ParsedPdf, parse_pdf
from app.datasheets.registry import DatasheetRegistry
from app.datasheets.sample import build_sample_pdf, ensure_sample_pdf


@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    return ensure_sample_pdf()


@pytest.fixture(scope="session")
def sample_parsed(sample_pdf_bytes: bytes) -> ParsedPdf:
    return parse_pdf(sample_pdf_bytes)


@pytest.fixture
def registry() -> DatasheetRegistry:
    return DatasheetRegistry()


def make_pdf(pages: list[str]) -> bytes:
    """Build a small PDF from HTML snippets (one per page)."""
    return build_sample_pdf(pages)
