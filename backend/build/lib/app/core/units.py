"""Unit parsing and normalisation.

Every physical quantity is normalised to one base unit per dimension so that the rule
engine only ever compares like with like:

* temperature -> °C
* voltage     -> V
* frequency   -> Hz
* memory      -> bytes (B)
* count       -> dimensionless

Memory prefixes follow the JEDEC convention used by virtually all semiconductor
datasheets: ``KB``/``kB``/``KiB`` all mean 1024 bytes and ``MB``/``MiB`` mean 1024² bytes.
Using SI (1000) for ``KB`` would make "4096 KB" of flash fail a "4 MB" requirement,
which no hardware engineer would expect.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class Dimension(StrEnum):
    """Physical dimension of a quantity."""

    TEMPERATURE = "temperature"
    VOLTAGE = "voltage"
    FREQUENCY = "frequency"
    MEMORY = "memory"
    COUNT = "count"


class UnitError(ValueError):
    """Raised when a unit or value cannot be parsed."""


@dataclass(frozen=True)
class UnitSpec:
    """How to convert a unit into its dimension's base unit."""

    dimension: Dimension
    factor: float
    offset: float = 0.0

    def to_base(self, value: float) -> float:
        """Convert ``value`` in this unit into the base unit."""
        return value * self.factor + self.offset


_KIB = 1024
_MIB = 1024**2
_GIB = 1024**3

# Keys are lower-cased, whitespace-free unit tokens after unicode normalisation.
_UNITS: dict[str, UnitSpec] = {
    # temperature
    "°c": UnitSpec(Dimension.TEMPERATURE, 1.0),
    "c": UnitSpec(Dimension.TEMPERATURE, 1.0),
    "degc": UnitSpec(Dimension.TEMPERATURE, 1.0),
    "celsius": UnitSpec(Dimension.TEMPERATURE, 1.0),
    "k": UnitSpec(Dimension.TEMPERATURE, 1.0, -273.15),
    "°f": UnitSpec(Dimension.TEMPERATURE, 5 / 9, -32 * 5 / 9),
    # voltage
    "v": UnitSpec(Dimension.VOLTAGE, 1.0),
    "mv": UnitSpec(Dimension.VOLTAGE, 1e-3),
    "μv": UnitSpec(Dimension.VOLTAGE, 1e-6),
    "uv": UnitSpec(Dimension.VOLTAGE, 1e-6),
    "kv": UnitSpec(Dimension.VOLTAGE, 1e3),
    # frequency
    "hz": UnitSpec(Dimension.FREQUENCY, 1.0),
    "khz": UnitSpec(Dimension.FREQUENCY, 1e3),
    "mhz": UnitSpec(Dimension.FREQUENCY, 1e6),
    "ghz": UnitSpec(Dimension.FREQUENCY, 1e9),
    # memory (JEDEC binary prefixes, see module docstring)
    "b": UnitSpec(Dimension.MEMORY, 1),
    "byte": UnitSpec(Dimension.MEMORY, 1),
    "bytes": UnitSpec(Dimension.MEMORY, 1),
    "kb": UnitSpec(Dimension.MEMORY, _KIB),
    "kib": UnitSpec(Dimension.MEMORY, _KIB),
    "kbyte": UnitSpec(Dimension.MEMORY, _KIB),
    "kbytes": UnitSpec(Dimension.MEMORY, _KIB),
    "mb": UnitSpec(Dimension.MEMORY, _MIB),
    "mib": UnitSpec(Dimension.MEMORY, _MIB),
    "mbyte": UnitSpec(Dimension.MEMORY, _MIB),
    "mbytes": UnitSpec(Dimension.MEMORY, _MIB),
    "gb": UnitSpec(Dimension.MEMORY, _GIB),
    "gib": UnitSpec(Dimension.MEMORY, _GIB),
    "kbit": UnitSpec(Dimension.MEMORY, _KIB / 8),
    "mbit": UnitSpec(Dimension.MEMORY, _MIB / 8),
    # count
    "": UnitSpec(Dimension.COUNT, 1),
    "x": UnitSpec(Dimension.COUNT, 1),
    "pcs": UnitSpec(Dimension.COUNT, 1),
}

BASE_UNITS: dict[Dimension, str] = {
    Dimension.TEMPERATURE: "°C",
    Dimension.VOLTAGE: "V",
    Dimension.FREQUENCY: "Hz",
    Dimension.MEMORY: "B",
    Dimension.COUNT: "",
}

_NUMBER_WORDS: dict[str, int] = {
    "one": 1, "single": 1, "two": 2, "dual": 2, "three": 3, "triple": 3, "four": 4,
    "quad": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "octal": 8, "ten": 10,
    "twelve": 12, "sixteen": 16,
}  # fmt: skip

