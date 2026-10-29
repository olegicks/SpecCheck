"""Regenerate samples/SC-MCU-100_datasheet.pdf.

Usage (from backend/):  python scripts/generate_sample_datasheet.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.datasheets.sample import SAMPLE_PATH, build_sample_pdf


def main() -> None:
    data = build_sample_pdf()
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_PATH.write_bytes(data)
    print(f"Wrote {SAMPLE_PATH} ({len(data) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
