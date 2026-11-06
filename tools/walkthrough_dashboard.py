"""Demo: geführte Tour durch das Dashboard — nimmt ein Video auf + macht
Detail-Screenshots (Workflow-Drilldown, Prompt-Modal).

.venv/bin/python tools/walkthrough_dashboard.py [BASE_URL] [OUTDIR]
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7777"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "build/dashboard-screenshots")
VID = OUT / "video"
OUT.mkdir(parents=True, exist_ok=True)
VID.mkdir(parents=True, exist_ok=True)

VW, VH = 1600, 1000
DRILL_ISSUE = 304  # Issue mit vollem Pipeline-Durchlauf (alle Stages, Score)

# Tab-Key, Label, Verweildauer(ms)
TOUR = [
    ("status", "Status", 3500),
    ("llm", "LLM & Kosten", 3500),
    ("quality", "LLM Quality", 3500),
    ("activity", "Activity", 3500),
    ("workflow", "Workflow", 2500),
    ("logs", "Logs", 3000),
    ("security", "Security", 3000),
    ("compliance", "Compliance", 3500),
    ("settings", "Settings", 3500),
    ("selfcheck", "Self-Check", 3000),
]


def _try(page, js: str) -> None:
    try:
        page.evaluate(js)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! eval fehlgeschlagen: {js[:40]} — {exc}")


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(
            viewport={"width": VW, "height": VH},
            record_video_dir=str(VID),
            record_video_size={"width": VW, "height": VH},
        )
        page = ctx.new_page()
        page.goto(BASE, wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(2500)

        for key, label, dwell in TOUR:
            print(f"  → Tab {label}")
            _try(page, f"showTab('{key}')")
            page.wait_for_timeout(1200)
            with contextlib.suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=6000)

            if key == "workflow":
                # Drilldown in ein Issue mit vollem Durchlauf (Gate-Stages/Score).
                page.wait_for_timeout(1200)
                _try(page, f"loadWorkflowDetail({DRILL_ISSUE})")
                page.wait_for_timeout(3500)
                page.screenshot(path=str(OUT / "detail-01-workflow-drilldown.png"), full_page=True)
                print("  ✓ detail-01-workflow-drilldown.png")

            if key == "llm":
                # System-Prompt-Ansicht (Prompt-Anpassung) als Modal zeigen.
                page.wait_for_timeout(dwell)
                _try(page, "viewSystemPrompt('planning')")
                page.wait_for_timeout(2500)
                page.screenshot(path=str(OUT / "detail-02-prompt-view.png"))
                print("  ✓ detail-02-prompt-view.png")
                _try(page, "closePromptModal()")
                page.wait_for_timeout(800)
                continue

            page.wait_for_timeout(dwell)

        page.wait_for_timeout(1500)
        video_path = page.video.path() if page.video else None
        ctx.close()  # finalisiert das Video
        browser.close()

    if video_path:
        dest = VID / "dashboard-tour.webm"
        Path(video_path).replace(dest)
        print(f"\nVideo: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
