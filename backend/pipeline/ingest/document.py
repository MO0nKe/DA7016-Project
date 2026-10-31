"""Ingest a PDF into the document model: every page read, labelled and rasterised, once per file."""

import hashlib
import io
import time
from collections import Counter

import pymupdf
from PIL import Image

from ...core.models import Block, Document, Maths, Page
from .blocks import raw_blocks
from .fonts import extract_fonts
from .labels import NON_TRANSLATABLE, TYPE_OF, body_size, furniture_band, label_for, repeated_furniture
from .maths import MATHS_DPI, maths_runs
from .raster import RASTER_DPI, overbars, rasterize, room_below, sample_background, scan_like, text_free
from .regions import drawn_areas, figure_areas, in_figure, layout_regions, region_label, split_by_regions
from .style import rich_text
from .text import SUPERSCRIPT_FLAG, has_letters, hex_color, rect_center_in, text_quality, union

MIN_TEXT_QUALITY = 0.97


class UnreadablePDF(ValueError):
    """The upload starts like a PDF but can't be read: damaged, truncated or password-protected."""


# ---------------------------------------------------------------- whole document


def ingest_pdf(pdf_bytes, filename, store):
    """Create (or return the existing) document. Never spends credits: pages whose text layer is
    missing or garbled are marked `pending_ocr`."""
    doc_id = hashlib.sha256(pdf_bytes).hexdigest()[:12]
    if store.exists(doc_id):
        return store.load(doc_id)
    try:
        pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except pymupdf.FileDataError as exc:
        raise UnreadablePDF("this PDF is damaged and can't be read") from exc
    if pdf.needs_pass:
        raise UnreadablePDF("this PDF is password-protected")
    if not pdf.page_count:
        raise UnreadablePDF("this PDF has no pages")
    doc_dir = store.dir(doc_id)
    (doc_dir / "pages").mkdir(parents=True, exist_ok=True)
    (doc_dir / "source.pdf").write_bytes(pdf_bytes)

    stripped = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # same pages, text removed

    extracted, kept, qualities, scanned, regions = [], [], [], [], []
    for page in pdf:
        blocks, keep = raw_blocks(page)
        kept.append(keep)
        text = " ".join(b["text"] if b["kind"] == "text" else " ".join(c.text for c in b["cells"]) for b in blocks)
        qualities.append(text_quality(text) if text.strip() else 0.0)
        scanned.append(scan_like(page))
        regions.append(layout_regions(page) if blocks and not scanned[-1] else [])
        extracted.append(split_by_regions(blocks, regions[-1]))

    usable = [q >= MIN_TEXT_QUALITY for q in qualities]
    body = body_size([b for blocks, ok in zip(extracted, usable) if ok for b in blocks])
    headers, footers = repeated_furniture(
        [b if ok else [] for b, ok in zip(extracted, usable)], [p.rect.height for p in pdf]
    )

    pages = []
    for i, page in enumerate(pdf):
        stem = f"pages/page-{i + 1:03d}"
        png = rasterize(page)
        (doc_dir / f"{stem}.png").write_bytes(png)
        image = f"{stem}.png"
        h = page.rect.height
        has_text = bool(extracted[i])
        if has_text and not usable[i] or (scanned[i] and not has_text):
            pages.append(
                Page(
                    index=i,
                    width=page.rect.width,
                    height=h,
                    source="pending_ocr",
                    dpi=RASTER_DPI,
                    image=image,
                    background=image,
                    text_quality=qualities[i],
                )
            )
            continue

        img = Image.open(io.BytesIO(png)).convert("RGB")
        scale = RASTER_DPI / 72
        largest = max((b["style"].font_size or 0 for b in extracted[i] if b["kind"] == "text"), default=0)
        pictures = [r for r, kind in regions[i] if kind == "picture"]
        figures = figure_areas(page)
        art = [d["rect"] for d in page.get_drawings()] if not scanned[i] else []
        marks = [
            (s["bbox"], hex_color(s["color"]))
            for blk in page.get_text("dict")["blocks"]
            if blk["type"] == 0
            for l in blk["lines"]
            for s in l["spans"]
            if s["flags"] & SUPERSCRIPT_FLAG and any(ch.isdigit() for ch in s["text"])
        ]
        blocks, bars = [], []
        bands = Counter(furniture_band(b["bbox"], h) for b in extracted[i])
        busy = {band for band in ("top", "bottom") if bands[band] > 3}
        for n, b in enumerate(extracted[i]):
            label = region_label(b, label_for(b, i, h, body, largest, headers, footers, scanned[i], busy))
            text = " | ".join(c.text for c in b["cells"]) if b["kind"] == "table" else b["text"]
            style = b["style"]
            bbox = [round(v, 2) for v in b["bbox"]]
            style.background = sample_background(img, bbox, scale)
            mark = next((color for box, color in marks if rect_center_in(box, bbox)), None)
            style.mark_color = mark if mark != style.color else None
            maths = []
            if b["kind"] == "text" and not scanned[i]:
                for k, (formula, box, descent) in enumerate(r for r in maths_runs(b["lines"]) if r[0] in text):
                    over = overbars(box, art)
                    bars += over
                    box = [round(v, 2) for v in union([box] + [list(r) for r in over])]
                    rel = f"maths/p{i}-b{n}-{k}.png"
                    (doc_dir / "maths").mkdir(exist_ok=True)
                    page.get_pixmap(dpi=MATHS_DPI, clip=pymupdf.Rect(box), alpha=False).save(doc_dir / rel)
                    maths.append(Maths(text=formula, bbox=box, descent=descent, image=rel))
            blocks.append(
                Block(
                    id=f"p{i}-b{n}",
                    order=n,
                    label=label,
                    type=TYPE_OF.get(label, "Text"),
                    bbox=bbox,
                    text=text,
                    rich=rich_text(b["lines"], style, text) if b["kind"] == "text" and not scanned[i] else None,
                    cells=b.get("cells"),
                    style=style,
                    source="text_layer",
                    maths=maths,
                    translatable=label not in NON_TRANSLATABLE and has_letters(text),
                    in_figure=in_figure(b, label, figures, pictures),
                )
            )
        bg_img = None
        if scanned[i]:
            background = image  # text is part of the scan image: cover it instead of removing it
        else:
            background = f"{stem}-bg.png"
            # Figure text stays as drawn (axis labels, legends) until the user translates it.
            bg_png = text_free(stripped[i], img, kept[i] + [b.bbox for b in blocks if b.in_figure], scale, bars)
            (doc_dir / background).write_bytes(bg_png)
            bg_img = Image.open(io.BytesIO(bg_png)).convert("RGB")
        if bg_img:  # on a scan the text is in the background, so nothing below looks empty
            for b in blocks:
                b.room = room_below(b, blocks, bg_img, scale, h, b.style.background or "#ffffff")
        pages.append(
            Page(
                index=i,
                width=page.rect.width,
                height=h,
                source="text_layer",
                dpi=RASTER_DPI,
                image=image,
                background=background,
                text_quality=qualities[i],
                blocks=blocks,
                figure_text_kept=not scanned[i],
                obstacles=[] if scanned[i] else drawn_areas(page),
            )
        )

    doc = Document(
        id=doc_id,
        filename=filename,
        created=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        pages=pages,
        fonts=extract_fonts(pdf, doc_dir),
    )
    store.save(doc)
    return doc
