"""Baut aus README.md ein weitergebbares Dokument — self-contained HTML + PDF.

Alle Bilder (inkl. animiertes GIF) werden als Base64 in die HTML eingebettet;
das Video (webm) wird — falls vorhanden — als <video> mitgeliefert. Die HTML ist
damit eine einzige Datei, die in jedem Browser per Doppelklick oeffnet (kein
Markdown, keine externen Assets). Aus derselben HTML rendert Headless-Chromium
eine PDF (Video -> Hinweis, GIF -> Standbild; das laesst sich in PDF nicht
animieren).

Nutzung:
    .venv/bin/python tools/build_readme_doc.py [README] [OUTDIR]
Voraussetzung: `markdown`, `playwright` + Chromium installiert.
"""

from __future__ import annotations

import base64
import mimetypes
import re
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "README.md"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "dist"
OUT.mkdir(parents=True, exist_ok=True)

# Video: lokal (nicht committet) im Buildbereich oder als publiziertes Doku-Asset.
VIDEO_CANDIDATES = [
    ROOT / "build" / "dashboard-screenshots" / "video" / "dashboard-tour.webm",
    ROOT / "docs" / "demo" / "dashboard-tour.webm",
]
GIF_ALT = "Dashboard-Tour durch alle Tabs"

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6; color: #1f2328; background: #fff;
  max-width: 860px; margin: 0 auto; padding: 40px 48px 80px;
}
h1, h2, h3, h4 { line-height: 1.25; margin-top: 1.6em; font-weight: 600; }
h1 { font-size: 2em; border-bottom: 1px solid #d0d7de; padding-bottom: .3em; }
h2 { font-size: 1.5em; border-bottom: 1px solid #d0d7de; padding-bottom: .3em; }
h3 { font-size: 1.25em; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: #eff1f3; padding: .2em .4em; border-radius: 6px; font-size: 85%;
}
pre {
  background: #f6f8fa; padding: 16px; border-radius: 8px; overflow: auto;
  font-size: 85%; line-height: 1.45;
}
pre code { background: none; padding: 0; }
blockquote {
  margin: 1em 0; padding: .4em 1em; color: #57606a;
  border-left: .25em solid #d0d7de; background: #f6f8fa; border-radius: 0 6px 6px 0;
}
table { border-collapse: collapse; width: 100%; margin: 1em 0; display: block; overflow: auto; }
th, td { border: 1px solid #d0d7de; padding: 6px 13px; }
th { background: #f6f8fa; }
tr:nth-child(2n) { background: #f6f8fa; }
img { max-width: 100%; height: auto; border: 1px solid #d0d7de; border-radius: 8px; margin: .5em 0; }
img[alt$="GIF"], img[alt*="Tour"] { border-color: #54aeff; }
video { max-width: 100%; border: 1px solid #54aeff; border-radius: 8px; margin: .5em 0; display: block; }
hr { border: none; border-top: 1px solid #d0d7de; margin: 2em 0; }
.docmeta { color: #57606a; font-size: 90%; margin-bottom: 2em; }
.print-note { display: none; }
@media print {
  body { max-width: none; padding: 0; font-size: 11px; }
  h1, h2 { border-bottom: none; }
  video { display: none; }
  .print-note { display: block; color: #57606a; font-style: italic;
    border: 1px dashed #d0d7de; border-radius: 8px; padding: 8px 12px; }
  pre, blockquote, table, img { page-break-inside: avoid; }
  a { color: #1f2328; }
}
@page { margin: 16mm 14mm; }
"""


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def inline_images(html: str) -> str:
    """<img src="docs/demo/x.png"> -> Base64-Data-URI (relativ zum Repo-Root)."""

    def repl(m: re.Match[str]) -> str:
        src = m.group(1)
        if src.startswith(("data:", "http://", "https://")):
            return m.group(0)
        p = (ROOT / src).resolve()
        if not p.is_file():
            print(f"  ! Bild fehlt, bleibt Referenz: {src}")
            return m.group(0)
        return m.group(0).replace(src, data_uri(p))

    return re.sub(r'<img[^>]*\bsrc="([^"]+)"', repl, html)


def inject_video(html: str) -> str:
    """Nach dem Tour-GIF ein <video> (Base64) + Print-Hinweis einsetzen."""
    video = next((p for p in VIDEO_CANDIDATES if p.is_file()), None)
    if not video:
        print("  · kein Video gefunden — HTML nur mit GIF/Bildern")
        note = (
            '<p class="print-note">Hinweis: Die animierte Dashboard-Tour '
            "und das Video sind nur in der HTML-Fassung bewegt; im PDF steht "
            "hier ein Standbild.</p>"
        )
        return re.sub(
            r'(<img[^>]*alt="' + re.escape(GIF_ALT) + r'"[^>]*>)', r"\1\n" + note, html, count=1
        )
    uri = data_uri(video)
    block = (
        '\n<video controls preload="metadata" playsinline>'
        f'<source src="{uri}" type="video/webm">'
        "Ihr Browser spielt dieses Video nicht ab (webm)."
        "</video>\n"
        '<p class="print-note">Hinweis: Animierte Tour + Video laufen nur in der '
        "HTML-Fassung; im PDF steht hier ein Standbild.</p>"
    )
    return re.sub(
        r'(<img[^>]*alt="' + re.escape(GIF_ALT) + r'"[^>]*>)', r"\1" + block, html, count=1
    )


def build_html() -> Path:
    body = markdown.markdown(
        SRC.read_text(encoding="utf-8"),
        extensions=["extra", "sane_lists", "toc", "nl2br"],
    )
    body = inline_images(body)
    body = inject_video(body)
    doc = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>S.A.M.U.E.L. — README</title>
<style>{CSS}</style>
</head>
<body>
<p class="docmeta">Exportiert aus <code>README.md</code> — eigenstaendige Datei,
alle Bilder eingebettet. Oeffnet in jedem Browser.</p>
{body}
</body>
</html>
"""
    out = OUT / "SAMUEL_README.html"
    out.write_text(doc, encoding="utf-8")
    print(f"  ✓ {out}  ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def build_pdf(html_path: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ! playwright fehlt — PDF uebersprungen")
        return
    pdf = OUT / "SAMUEL_README.pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(800)
        page.pdf(
            path=str(pdf),
            format="A4",
            print_background=True,
            margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
        )
        browser.close()
    print(f"  ✓ {pdf}  ({pdf.stat().st_size / 1e6:.1f} MB)")


def main() -> int:
    print(f"README: {SRC}")
    html = build_html()
    build_pdf(html)
    print(f"\nFertig -> {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
