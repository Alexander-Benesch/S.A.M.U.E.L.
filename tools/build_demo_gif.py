"""Baut ein kompaktes Slideshow-GIF aus den Dashboard-Screenshots (README-tauglich).

.venv/bin/python tools/build_demo_gif.py [SCREENSHOT_DIR] [OUT_GIF]
Jedes Bild wird auf feste Breite skaliert und oben auf eine feste Canvas-Hoehe
beschnitten (konsistente Frames), dann als animiertes GIF gespeichert.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "build/dashboard-screenshots")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "build/dashboard-screenshots/dashboard-tour.gif")

WIDTH = 1100
HEIGHT = 760  # Canvas-Hoehe (Kopf + erster Inhalt jedes Tabs)
MS_PER_FRAME = 2200
BG = (11, 18, 32)  # dunkles Panel-Blau

# Reihenfolge der Tour (Detail-Frames zwischen den passenden Tabs).
ORDER = [
    "01-status.png",
    "02-llm-kosten.png",
    "detail-02-llm-routing-night.png",
    "03-llm-quality.png",
    "04-activity.png",
    "05-workflow.png",
    "detail-01-workflow-drilldown.png",
    "06-logs.png",
    "07-security.png",
    "08-compliance.png",
    "09-settings.png",
    "10-self-check.png",
]


def frame(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGB")
    scale = WIDTH / img.width
    img = img.resize((WIDTH, round(img.height * scale)), Image.LANCZOS)
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BG)
    canvas.paste(img.crop((0, 0, WIDTH, min(HEIGHT, img.height))), (0, 0))
    return canvas


def main() -> int:
    frames = [frame(SRC / n) for n in ORDER if (SRC / n).exists()]
    if not frames:
        print("Keine Screenshots gefunden.")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUT,
        save_all=True,
        append_images=frames[1:],
        duration=MS_PER_FRAME,
        loop=0,
        optimize=True,
    )
    mb = OUT.stat().st_size / 1e6
    print(f"{len(frames)} Frames -> {OUT} ({mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
