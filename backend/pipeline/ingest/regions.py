"""Page regions: the pymupdf-layout model's regions (blocks spanning two are split, and its labels refine
ours), and drawn figures and photos, whose text is translated only on request."""

import pymupdf

from .blocks import text_block
from .text import rect_center_in


def figure_areas(page):
    """Boxes of pictures and drawn figures, whose text isn't translated unless asked: raster images
    (not a scan, nor a banner or background spanning the page) and drawing clusters with many curves
    or slanted strokes (diagrams, charts, logos; tables, forms and boxes are straight lines)."""
    w, h = page.rect.width, page.rect.height
    images = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
    out = [r for r in images if r.width < 0.9 * w and r.height < 0.9 * h]
    drawings = page.get_drawings()
    if not drawings:
        return out

    def strokes(d):
        """How many curves and slanted lines the drawing has."""
        return sum(
            it[0] == "c" or it[0] == "l" and abs(it[1].x - it[2].x) > 0.5 and abs(it[1].y - it[2].y) > 0.5
            for it in d["items"]
        )

    for cluster in page.cluster_drawings(drawings=drawings):
        if sum(strokes(d) for d in drawings if cluster.contains(d["rect"])) >= 20:
            out.append(cluster)
    return out


def drawn_areas(page):
    """Boxes of everything drawn rather than written that text must not run into: pictures, and clusters of line
    art at least 8 pt each way (charts, diagrams, frames, coloured panels; not rules or underlines). Nothing that
    spans the page (a background, a scan). Text sitting on one of them is told apart when it's drawn (render)."""
    w, h = page.rect.width, page.rect.height

    def page_sized(r):
        """Whether `r` covers nearly the whole page."""
        return r.width >= 0.9 * w and r.height >= 0.9 * h

    rects = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
    drawings = [d for d in page.get_drawings() if not page_sized(d["rect"])]  # a frame would join every cluster
    rects += page.cluster_drawings(drawings=drawings) if drawings else []
    return [[round(v, 1) for v in r] for r in rects if r.width >= 8 and r.height >= 8 and not page_sized(r)]


def in_figure(block, label, figures, pictures=()):
    """Text inside a figure. In a figure found by drawings (`figures`) only short blocks count: long text in its
    box is a paragraph beside it. In a picture the layout model found (`pictures`) all of it counts (axis
    labels, legends): the model gives text beside a picture regions of its own."""
    if block["kind"] != "text" or label in ("Image-caption", "Table-caption"):
        return False
    short = len(block["lines"]) <= 2 and len(block["text"]) < 100
    return (
        short
        and any(rect_center_in(block["bbox"], f) for f in figures)
        or any(rect_center_in(block["bbox"], f) for f in pictures)
    )


def layout_regions(page):
    """[(bbox, class)] from PyMuPDF's layout model (pymupdf-layout, ONNX): title, section-header, text,
    list-item, caption, footnote, formula, picture, table, page-header, page-footer. [] if it fails, and
    ingest falls back to its own heuristics."""
    try:
        import pymupdf.layout  # noqa: F401  (loads the model and enables page.get_layout)

        page.get_layout()
        return [(list(r[:4]), r[4]) for r in page.layout_information or []]
    except Exception:  # a missing model or an odd page: the heuristics alone still give a usable ingest
        return []


def region_of(bbox, regions):
    """Index of the region overlapping `bbox` most, or None."""
    best, index = 0.0, None
    for n, (r, _) in enumerate(regions):
        area = max(0.0, min(bbox[2], r[2]) - max(bbox[0], r[0])) * max(0.0, min(bbox[3], r[3]) - max(bbox[1], r[1]))
        if area > best:
            best, index = area, n
    return index


def split_by_regions(blocks, regions):
    """Split text blocks whose lines lie in different layout regions (a heading glued to its paragraph, two
    paragraphs the PDF merged), and note each block's region class in b["region"]."""
    out = []
    for b in blocks:
        if b["kind"] != "text" or b.get("fixed"):
            out.append(b)
            continue
        groups, last = [], object()
        for line in b["lines"]:
            n = region_of(line["bbox"], regions)
            if n is not None and n != last and groups:
                groups.append([])
            if not groups:
                groups.append([])
            groups[-1].append(line)
            last = n if n is not None else last
        parts = [b] if len(groups) == 1 else [text_block(g, b["list"]) for g in groups]
        for part in parts:
            n = region_of(part["bbox"], regions)
            part["region"] = regions[n][1] if n is not None else None
        out += parts
    return out


REGION_LABEL = {
    "title": "Title",
    "section-header": "Section-title",
    "caption": "Image-caption",
    "footnote": "Footnote",
    "list-item": "List",
    "page-header": "Header",
    "page-footer": "Footer",
}


def region_label(b, label):
    """Our label, unless we called it a paragraph and the layout model saw something more specific."""
    hint = REGION_LABEL.get(b.get("region"))
    if label != "Paragraph" or not hint:
        return label
    if hint in ("Title", "Section-title", "Header", "Footer") and len(b["text"]) > 150:
        return label  # a long block is not a heading or a running head, whatever its box looks like
    return hint
