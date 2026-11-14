"""Render docs/pitch/pitch.html to PITCH.pdf (one A4 page) and docs/pitch/pitch.png.

    python -m scripts.make_pitch

Needs Playwright (requirements-dev.txt). Set JA_CHROME to a Chrome/Edge executable to use an
installed browser instead of Playwright's own (on Windows, Edge works:
"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe").
Edit the HTML, run this again, and check that it still reports one page.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "pitch" / "pitch.html"
PDF = ROOT / "PITCH.pdf"
PNG = ROOT / "docs" / "pitch" / "pitch.png"


def page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed: pip install -r requirements-dev.txt")
        return 1
    chrome = os.environ.get("JA_CHROME")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome) if chrome else p.chromium.launch()
        page = browser.new_page(viewport={"width": 794, "height": 1123}, device_scale_factor=2)
        page.goto(SRC.as_uri())
        page.wait_for_load_state("networkidle")
        overflow = page.evaluate("document.body.scrollHeight - document.body.clientHeight")
        pdf = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        PDF.write_bytes(pdf)
        page.screenshot(path=str(PNG), full_page=False)
        browser.close()
    n = page_count(pdf)
    print(f"{PDF.relative_to(ROOT)}: {n} page(s), {len(pdf) // 1024} KB; preview {PNG.relative_to(ROOT)}")
    if overflow > 0:
        print(f"Warning: content is {overflow}px taller than the page and is cut off. Shorten the text.")
    if n != 1 or overflow > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
