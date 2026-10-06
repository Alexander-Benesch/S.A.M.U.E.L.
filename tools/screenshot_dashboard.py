"""Demo-Hilfe: Screenshot jedes Dashboard-Tabs via Headless-Chromium.

Nutzung: .venv/bin/python tools/screenshot_dashboard.py [BASE_URL] [OUTDIR]
Voraussetzung: laufendes Dashboard + `playwright` + Chromium installiert.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7777"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "build/dashboard-screenshots")
OUT.mkdir(parents=True, exist_ok=True)

# (Tab-Key wie in showTab(), Dateiname/Label)
TABS = [
    ("status", "01-status"),
    ("llm", "02-llm-kosten"),
    ("quality", "03-llm-quality"),
    ("activity", "04-activity"),
    ("workflow", "05-workflow"),
    ("logs", "06-logs"),
    ("security", "07-security"),
    ("compliance", "08-compliance"),
    ("settings", "09-settings"),
    ("selfcheck", "10-self-check"),
]


def main() -> int:
    saved = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
        page.goto(BASE, wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(1500)
        for key, name in TABS:
            try:
                page.evaluate(f"showTab('{key}')")
            except Exception as exc:  # noqa: BLE001
                print(f"  ! showTab('{key}') fehlgeschlagen: {exc}")
            # Daten laden lassen (mehrere async fetches pro Tab)
            with contextlib.suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=8000)
            page.wait_for_timeout(1800)
            path = OUT / f"{name}.png"
            page.screenshot(path=str(path), full_page=True)
            saved.append(path.name)
            print(f"  ✓ {path}")
        browser.close()
    print(f"\n{len(saved)} Screenshots in {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
