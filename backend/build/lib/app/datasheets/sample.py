"""Generator for the fictional "SC-MCU-100" automotive MCU datasheet.

The document is intentionally tricky so the agent and the rule engine are exercised
on realistic problems:

* operating temperature and fCPU appear *only* in a table (REQ-001, REQ-003)
* the I/O supply is given in **mV** (REQ-002)
* flash is given as **4096 KB** while the requirement says 4 MB (REQ-004)
* SRAM size depends on the ordering variant -> genuinely **ambiguous** (REQ-005)
* only **3** CAN FD controllers -> a genuine **FAIL** against ">= 4" (REQ-006)
* AEC-Q100 is mentioned *only in a footnote* (REQ-008)

Everything is fictional and every page says so.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

SAMPLE_ID = "sc-mcu-100"
SAMPLE_FILENAME = "SC-MCU-100_datasheet.pdf"
SAMPLE_PATH = Path(__file__).resolve().parents[2] / "samples" / SAMPLE_FILENAME

_PAGE = pymupdf.paper_rect("a4")
_MARGIN = 56
_FOOTER = "FICTIONAL SAMPLE — SC-MCU-100 is not a real product. Created for software demonstration."

_CSS = """
* { font-family: sans-serif; }
body { font-size: 10pt; color: #1f2937; line-height: 1.4; }
h1 { font-size: 22pt; color: #0f3d5e; margin: 0 0 4pt 0; }
h2 { font-size: 13pt; color: #0f3d5e; margin: 14pt 0 6pt 0; }
h3 { font-size: 11pt; margin: 10pt 0 4pt 0; }
p { margin: 0 0 6pt 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt 0; }
th { background-color: #dbe7f0; text-align: left; }
th, td { border: 1px solid #94a3b8; padding: 3pt 5pt; font-size: 9pt; }
.note { font-size: 8pt; color: #475569; }
.banner { border: 1px solid #b45309; background-color: #fef3c7; padding: 6pt; color: #78350f; }
.sub { font-size: 12pt; color: #475569; }
"""

_PAGES: list[str] = [
    # 1 — cover
    """
<h1>SC-MCU-100 Series</h1>
<p class="sub">32-bit Automotive Microcontroller for Vehicle Computers and Zone Controllers</p>
<p class="sub">Datasheet — Revision 1.2</p>
<div class="banner"><b>Fictional document.</b> The SC-MCU-100 is a fictional device invented
for demonstrating the SpecCheck datasheet verification tool. Any resemblance to real
products is coincidental. Do not use for design decisions.</div>
<h2>1 Key features</h2>
<ul>
<li>Dual-core lockstep 32-bit RISC CPU with floating point unit</li>
<li>4096 KB embedded program flash with ECC (SEC-DED)</li>
<li>Up to 1 MB SRAM with ECC, depending on device variant (see Table 7-1)</li>
<li>3 CAN FD controllers compliant with ISO 11898-1:2015</li>
<li>1 Ethernet MAC (10/100 Mbit/s) with RMII interface for 100BASE-T1 PHYs</li>
<li>Hardware security module with AES-128/256 and true random number generator</li>
<li>Functional safety: designed for ISO 26262 ASIL-B applications</li>
<li>Packages: LQFP-144 and BGA-292</li>
</ul>
""",
    # 2 — overview
    """
<h2>2 Device overview</h2>
<p>The SC-MCU-100 integrates two CPU cores in lockstep, a crossbar interconnect,
embedded memories and a rich set of automotive communication peripherals. The device
targets body control, gateway and zone-controller functions inside a vehicle computer
architecture.</p>
<h3>2.1 CPU subsystem</h3>
<p>The CPU subsystem consists of a primary core and a checker core executing the same
instruction stream with a two-cycle delay. Mismatches are reported to the fault
collection unit. The maximum CPU frequency is specified in the electrical
characteristics (Table 5-1).</p>
<h3>2.2 Memory subsystem</h3>
<p>Program flash: 4096 KB organised in four banks of 1024 KB, read-while-write capable.
All flash and SRAM arrays are protected by error correction code (ECC) with single-error
correction and double-error detection.</p>
<p>The SRAM size depends on the device variant. Refer to the ordering information in
Section 7 for the memory configuration of each part number.</p>
""",
    # 3 — communication interfaces
    """
<h2>3 Communication interfaces</h2>
<table>
<tr><th>Interface</th><th>Instances</th><th>Notes</th></tr>
<tr><td>CAN FD</td><td>3</td><td>MCAN0 – MCAN2, up to 8 Mbit/s data phase</td></tr>
<tr><td>LIN</td><td>4</td><td>LIN 2.2A / SAE J2602</td></tr>
<tr><td>Ethernet MAC</td><td>1</td><td>10/100 Mbit/s, RMII, IEEE 802.1AS time sync</td></tr>
<tr><td>SPI</td><td>6</td><td>Up to 50 MHz</td></tr>
<tr><td>I2C</td><td>2</td><td>Standard, fast and fast-plus mode</td></tr>
</table>
<p class="note">Table 3-1: Communication interface overview</p>
<h3>3.1 CAN FD</h3>
<p>The device contains 3 CAN FD controllers (MCAN0 to MCAN2). Each controller provides
64 message buffers and supports partial networking with an external transceiver.</p>
<h3>3.2 Ethernet</h3>
<p>The Ethernet MAC connects to an external automotive Ethernet PHY such as a 100BASE-T1
transceiver through the RMII interface.</p>
""",
    # 4 — safety and quality (footnote)
    """
<h2>4 Functional safety and quality</h2>
<p>The SC-MCU-100 was developed according to an ISO 26262 compliant process and offers
safety mechanisms including lockstep cores, memory ECC, clock monitors and a windowed
watchdog. A safety manual is available on request.</p>
<p>Automotive grade devices are available for applications requiring extended
reliability.<sup>1</sup> Contact your sales representative for production part approval
documentation.</p>
<p>The hardware security module provides secure boot, key storage and cryptographic
acceleration for secure on-board communication.</p>
<br><br><br><br><br><br><br><br><br><br><br><br>
<hr>
<p class="note"><sup>1</sup> Devices with the suffix "-Q" are qualified according to
AEC-Q100 Grade 1.</p>
""",
    # 5 — electrical characteristics (values only in table, mV)
    """
<h2>5 Electrical characteristics</h2>
<h3>5.1 Recommended operating conditions</h3>
<table>
<tr><th>Symbol</th><th>Parameter</th><th>Min</th><th>Typ</th><th>Max</th><th>Unit</th></tr>
<tr><td>TA</td><td>Ambient operating temperature</td>
<td>-40</td><td>-</td><td>125</td><td>°C</td></tr>
<tr><td>TJ</td><td>Junction temperature</td><td>-40</td><td>-</td><td>150</td><td>°C</td></tr>
<tr><td>VDD</td><td>Core supply voltage</td><td>1.14</td><td>1.20</td><td>1.26</td><td>V</td></tr>
<tr><td>VDDIO</td><td>I/O supply voltage</td><td>2700</td><td>3300</td><td>5500</td><td>mV</td></tr>
<tr><td>fCPU</td><td>CPU clock frequency</td><td>-</td><td>-</td><td>400</td><td>MHz</td></tr>
</table>
<p class="note">Table 5-1: Recommended operating conditions</p>
<h3>5.2 Supply current</h3>
<table>
<tr><th>Mode</th><th>Typ</th><th>Max</th><th>Unit</th></tr>
<tr><td>Run, 400 MHz, all peripherals</td><td>180</td><td>260</td><td>mA</td></tr>
<tr><td>Standby, SRAM retention</td><td>45</td><td>120</td><td>µA</td></tr>
</table>
<p class="note">Table 5-2: Supply current</p>
""",
    # 6 — package
    """
<h2>6 Package information</h2>
<table>
<tr><th>Package</th><th>Body size</th><th>Pitch</th><th>GPIO</th></tr>
<tr><td>LQFP-144</td><td>20 × 20 mm</td><td>0.5 mm</td><td>112</td></tr>
<tr><td>BGA-292</td><td>17 × 17 mm</td><td>0.8 mm</td><td>220</td></tr>
</table>
<p class="note">Table 6-1: Package options</p>
<p>Thermal resistance values are provided in the separate package application note.</p>
""",
    # 7 — ordering information (SRAM ambiguity)
    """
<h2>7 Ordering information</h2>
<table>
<tr><th>Part number</th><th>Flash</th><th>SRAM</th><th>Package</th><th>Grade</th></tr>
<tr><td>SC-MCU-100A</td><td>4096 KB</td><td>512 KB</td><td>LQFP-144</td><td>Industrial</td></tr>
<tr><td>SC-MCU-100B</td><td>4096 KB</td><td>1024 KB</td><td>BGA-292</td><td>Industrial</td></tr>
<tr><td>SC-MCU-100B-Q</td><td>4096 KB</td><td>1024 KB</td><td>BGA-292</td><td>Automotive</td></tr>
</table>
<p class="note">Table 7-1: Ordering information</p>
<p>Not all combinations are available in all regions. SRAM size of engineering samples
may differ from production devices.</p>
""",
    # 8 — revision history
    """
<h2>8 Revision history</h2>
<table>
<tr><th>Revision</th><th>Date</th><th>Changes</th></tr>
<tr><td>1.0</td><td>2025-03-01</td><td>Initial release</td></tr>
<tr><td>1.1</td><td>2025-07-15</td><td>Added BGA-292 package</td></tr>
<tr><td>1.2</td><td>2025-11-20</td><td>Updated ordering information</td></tr>
</table>
<div class="banner">This datasheet is fictional and was generated by a script in the
SpecCheck repository. It contains deliberate edge cases for testing.</div>
""",
]


def build_sample_pdf(pages: list[str] | None = None) -> bytes:
    """Render the sample datasheet (or custom HTML pages) to PDF bytes."""
    doc = pymupdf.open()
    width, height = _PAGE.width, _PAGE.height
    body = pymupdf.Rect(_MARGIN, _MARGIN, width - _MARGIN, height - _MARGIN - 20)
    footer = pymupdf.Rect(_MARGIN, height - _MARGIN, width - _MARGIN, height - 20)
    source = pages if pages is not None else _PAGES
    for number, html in enumerate(source, start=1):
        page = doc.new_page(width=_PAGE.width, height=_PAGE.height)
        page.insert_htmlbox(body, html, css=_CSS)
        page.insert_htmlbox(
            footer,
            f"<p class='note'>{_FOOTER} &nbsp; Page {number} of {len(source)}</p>",
            css=_CSS,
        )
    doc.set_metadata(
        {
            "title": "SC-MCU-100 Datasheet (fictional sample)",
            "author": "SpecCheck",
            "creationDate": "D:20251120000000",
            "modDate": "D:20251120000000",
        }
    )
    doc.subset_fonts()
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data


def ensure_sample_pdf(path: Path = SAMPLE_PATH) -> bytes:
    """Return the sample PDF bytes, generating the file if it does not exist."""
    if path.exists():
        return path.read_bytes()
    data = build_sample_pdf()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data
