"""Page images of the originals for compare.html. Usage (repo root): uv run python eval/conversion/orig_png.py"""

from pathlib import Path

import pymupdf

out = Path("eval/conversion/orig")
out.mkdir(exist_ok=True)
for f in sorted(Path("documents").glob("*.pdf")):
    for i, page in enumerate(pymupdf.open(f)):
        page.get_pixmap(dpi=130, alpha=False).save(out / f"{f.stem}-p{i + 1}.png")
