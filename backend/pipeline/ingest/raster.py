"""Page images: rasters, the text-free background translations are drawn over, link underlines and
overbars, sampled background colours, and the empty room below a block."""

import io

import pymupdf
from PIL import Image, ImageChops

from .style import MATH_FONT, font_name
from .text import horizontal

RASTER_DPI = 150


def sample_background(img, bbox, scale):
    """Median colour of a thin ring just outside the block: what to paint over scanned text."""
    x0, y0, x1, y1 = (int(round(v * scale)) for v in bbox)
    x0, y0 = max(0, x0 - 3), max(0, y0 - 3)
    x1, y1 = min(img.width - 1, x1 + 3), min(img.height - 1, y1 + 3)
    if x1 <= x0 or y1 <= y0:
        return "#ffffff"
    px = img.load()
    ring = [px[x, y0] for x in range(x0, x1, 2)] + [px[x, y1] for x in range(x0, x1, 2)]
    ring += [px[x0, y] for y in range(y0, y1, 2)] + [px[x1, y] for y in range(y0, y1, 2)]
    med = [sorted(c[i] for c in ring)[len(ring) // 2] for i in range(3)]
    return "#{:02x}{:02x}{:02x}".format(*med)


def room_below(block, others, background, scale, page_h, colour="#ffffff"):
    """Points of empty space under a block that a longer translation may grow into: down to the next block
    in its columns, anything drawn in the text-free `background` (pictures, rules, kept maths) or the bottom
    margin, less a gap of half a line."""
    x0, _, x1, y1 = block.bbox
    tops = [
        o.bbox[1]
        for o in others
        if o is not block and o.bbox[1] >= y1 - 1 and min(x1, o.bbox[2]) - max(x0, o.bbox[0]) > 1
    ]
    bottom = min(tops + [page_h - 36])
    area = tuple(int(round(v * scale)) for v in (x0, y1 + 1, x1, bottom))
    if area[3] - area[1] < 2 or area[2] <= area[0]:
        return 0.0
    strip = background.crop(area)
    ink = (
        ImageChops.difference(strip, Image.new("RGB", strip.size, colour)).convert("L").point(lambda v: 255 * (v > 40))
    )
    if box := ink.getbbox():
        bottom = y1 + 1 + box[1] / scale
    return round(max(0.0, bottom - y1 - (block.style.font_size or 10) / 2), 1)


def scan_like(page):
    """A scanned page: a picture covers it and none of its text is visible (at most an invisible OCR layer).
    Slides and posters draw real text over a full-page picture; that text can be removed like any other."""
    area = page.rect.width * page.rect.height
    big_image = any(pymupdf.Rect(i["bbox"]).get_area() > 0.6 * area for i in page.get_image_info())
    return big_image and not any(s["type"] != 3 for s in page.get_texttrace())  # 3 = invisible text


def underlines(page, keep):
    """Thin horizontal line art just under a line of text and no wider than it: link underlines, which would
    otherwise stay in the background and cut through the translation. Table rules run past the text, and
    anything near text kept as drawn (fraction bars in maths) is left alone."""
    # Spans, not lines: PyMuPDF splits a visual line where the font or direction changes, and a superscript
    # reference has a baseline of its own.
    # Spaces count towards the run: broken Indic shaping can leave a word's text box short of its glyphs, but
    # the space after it starts where the glyphs end.
    spans = [
        s
        for b in page.get_text("dict")["blocks"]
        if b["type"] == 0
        for l in b["lines"]
        if horizontal(l)
        for s in l["spans"]
        if s["text"] and not MATH_FONT.search(font_name(s["font"]))
    ]
    near_kept = [pymupdf.Rect(k) + (-3, -3, 3, 3) for k in keep]
    art = [d["rect"] for d in page.get_drawings()]
    lines = [n for n, q in enumerate(art) if min(q.width, q.height) < 2]
    under = set()
    for n, r in enumerate(art):
        if r.height >= 2 or r.width <= 2 or any(r.intersects(k) for k in near_kept):
            continue
        above = sorted(
            (s["bbox"][0] - 1.5, s["bbox"][2] + 1.5)
            for s in spans
            if s["origin"][1] - 1 <= r.y0 <= s["bbox"][3] + 2.5 and s["bbox"][2] > r.x0 and s["bbox"][0] < r.x1
        )
        words = [
            a
            for a, _ in sorted(
                (s["bbox"][0] - 1.5, 0)
                for s in spans
                if s["text"].strip()
                and s["origin"][1] - 1 <= r.y0 <= s["bbox"][3] + 2.5
                and s["bbox"][2] > r.x0
                and s["bbox"][0] < r.x1
            )
        ]
        if not words or words[0] > r.x0:
            continue  # no text over it, or the mark starts before the text: a rule
        reach = above[0][1]
        for a, b in above[1:]:
            if a - reach > 12:  # a gap wider than a word space: not one underlined run
                break
            reach = max(reach, b)
        if reach >= r.x1:
            under.add(n)

    def touches(q, r):  # q meets an end of r. By hand: Rect.intersects ignores zero-height (hairline) rects.
        """Whether `q` meets either end of `r`."""
        return any(q.x0 <= x + 1 and q.x1 >= x - 1 and q.y0 <= r.y1 + 1 and q.y1 >= r.y0 - 1 for x in (r.x0, r.x1))

    # A mark chained (through other marks) to a line that is not under text is a piece of a rule or a box's
    # edge. Marks that only touch each other ("[2][3]", two underlined links side by side) are underlines.
    rule = {n for n in under if any(m not in under and m != n and touches(art[m], art[n]) for m in lines)}
    while grown := {n for n in under - rule if any(touches(art[m], art[n]) for m in rule)}:
        rule |= grown
    return [art[n] for n in sorted(under - rule)]


def overbars(box, art):
    """Thin line art above an inline formula's middle and within its width: the bars of Ā or x̄, and a stacked
    fraction's bar, drawn as lines rather than glyphs. They belong in the formula's crop, not in the background."""
    x0, y0, x1, y1 = box
    top = y0 + 0.6 * (y1 - y0)
    return [
        r
        for r in art
        if r.height < 2
        and 1 < r.width <= x1 - x0 + 2
        and r.x0 >= x0 - 1
        and r.x1 <= x1 + 1
        and y0 - 3 <= (r.y0 + r.y1) / 2 <= top
    ]


def text_free(page, original, keep, scale, marks=()):
    """PNG of `page` with its text, link underlines and `marks` (line art belonging to text, such as maths
    overbars) removed, pictures and other drawings kept, and `keep` pasted back from `original` (its raster):
    what translations are drawn over. Modifies `page` (use a throwaway copy)."""
    if marks := underlines(page, keep) + list(marks):
        # Touching marks on one line ("[1][2][3]") can be one path in the PDF, which is only removed when a
        # single redaction covers all of it.
        merged = []
        for r in sorted(marks, key=lambda r: (round(r.y0, 1), r.x0)):
            if merged and abs(merged[-1].y0 - r.y0) < 0.3 and r.x0 <= merged[-1].x1 + 1:
                merged[-1] = merged[-1] | r
            else:
                merged.append(pymupdf.Rect(r))
        for r in merged:
            page.add_redact_annot(r + (-0.5, -0.5, 0.5, 0.5), fill=False)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
            text=pymupdf.PDF_REDACT_TEXT_NONE,
        )
    page.add_redact_annot(page.rect, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    return restore(rasterize(page), original, keep, scale)


def rasterize(page, dpi=RASTER_DPI):
    """The page as PNG bytes, without transparency."""
    return page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")


def restore(background_png, original, boxes, scale, pad=1.0):
    """Paste the original page's pixels back over `boxes` (PDF points) of the text-free background:
    text we draw as-is rather than re-typeset."""
    if not boxes:
        return background_png
    bg = Image.open(io.BytesIO(background_png)).convert("RGB")
    for x0, y0, x1, y1 in boxes:
        area = tuple(int(round(v * scale)) for v in (x0 - pad, y0 - pad, x1 + pad, y1 + pad))
        bg.paste(original.crop(area), area[:2])
    out = io.BytesIO()
    bg.save(out, "PNG")
    return out.getvalue()
