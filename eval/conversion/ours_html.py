"""Flowing HTML, one file per page, from our current ingest (for the conversion comparison).
Usage: ours_html.py <out dir> <pdf>...  (run from the repo root with the project venv)"""

import base64
import html
import sys
import tempfile
from pathlib import Path

import pymupdf

sys.path.insert(0, ".")
from backend.core.store import DocumentStore
from backend.pipeline.ingest import ingest_pdf
from backend.pipeline.ingest.blocks import raw_blocks
from backend.pipeline.ingest.regions import figure_areas
from backend.pipeline.render import clean_table_html

PICTURE = {"Image", "Chart", "Diagram", "Equation", "Expression", "Figure"}

HEAD = '<!doctype html><meta charset="utf-8"><style>body{font:16px/1.5 "Noto Serif","Noto Serif Devanagari","Noto Serif Bengali","Noto Serif Tamil",serif;max-width:760px;margin:24px auto;color:#111} table{border-collapse:collapse} td,th{border:1px solid #999;padding:2px 6px} img{max-width:100%} .fn{font-size:13px;color:#444} figcaption,.cap{font-size:14px;color:#333}</style>'  # noqa: E501
SKIP = {"Header", "Footer", "Page-number"}


def crop(page, rect):
    """The page region as an inline PNG figure."""
    pix = page.get_pixmap(dpi=110, clip=pymupdf.Rect(rect))
    return f'<figure><img src="data:image/png;base64,{base64.b64encode(pix.tobytes("png")).decode()}"></figure>'


def merged(boxes, near=6, gap=60):
    """Figures and kept lines (equation pieces, exponents, numbers) joined into one picture where they touch."""
    out = [b for b in map(list, boxes) if b[3] - b[1] <= 3 * (b[2] - b[0])]  # rotated text: a margin stamp
    joined = True
    while joined:
        joined = False
        for i, a in enumerate(out):
            for b in out[i + 1 :]:
                beside = (
                    b[0] < a[2] + gap and a[0] < b[2] + gap or min(a[2] - a[0], b[2] - b[0]) < 40
                )  # "(4)" far right
                if b[1] < a[3] + near and a[1] < b[3] + near and beside:
                    a[:] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    out.remove(b)
                    joined = True
                    break
            if joined:
                break
    return sorted((b for b in out if b[2] - b[0] > 30 or b[3] - b[1] > 30), key=lambda b: b[1])  # not a stray glyph


def table(b):
    """A text-layer table block as an HTML table."""
    rows, ncols = {}, max(c.col for c in b.cells) + 1
    for c in b.cells:
        rows.setdefault(c.row, []).append(c)
    out = []
    for _, cells in sorted(rows.items()):
        tag = "th" if all(c.header for c in cells) else "td"
        by_col = {c.col: c.text for c in cells}
        out.append("<tr>" + "".join(f"<{tag}>{html.escape(by_col.get(n, ''))}</{tag}>" for n in range(ncols)) + "</tr>")
    return "<table>" + "".join(out) + "</table>"


def page_html(pdf_page, page):
    """One ingested page as flowing HTML: headings, paragraphs, lists, tables, figures cropped from the PDF and
    footnotes last."""
    ocr = page.source == "ocr"  # Bodhan OCR blocks: its own labels; pictures are blocks too
    _, keep = ([], []) if ocr else raw_blocks(pdf_page)
    crops = [] if ocr else merged([list(r) for r in figure_areas(pdf_page)] + [list(k) for k in keep])
    levels = []  # x0 of open list levels
    out = []

    def close_lists(to=0):
        """Close open list levels down to `to`."""
        while len(levels) > to:
            out.append("</ul>")
            levels.pop()

    placed, notes = set(), []
    for b in page.blocks:
        for i, r in enumerate(crops):  # a figure/equation goes before the first block below it in its column
            if i not in placed and r[1] <= b.bbox[1] and r[0] < b.bbox[2] and b.bbox[0] < r[2]:
                close_lists()
                out.append(crop(pdf_page, r))
                placed.add(i)
        if b.label in SKIP or b.in_figure:
            continue
        if b.label in PICTURE:
            close_lists()
            out.append(crop(pdf_page, b.bbox))
            continue
        if b.html:
            close_lists()
            out.append(clean_table_html(b.html))
            continue
        if not b.text.strip():
            continue
        text = html.escape(b.text)
        if b.label == "List":
            x = b.bbox[0]
            while levels and x < levels[-1] - 3:
                out.append("</ul>")
                levels.pop()
            if not levels or x > levels[-1] + 3:
                out.append("<ul>")
                levels.append(x)
            out.append(f"<li>{text.lstrip('•◦▪●○■–- ')}</li>")
            continue
        close_lists()
        if b.cells:
            out.append(table(b))
        elif b.label == "Title":
            out.append(f"<h1>{text}</h1>")
        elif b.label in ("Section-title", "Sub-section-title", "Sub-sub-section-title", "Chapter-title"):
            out.append(f"<h2>{text}</h2>")
        elif b.label in ("Image-caption", "Table-caption"):
            out.append(f'<p class="cap">{text}</p>')
        elif b.label == "Footnote":  # at the end of the page, as a reader expects
            notes.append(f'<p class="fn">{text}</p>')
        elif out and out[-1].startswith("<p>") and text[:1].islower() and out[-1][-5:-4] not in ".!?:":
            out[-1] = f"{out[-1][:-4]} {text}</p>"  # a paragraph continued in the next column
        else:
            out.append(f"<p>{text}</p>")
    close_lists()
    for i, r in enumerate(crops):
        if i not in placed:
            out.append(crop(pdf_page, r))
    return HEAD + "".join(out + notes)


if __name__ == "__main__":
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    store = DocumentStore(Path(tempfile.mkdtemp()))
    for f in sys.argv[2:]:
        pdf = pymupdf.open(f)
        doc = ingest_pdf(Path(f).read_bytes(), Path(f).name, store)
        for p in doc.pages:
            if p.source == "pending_ocr":
                continue
            (out_dir / f"{Path(f).stem}-p{p.index + 1}.html").write_text(page_html(pdf[p.index], p))
        print("ok", Path(f).stem)
