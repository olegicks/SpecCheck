"""Keeps parsed datasheets (sample + uploads) available to check runs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.datasheets.pdf import DEFAULT_MAX_BYTES, DEFAULT_MAX_PAGES, ParsedPdf, parse_pdf
from app.datasheets.sample import SAMPLE_FILENAME, SAMPLE_ID, ensure_sample_pdf
from app.datasheets.search import DatasheetIndex, Embedder
from app.datasheets.store import TTLStore


@dataclass
class Datasheet:
    """A parsed, searchable datasheet held in memory."""

    id: str
    filename: str
    data: bytes = field(repr=False)
    parsed: ParsedPdf = field(repr=False)
    index: DatasheetIndex = field(repr=False)
    is_sample: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def page_count(self) -> int:
        return self.parsed.page_count

    def summary(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "page_count": self.page_count,
            "is_sample": self.is_sample,
            "title": self.parsed.title,
        }


class DatasheetRegistry:
    """The built-in sample lives forever; uploads expire after ``ttl_seconds``."""

    def __init__(
        self,
        ttl_seconds: float = 1800,
        max_items: int = 50,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_pages: int = DEFAULT_MAX_PAGES,
        embedder: Embedder | None = None,
    ):
        self._uploads: TTLStore[Datasheet] = TTLStore(ttl_seconds, max_items)
        self._samples: dict[str, Datasheet] = {}
        self._max_bytes = max_bytes
        self._max_pages = max_pages
        self._embedder = embedder

    def _build(self, ident: str, filename: str, data: bytes, is_sample: bool) -> Datasheet:
        parsed = parse_pdf(data, self._max_bytes, self._max_pages)
        index = DatasheetIndex(parsed.pages, embedder=self._embedder)
        return Datasheet(ident, filename, data, parsed, index, is_sample)

    def sample(self) -> Datasheet:
        """The built-in fictional SC-MCU-100 datasheet (parsed once, then cached)."""
        if SAMPLE_ID not in self._samples:
            data = ensure_sample_pdf()
            self._samples[SAMPLE_ID] = self._build(SAMPLE_ID, SAMPLE_FILENAME, data, True)
        return self._samples[SAMPLE_ID]

    def add_upload(self, data: bytes, filename: str) -> Datasheet:
        """Validate and parse an uploaded PDF; raises DatasheetError on bad input."""
        safe_name = (filename or "upload.pdf").replace("\\", "/").rsplit("/", 1)[-1][:120]
        sheet = self._build(f"ds_{uuid.uuid4().hex[:16]}", safe_name, data, False)
        self._uploads.put(sheet.id, sheet)
        return sheet

    def get(self, datasheet_id: str) -> Datasheet | None:
        if datasheet_id == SAMPLE_ID:
            return self.sample()
        return self._uploads.get(datasheet_id)

    def touch(self, datasheet_id: str) -> None:
        self._uploads.touch(datasheet_id)
