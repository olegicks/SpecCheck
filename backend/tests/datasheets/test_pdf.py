import pymupdf
import pytest

from app.datasheets.pdf import DatasheetError, parse_pdf, render_page_png, validate_pdf_bytes
from app.datasheets.sample import build_sample_pdf
from tests.conftest import make_pdf

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_sample_has_eight_pages_and_title(sample_parsed) -> None:
    assert sample_parsed.page_count == 8
    assert "fictional" in (sample_parsed.title or "").lower()


def test_every_sample_page_is_marked_fictional(sample_parsed) -> None:
    assert all("FICTIONAL SAMPLE" in page for page in sample_parsed.pages)


@pytest.mark.parametrize(
    ("page", "needle"),
    [
        (5, "VDDIO"),
        (5, "2700"),
        (5, "mV"),
        (4, "AEC-Q100 Grade 1"),
        (3, "CAN FD"),
        (7, "512 KB"),
    ],
)
def test_tricky_cases_are_on_expected_pages(sample_parsed, page: int, needle: str) -> None:
    assert needle in sample_parsed.page_text(page)


def test_aec_q100_only_in_footnote(sample_parsed) -> None:
    pages_with_aec = [i for i, t in enumerate(sample_parsed.pages, 1) if "AEC-Q100" in t]
    assert pages_with_aec == [4]


def test_page_text_out_of_range(sample_parsed) -> None:
    assert sample_parsed.page_text(0) is None
    assert sample_parsed.page_text(99) is None


def test_sample_generation_is_deterministic() -> None:
    assert len(build_sample_pdf()) == len(build_sample_pdf())


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "empty"),
        (b"PK\x03\x04 this is a zip", "not a PDF"),
        (b"\x89PNG\r\n\x1a\n", "not a PDF"),
    ],
)
def test_invalid_bytes(data: bytes, message: str) -> None:
    with pytest.raises(DatasheetError, match=message):
        validate_pdf_bytes(data)


def test_too_large() -> None:
    with pytest.raises(DatasheetError, match="larger than"):
        validate_pdf_bytes(b"%PDF-" + b"0" * 2048, max_bytes=1024)


def test_too_many_pages() -> None:
    data = make_pdf(["<p>page</p>"] * 4)
    with pytest.raises(DatasheetError, match="limit is 3"):
        parse_pdf(data, max_pages=3)


def test_corrupt_pdf() -> None:
    with pytest.raises(DatasheetError, match="could not be opened"):
        parse_pdf(b"%PDF-1.7\n garbage garbage")


def test_image_only_pdf_is_rejected() -> None:
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    with pytest.raises(DatasheetError, match="Scanned"):
        parse_pdf(data)


def test_encrypted_pdf_is_rejected() -> None:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    with pytest.raises(DatasheetError, match="Password"):
        parse_pdf(data)


def test_render_page_png(sample_pdf_bytes: bytes) -> None:
    png = render_page_png(sample_pdf_bytes, 1)
    assert png.startswith(PNG_MAGIC)


def test_render_with_highlight_changes_pixels(sample_pdf_bytes: bytes) -> None:
    plain = render_page_png(sample_pdf_bytes, 5)
    highlighted = render_page_png(sample_pdf_bytes, 5, highlight="I/O supply voltage")
    assert highlighted.startswith(PNG_MAGIC) and highlighted != plain


def test_render_highlight_falls_back_to_chunks(sample_pdf_bytes: bytes) -> None:
    plain = render_page_png(sample_pdf_bytes, 5)
    # Words exist on the page but not as one contiguous phrase.
    fuzzy = render_page_png(
        sample_pdf_bytes, 5, highlight="VDDIO I/O supply voltage 2700 3300 5500 mV"
    )
    assert fuzzy != plain


def test_render_missing_page(sample_pdf_bytes: bytes) -> None:
    with pytest.raises(DatasheetError, match="does not exist"):
        render_page_png(sample_pdf_bytes, 42)
