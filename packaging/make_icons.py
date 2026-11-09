#!/usr/bin/env python3
"""Regenerate the app icons from brightspace_downloader/assets/logo.svg.

Only needed after changing the logo; the generated files are part of the project.

Usage:
    pip install resvg-py pillow
    python packaging/make_icons.py

Writes into brightspace_downloader/assets/:
    icon.png   1024x1024  - window/dock icon on macOS and Linux (GTK/Qt)
    icon.ico   16..256    - window/taskbar icon on Windows, and the .exe file icon
    icon.icns  16..1024   - macOS .app bundle icon
and copies logo.svg into brightspace_downloader/web/ for the header logo in the UI.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import resvg_py
from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "brightspace_downloader" / "assets"
SVG = ASSETS / "logo.svg"


def render(size: int) -> Image.Image:
    """Rasterize the SVG to a size x size RGBA image (transparent background)."""
    # resvg handles the logo's nested clip-paths (the rounded corners) correctly.
    png = resvg_py.svg_to_bytes(svg_path=str(SVG), width=size, height=size)
    img = Image.open(io.BytesIO(bytes(png))).convert("RGBA")
    if img.size != (size, size):
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
        img = canvas
    return img


def main() -> None:
    big = render(1024)
    big.save(ASSETS / "icon.png", optimize=True)

    # Render each ICO size directly from the vector so small sizes stay crisp.
    ico_sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = [render(s) for s in ico_sizes]
    frames[-1].save(ASSETS / "icon.ico", format="ICO",
                    sizes=[(s, s) for s in ico_sizes], append_images=frames[:-1])

    big.save(ASSETS / "icon.icns", format="ICNS")
    # The in-app header logo (web/ is the root the webview serves).
    shutil.copyfile(SVG, ASSETS.parent / "web" / "logo.svg")
    for name in ("icon.png", "icon.ico", "icon.icns"):
        print(f"wrote {ASSETS / name} ({(ASSETS / name).stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
