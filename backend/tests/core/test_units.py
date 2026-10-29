import pytest

from app.core.units import (
    Dimension,
    UnitError,
    dimension_of,
    extract_numbers,
    extract_quantities,
    format_base,
    is_known_unit,
    parse_number,
    to_base,
    word_to_count,
)


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (125, "°C", 125),
        (125, "℃", 125),
        (125, "degC", 125),
        (125, "º C", 125),
        (273.15, "K", 0),
        (212, "°F", 100),
        (3.3, "V", 3.3),
        (3300, "mV", 3.3),
        (500, "µV", 0.0005),
        (400, "MHz", 400e6),
        (32, "kHz", 32e3),
        (1.2, "GHz", 1.2e9),
        (1, "KB", 1024),
        (1, "kB", 1024),
        (1, "KiB", 1024),
        (4, "MB", 4 * 1024**2),
        (4096, "KB", 4 * 1024**2),
        (8, "Mbit", 1024**2),
        (3, "", 3),
    ],
)
def test_to_base(value: float, unit: str, expected: float) -> None:
    assert to_base(value, unit) == pytest.approx(expected)


def test_kb_and_mb_are_binary_so_4096_kb_equals_4_mb() -> None:
    assert to_base(4096, "KB") == to_base(4, "MB")


def test_unknown_unit_raises() -> None:
    with pytest.raises(UnitError):
        to_base(1, "furlong")
    assert not is_known_unit("parsec")


def test_dimension_of() -> None:
    assert dimension_of("mV") is Dimension.VOLTAGE
    assert dimension_of("GHz") is Dimension.FREQUENCY
    assert dimension_of("KiB") is Dimension.MEMORY
    assert dimension_of("°C") is Dimension.TEMPERATURE


@pytest.mark.parametrize(
    ("token", "expected"),
    [("3.3", 3.3), ("3,3", 3.3), ("1,024", 1024), ("−40", -40), ("+125", 125), ("1,024.5", 1024.5)],
)
def test_parse_number(token: str, expected: float) -> None:
    assert parse_number(token) == pytest.approx(expected)


def test_parse_number_rejects_garbage() -> None:
    with pytest.raises(UnitError):
        parse_number("abc")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("-40 to +125", [-40, 125]),
        ("−40 … +125 °C", [-40, 125]),
        ("3.0-5.5 V", [3.0, 5.5]),
        ("2700 mV to 5500 mV", [2700, 5500]),
        ("TA = –40 °C", [-40]),
        ("no numbers", []),
    ],
)
def test_extract_numbers(text: str, expected: list[float]) -> None:
    assert extract_numbers(text) == pytest.approx(expected)


def test_extract_quantities_pairs_numbers_with_units() -> None:
    qs = extract_quantities("VDDIO 2700 mV to 5.5V, 400MHz, 3 channels, 125 °C")
    assert [(q.value, q.unit) for q in qs] == [
        (2700, "mV"),
        (5.5, "V"),
        (400, "MHz"),
        (3, ""),
        (125, "°C"),
    ]
    assert qs[0].base_value == pytest.approx(2.7)


def test_word_to_count() -> None:
    assert word_to_count("Dual CAN FD") == 2
    assert word_to_count("three controllers") == 3
    assert word_to_count("CAN FD") is None


@pytest.mark.parametrize(
    ("value", "dim", "expected"),
    [
        (4 * 1024**2, Dimension.MEMORY, "4 MB"),
        (512 * 1024, Dimension.MEMORY, "512 KB"),
        (100, Dimension.MEMORY, "100 B"),
        (2 * 1024**3, Dimension.MEMORY, "2 GB"),
        (400e6, Dimension.FREQUENCY, "400 MHz"),
        (1.2e9, Dimension.FREQUENCY, "1.2 GHz"),
        (32e3, Dimension.FREQUENCY, "32 kHz"),
        (50, Dimension.FREQUENCY, "50 Hz"),
        (3.3, Dimension.VOLTAGE, "3.3 V"),
        (-40, Dimension.TEMPERATURE, "-40 °C"),
        (4, Dimension.COUNT, "4"),
    ],
)
def test_format_base(value: float, dim: Dimension, expected: str) -> None:
    assert format_base(value, dim) == expected