# A sign only counts when it is not glued to a preceding digit, so "3.0-5.5" yields
# 3.0 and 5.5 instead of 3.0 and -5.5.
_NUMBER_RE = re.compile(r"(?<![\d.,])([-+]?)(\d+(?:[.,]\d+)*)")
_QUANTITY_RE = re.compile(
    r"(?<![\w.,])([-+]?)(\d+(?:[.,]\d+)*)\s*(°\s?[cf]|[a-zμ]+)?(?![a-z])", re.IGNORECASE
)


def normalize_symbols(text: str) -> str:
    """Normalise unicode variants of minus signs, degree signs and micro prefixes."""
    # "º" (masculine ordinal) is often typed instead of "°"; NFKC would turn it into "o".
    text = text.replace("º", "°").replace("˚", "°")
    text = unicodedata.normalize("NFKC", text)
    for dash in ("−", "–", "—", "‐", "‑", "‒"):
        text = text.replace(dash, "-")
    return text.replace("µ", "μ")


def unit_key(unit: str) -> str:
    """Return the lookup key for a unit string (lower-case, normalised, no spaces)."""
    return re.sub(r"\s+", "", normalize_symbols(unit or "")).lower()


def lookup_unit(unit: str) -> UnitSpec:
    """Return the :class:`UnitSpec` for ``unit`` or raise :class:`UnitError`."""
    key = unit_key(unit)
    if key not in _UNITS:
        raise UnitError(f"Unknown unit: {unit!r}")
    return _UNITS[key]


def is_known_unit(unit: str) -> bool:
    """Return True if ``unit`` is supported."""
    return unit_key(unit) in _UNITS


def dimension_of(unit: str) -> Dimension:
    """Return the physical dimension of ``unit``."""
    return lookup_unit(unit).dimension


def to_base(value: float, unit: str) -> float:
    """Convert ``value`` given in ``unit`` into the base unit of its dimension."""
    return lookup_unit(unit).to_base(value)


def parse_number(token: str) -> float:
    """Parse one numeric token, accepting decimal commas and thousands separators.

    A comma followed by exactly three digits is a thousands separator ("1,024");
    any other comma is a decimal separator ("3,3").
    """
    token = normalize_symbols(token).strip()
    sign = -1.0 if token.startswith("-") else 1.0
    token = token.lstrip("+-")
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", token):
        token = token.replace(",", "")
    else:
        token = token.replace(",", ".")
    try:
        return sign * float(token)
    except ValueError as exc:
        raise UnitError(f"Not a number: {token!r}") from exc


def extract_numbers(text: str) -> list[float]:
    """Return all numbers in ``text`` in order of appearance."""
    text = normalize_symbols(text)
    return [parse_number(sign + digits) for sign, digits in _NUMBER_RE.findall(text)]


def word_to_count(text: str) -> int | None:
    """Return the count for a number word ("dual" -> 2) found in ``text``, if any."""
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in _NUMBER_WORDS:
            return _NUMBER_WORDS[word]
    return None


@dataclass(frozen=True)
class Quantity:
    """A number with a known unit, normalised to the base unit."""

    value: float
    unit: str
    dimension: Dimension
    base_value: float


def make_quantity(value: float, unit: str) -> Quantity:
    """Build a normalised :class:`Quantity`."""
    spec = lookup_unit(unit)
    return Quantity(value, unit, spec.dimension, spec.to_base(value))


def extract_quantities(text: str) -> list[Quantity]:
    """Find every ``<number> <unit>`` pair in free text.

    Numbers without a recognised unit are returned as dimensionless counts so that
    callers can still match bare numbers (e.g. in table rows where the unit is in a
    header cell).
    """
    text = normalize_symbols(text)
    quantities: list[Quantity] = []
    for sign, digits, unit in _QUANTITY_RE.findall(text):
        value = parse_number(sign + digits)
        unit = unit or ""
        if not is_known_unit(unit):
            unit = ""
        quantities.append(make_quantity(value, unit))
    return quantities


def format_base(value: float, dimension: Dimension) -> str:
    """Human readable rendering of a base value (used in reports)."""
    if dimension is Dimension.MEMORY:
        for unit, factor in (("GB", _GIB), ("MB", _MIB), ("KB", _KIB)):
            if value >= factor and value % factor == 0:
                return f"{value / factor:g} {unit}"
        return f"{value:g} B"
    if dimension is Dimension.FREQUENCY:
        for unit, factor in (("GHz", 1e9), ("MHz", 1e6), ("kHz", 1e3)):
            if abs(value) >= factor:
                return f"{value / factor:g} {unit}"
        return f"{value:g} Hz"
    if dimension is Dimension.COUNT:
        return f"{value:g}"
    return f"{value:g} {BASE_UNITS[dimension]}"
