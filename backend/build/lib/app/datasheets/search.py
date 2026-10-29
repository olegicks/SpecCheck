"""Keyword search over datasheet pages using BM25, with optional embedding re-ranking.

Datasheets are full of exact technical tokens ("VDDIO", "AEC-Q100", "CAN FD") where
lexical search beats semantic search, is free, deterministic and needs no API call.
Embeddings can be enabled to re-rank BM25 candidates for paraphrased queries.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.core.units import normalize_symbols

CHUNK_WORDS = 80
CHUNK_OVERLAP = 20
MAX_TOP_K = 10

_TOKEN_RE = re.compile(r"[a-z0-9μ°]+(?:[-./][a-z0-9]+)*")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
    ]
)


def tokenize(text: str) -> list[str]:
    """Lower-case tokens; compound tokens ("aec-q100") also yield their parts."""
    tokens: list[str] = []
    for tok in _TOKEN_RE.findall(normalize_symbols(text).lower()):
        if tok in _STOPWORDS:
            continue
        tokens.append(tok)
        parts = re.split(r"[-./]", tok)
        if len(parts) > 1:
            tokens.extend(p for p in parts if p and p not in _STOPWORDS)
            tokens.append("".join(parts))
    return tokens


@dataclass(frozen=True)
class Chunk:
    page: int
    text: str


@dataclass(frozen=True)
class SearchHit:
    page: int
    text: str
    score: float


def chunk_pages(
    pages: Sequence[str], size: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP
) -> list[Chunk]:
    """Split each page into overlapping word windows so hits point to a small passage."""
    chunks: list[Chunk] = []
    step = max(1, size - overlap)
    for number, text in enumerate(pages, start=1):
        words = text.split()
        if not words:
            continue
        for start in range(0, max(1, len(words) - overlap), step):
            chunks.append(Chunk(number, " ".join(words[start : start + size])))
    return chunks


Embedder = Callable[[list[str]], list[list[float]]]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class DatasheetIndex:
    """BM25 index over page chunks."""

    def __init__(self, pages: Sequence[str], embedder: Embedder | None = None):
        self.chunks = chunk_pages(pages)
        corpus = [tokenize(c.text) for c in self.chunks] or [[""]]
        self._bm25 = BM25Okapi(corpus)
        self._embedder = embedder
        self._chunk_vectors: list[list[float]] | None = None

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        """Return the best-matching chunks, at most one hit per page, best first."""
        top_k = max(1, min(top_k, MAX_TOP_K))
        tokens = tokenize(query)
        if not tokens or not self.chunks:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(self.chunks)), key=lambda i: scores[i], reverse=True)
        candidates = [i for i in ranked if scores[i] > 0][: top_k * 4]
        if self._embedder and candidates:
            candidates = self._rerank(query, candidates)
        hits: list[SearchHit] = []
        seen_pages: set[int] = set()
        for i in candidates:
            chunk = self.chunks[i]
            if chunk.page in seen_pages:
                continue
            seen_pages.add(chunk.page)
            hits.append(SearchHit(chunk.page, chunk.text, round(float(scores[i]), 3)))
            if len(hits) == top_k:
                break
        return hits

    def _rerank(self, query: str, candidates: list[int]) -> list[int]:
        assert self._embedder is not None
        if self._chunk_vectors is None:
            self._chunk_vectors = self._embedder([c.text for c in self.chunks])
        query_vector = self._embedder([query])[0]
        return sorted(
            candidates, key=lambda i: _cosine(query_vector, self._chunk_vectors[i]), reverse=True
        )
