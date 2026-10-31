"""Make the tab icons.

    uv run scripts/make_assets.py

Writes frontend/public/{favicon.ico, apple-touch-icon.png}: the mark, as public/panna.svg and ui/PannaMark.tsx.
Deterministic: run it again after changing the mark or its colour, and commit what it writes.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"
ACCENT = (0x9A, 0x50, 0x48)  # --color-accent, oklch(52% 0.10 28)
PAPER = (0xF9, 0xF8, 0xF5)  # --color-surface


def icon(size):
    """The mark: प (pa) on an accent tile, its headline across the top (as public/panna.svg), drawn at 4x, reduced."""
    s = size * 4 / 48
    img = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size * 4 - 1, size * 4 - 1], radius=11 * s, fill=ACCENT)
    width = round(5 * s)
    draw.line([(10 * s, 14 * s), (38 * s, 14 * s)], fill=PAPER, width=width)
    draw.line([(31 * s, 14 * s), (31 * s, 38 * s)], fill=PAPER, width=width)
    arc = [(16 + 6 - 6 * np.cos(a), 22 + 6 * np.sin(a)) for a in np.linspace(0, np.pi / 2, 12)]
    loop = [(16, 14), (16, 22), *arc, (31, 28)]
    draw.line([(x * s, y * s) for x, y in loop], fill=PAPER, width=width, joint="curve")
    return img.resize((size, size), Image.LANCZOS)


def main():
    """Write the studio's favicon.ico and apple-touch-icon.png."""
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    icon(48).save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    touch = Image.new("RGB", (180, 180), ACCENT)  # opaque and square: iOS rounds the corners itself
    touch.paste(icon(180), mask=icon(180))
    touch.save(PUBLIC / "apple-touch-icon.png")
    print("icons: favicon.ico (16, 32, 48), apple-touch-icon.png (180)")


if __name__ == "__main__":
    main()
