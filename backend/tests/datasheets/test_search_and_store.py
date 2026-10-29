import pytest

from app.datasheets.pdf import DatasheetError
from app.datasheets.registry import DatasheetRegistry
from app.datasheets.sample import SAMPLE_ID
from app.datasheets.search import DatasheetIndex, chunk_pages, tokenize
from app.datasheets.store import TTLStore


def test_tokenize_splits_compounds_and_drops_stopwords() -> None:
    tokens = tokenize("The AEC-Q100 qualification of CAN-FD")
    assert "aec-q100" in tokens and "aec" in tokens and "q100" in tokens and "aecq100" in tokens
    assert "the" not in tokens and "of" not in tokens


def test_chunk_pages_overlaps_and_keeps_page_numbers() -> None:
    words = " ".join(f"w{i}" for i in range(200))
    chunks = chunk_pages(["", words], size=80, overlap=20)
    assert {c.page for c in chunks} == {2}
    assert chunks[0].text.split()[-1] == "w79"
    assert chunks[1].text.split()[0] == "w60"


@pytest.mark.parametrize(
    ("query", "page"),
    [
        ("ambient operating temperature", 5),
        ("VDDIO I/O supply voltage", 5),
        ("AEC-Q100 qualification", 4),
        ("CAN FD controllers", 3),
        ("part number SRAM flash package grade", 7),
    ],
)
def test_bm25_finds_expected_page(sample_parsed, query: str, page: int) -> None:
    index = DatasheetIndex(sample_parsed.pages)
    hits = index.search(query, top_k=3)
    assert hits and hits[0].page == page


def test_search_returns_one_hit_per_page_and_respects_top_k(sample_parsed) -> None:
    hits = DatasheetIndex(sample_parsed.pages).search("SC-MCU-100 fictional", top_k=4)
    assert len(hits) <= 4
    assert len({h.page for h in hits}) == len(hits)
    assert hits == sorted(hits, key=lambda h: h.score, reverse=True)


def test_search_edge_cases(sample_parsed) -> None:
    index = DatasheetIndex(sample_parsed.pages)
    assert index.search("") == []
    assert index.search("xylophone zebra") == []
    assert len(index.search("temperature", top_k=999)) <= 10


def test_empty_index() -> None:
    assert DatasheetIndex([""]).search("anything") == []


def test_embedding_rerank_reorders_candidates() -> None:
    pages = ["frequency frequency clock", "speed maximum", "unrelated text", "more words"]

    def embedder(texts: list[str]) -> list[list[float]]:
        # Pretend page 2 is semantically closest to the query.
        return [[1.0, 0.0] if "speed" in t else [0.0, 1.0] for t in texts]

    plain = DatasheetIndex(pages).search("frequency speed", top_k=2)
    reranked = DatasheetIndex(pages, embedder=embedder).search("frequency speed", top_k=2)
    assert plain[0].page == 1
    assert reranked[0].page == 2


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_ttl_store_expiry_touch_and_eviction() -> None:
    clock = FakeClock()
    store: TTLStore[int] = TTLStore(ttl_seconds=10, max_items=2, clock=clock)
    store.put("a", 1)
    clock.now = 5
    store.touch("a")
    store.touch("missing")
    clock.now = 12
    assert store.get("a") == 1  # touched at t=5, expires at t=15
    clock.now = 16
    assert store.get("a") is None
    store.put("b", 2)
    store.put("c", 3)
    store.put("d", 4)
    assert store.get("b") is None and len(store) == 2
    assert store.get("nope") is None


def test_registry_sample_is_cached(registry: DatasheetRegistry) -> None:
    first = registry.get(SAMPLE_ID)
    assert first is registry.sample()
    assert first.page_count == 8 and first.is_sample
    assert first.summary()["filename"].endswith(".pdf")


def test_registry_upload(registry: DatasheetRegistry, sample_pdf_bytes: bytes) -> None:
    sheet = registry.add_upload(sample_pdf_bytes, "C:\\fakepath\\my datasheet.pdf")
    assert sheet.filename == "my datasheet.pdf"
    assert registry.get(sheet.id) is sheet
    registry.touch(sheet.id)
    assert registry.get("ds_unknown") is None


def test_registry_rejects_bad_upload(registry: DatasheetRegistry) -> None:
    with pytest.raises(DatasheetError):
        registry.add_upload(b"not a pdf", "x.pdf")
