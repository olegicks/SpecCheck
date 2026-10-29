"""Built-in requirement templates."""

from __future__ import annotations

from app.core.requirements import Requirement

_VEHICLE_COMPUTER_MCU: list[dict] = [
    {
        "id": "REQ-001",
        "title": "Ambient operating temperature",
        "type": "range",
        "parameters": {"min": -40, "max": 125, "unit": "°C"},
        "priority": "must",
    },
    {
        "id": "REQ-002",
        "title": "I/O supply voltage range",
        "type": "range",
        "parameters": {"min": 3.0, "max": 5.5, "unit": "V"},
        "priority": "must",
    },
    {
        "id": "REQ-003",
        "title": "CPU core clock frequency",
        "type": "min",
        "parameters": {"min": 300, "unit": "MHz"},
        "priority": "must",
    },
    {
        "id": "REQ-004",
        "title": "Embedded program flash",
        "type": "min",
        "parameters": {"min": 4, "unit": "MB"},
        "priority": "must",
    },
    {
        "id": "REQ-005",
        "title": "On-chip SRAM",
        "type": "min",
        "parameters": {"min": 1, "unit": "MB"},
        "priority": "must",
    },
    {
        "id": "REQ-006",
        "title": "CAN FD interfaces",
        "type": "min_count",
        "parameters": {"count": 4, "feature": "CAN FD controller"},
        "priority": "must",
    },
    {
        "id": "REQ-007",
        "title": "Automotive Ethernet (100BASE-T1 capable MAC)",
        "type": "min_count",
        "parameters": {"count": 1, "feature": "Ethernet MAC"},
        "priority": "should",
    },
    {
        "id": "REQ-008",
        "title": "AEC-Q100 qualification",
        "type": "presence",
        "parameters": {"feature": "AEC-Q100"},
        "priority": "must",
    },
    {
        "id": "REQ-009",
        "title": "ECC on flash and SRAM",
        "type": "presence",
        "parameters": {"feature": "ECC"},
        "priority": "should",
    },
]

TEMPLATES: dict[str, dict] = {
    "vehicle-computer-mcu": {
        "name": "Vehicle Computer MCU",
        "description": "Typical requirements for an MCU in an automotive vehicle computer.",
        "requirements": _VEHICLE_COMPUTER_MCU,
    }
}


def get_template(template_id: str) -> list[Requirement]:
    """Return validated requirements for a template, or raise KeyError."""
    return [Requirement.model_validate(r) for r in TEMPLATES[template_id]["requirements"]]
