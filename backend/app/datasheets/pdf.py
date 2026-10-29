"""PDF validation, per-page text extraction and page rendering (PyMuPDF)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf

PDF_MAGIC = b"%PDF-"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_PAGES = 80
_HIGHLIGHT_COLOR = (1.0, 0.85, 0.1)


class DatasheetError(ValueError):
    """Raised for invalid, oversized or unreadable PDFs. Messages are user-facing."""


@dataclass(frozen=True)
class ParsedPdf:
    """Text of every page (index 0 = page 1) plus basic metadata."""

    pages: list[str]
    title: str | None

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def page_text(self, page_number: int) -> str | None:
        """Text of a 1-based page number, or None if out of range."""
        if 1 <= page_number <= len(self.pages):
            return self.pages[page_number - 1]
        return None


def validate_pdf_bytes(data: bytes, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    """Reject empty, oversized and non-PDF payloads by size and magic bytes."""
    if not data:
        raise DatasheetError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise DatasheetError(f"File is larger than {max_bytes // (1024 * 1024)} MB.")
    if not data.startswith(PDF_MAGIC):
        raise DatasheetError("File is not a PDF (missing %PDF- header).")


def parse_pdf(
    data: bytes, max_bytes: int = DEFAULT_MAX_BYTES, max_pages: int = DEFAULT_MAX_PAGES
) -> ParsedPdf:
    """Validate a PDF and extract plain text per page."""
    validate_pdf_bytes(data, max_bytes)
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise DatasheetError("The PDF could not be opened (corrupt file?).") from exc
    with doc:
        if doc.needs_pass:
            raise DatasheetError("Password-protected PDFs are not supported.")
        if doc.page_count == 0:
            raise DatasheetError("The PDF has no pages.")
        if doc.page_count > max_pages:
            raise DatasheetError(f"The PDF has {doc.page_count} pages; the limit is {max_pages}.")
        pages = [page.get_text("text", sort=True) for page in doc]
        title = (doc.metadata or {}).get("title") or None
    if not any(p.strip() for p in pages):
        raise DatasheetError(
            "No text could be extracted. Scanned (image-only) PDFs are not supported."
        )
    return ParsedPdf(pages=pages, title=title)


def _highlight_rects(page: pymupdf.Page, quote: str) -> list[pymupdf.Rect]:
    """Find the quote on the page; fall back to searching it in chunks of a few words."""
    quote = re.sub(r"\s+", " ", quote).strip()
    rects = page.search_for(quote)
    if rects:
        return rects
    words = quote.split(" ")
    found: list[pymupdf.Rect] = []
    size = 4
    for start in range(0, len(words), size):
        chunk = " ".join(words[start : start + size])
        if len(chunk) >= 4:
            found.extend(page.search_for(chunk))
    return found


def render_page_png(
    data: bytes, page_number: int, highlight: str | None = None, zoom: float = 1.6
) -> bytes:
    """Render a 1-based page to PNG, optionally highlighting a quote."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if not 1 <= page_number <= doc.page_count:
            raise DatasheetError(f"Page {page_number} does not exist.")
        page = doc[page_number - 1]
        if highlight:
            for rect in _highlight_rects(page, highlight):
                annot = page.add_highlight_annot(rect)
                annot.set_colors(stroke=_HIGHLIGHT_COLOR)
                annot.update()
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pixmap.tobytes("png")
