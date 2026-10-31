"""Render pages as HTML: each block absolutely positioned at its original box over the page
background. The same markup feeds the studio (fragments) and the PDF export (a full document).

Text-layer pages sit on a background with the original text removed. OCR/scanned pages sit on
the original image, so each block paints its sampled background colour over the old text.
"""

import html
import re
from pathlib import Path

from ..core.languages import RTL
from .markup import MARKERS, RUN_TAG, SUPERSCRIPTS, TAG_SPLIT, formula_pattern

PLAIN_DIGITS = str.maketrans(SUPERSCRIPTS, "0123456789+-()=")

STATIC = Path(__file__).resolve().parent.parent / "static"

# Starting sizes (pt) for OCR blocks, whose original font size is unknown: fit grows up to this.
MAX_SIZE = {
    "Title": 26,
    "Chapter-title": 24,
    "Section-title": 16,
    "Sub-section-title": 14,
    "Sub-sub-section-title": 13,
    "Header": 9,
    "Footer": 9,
    "Page-number": 9,
    "Footnote": 8,
    "Image-caption": 9,
    "Table-caption": 9,
    "Table": 10,
}
WRAP_GAP = 3  # pt kept clear around a picture text wraps around
SINGLE_LINE_GROWABLE = {
    "Title",
    "Chapter-title",
    "Section-title",
    "Sub-section-title",
    "Sub-sub-section-title",
    "Header",
    "Footer",
    "Image-caption",
    "Table-caption",
    "Paragraph",
    "List",
    "Footnote",
}
ALLOWED_TAGS = re.compile(r"</?(table|thead|tbody|tr|th|td|br|b|i|sup|sub)\b[^>]*>", re.I)
ANY_TAG = re.compile(r"<[^>]+>")
SPAN_ATTR = re.compile(r'\s(rowspan|colspan)\s*=\s*"?(\d+)"?', re.I)


def font_css_name(name):
    """A CSS font-family name for an embedded PDF font."""
    return "pdf-" + re.sub(r"[^A-Za-z0-9_-]", "_", name)


def font_family(block, fonts):
    """Inline font-family putting the PDF's own embedded font first, when the document has it."""
    if not fonts or block.style.font not in fonts:
        return ""
    # Single quotes: this goes inside a double-quoted style="…" attribute.
    return f";font-family:'{font_css_name(block.style.font)}',var(--ds-{block.style.family}-stack)"


def font_faces(page, fonts):
    """@font-face rules for the embedded fonts this page uses. `fonts`: name -> URL."""
    used = {b.style.font for b in page.blocks if b.style.font in (fonts or {})}
    if not used:
        return ""
    rules = "".join(f'@font-face{{font-family:"{font_css_name(n)}";src:url("{fonts[n]}")}}' for n in sorted(used))
    return f"<style>{rules}</style>"


def pt(v):
    """A length in points for CSS."""
    return f"{v:.2f}pt"


def clean_table_html(raw):
    """Keep only table structure tags (and rowspan/colspan) from OCR/translated HTML."""

    def keep(m):
        """A table structure tag reduced to its name and any rowspan or colspan; any other tag dropped."""
        tag = m.group(0)
        if not ALLOWED_TAGS.fullmatch(tag):
            return ""
        name = re.match(r"</?\s*(\w+)", tag).group(1).lower()
        if tag.startswith("</"):
            return f"</{name}>"
        attrs = "".join(f' {a.lower()}="{n}"' for a, n in SPAN_ATTR.findall(tag))
        return f"<{name}{attrs}>"

    return ANY_TAG.sub(keep, raw)


def chosen(block, lang):
    """(translation or None) for this language; None means draw the source."""
    t = block.translations.get(lang) if lang else None
    return t if t and t.status != "error" else None


# Scripts taller than the Latin line spacing a PDF gives: Nastaliq's stacked strokes, Malayalam's stacked conjuncts.
TALL_SCRIPTS = {"ur": 1.7, "ks": 1.7, "sd-Arab": 1.7, "ml": 1.35}


def unchanged(block, t):
    """The translation came back as the original ("FIPS 197", a row of numbers) and nobody has edited it."""
    if t.status != "done" or t.style:
        return False
    return t.cells == [c.text for c in block.cells] if block.cells else t.text == block.text and not t.html


def style_attr(block, box, covered, font_size=None, align=None):
    """The block's inline CSS: its box, colour, alignment and line height, and its background when `covered`."""
    s = block.style
    parts = [f"left:{pt(box[0])}", f"top:{pt(box[1])}", f"width:{pt(box[2] - box[0])}", f"height:{pt(box[3] - box[1])}"]
    if s.color:
        parts.append(f"color:{s.color}")
    if covered and s.background:
        parts.append(f"background:{s.background}")
    parts.append(f"text-align:{align or s.align}")
    if s.line_height:
        parts.append(f"line-height:{s.line_height}")
    if font_size:
        parts.append(f"font-size:{font_size}pt")
    return ";".join(parts)


def classes(block, extra=""):
    """The block's CSS classes: font family, label and its bold, italic or hanging style."""
    s = block.style
    c = ["ds-block", f"ds-{s.family}", f"ds-label-{block.label.lower()}"]
    if s.bold:
        c.append("ds-bold")
    if s.italic:
        c.append("ds-italic")
    if s.hanging:
        c.append("ds-hanging")
    if extra:
        c.append(extra)
    return " ".join(c)


def heading_cell(c, block):
    """A cell alone in its row and centred on the table: an infobox's section heading ("UNESCO World Heritage Site")."""
    alone = not any(d is not c and d.row == c.row and d.text.strip() for d in block.cells)
    mid, width = (block.bbox[0] + block.bbox[2]) / 2, block.bbox[2] - block.bbox[0]
    return alone and bool(c.text.strip()) and abs((c.bbox[0] + c.bbox[2]) / 2 - mid) < 0.1 * width


def cell_boxes(block):
    """Each table cell's box, grown into the space a longer translation may use: right up to the next filled
    cell in its row (or the table's edge), down to the next row (or the table's bottom). A cell measured
    around its text (an infobox, a statement) gets the room its column has; a ruled cell already meets its
    neighbours and keeps its size. A heading cell spans the table."""
    x_end, y_end = block.bbox[2], block.bbox[3]
    out = []
    for c in block.cells:
        x0, y0, x1, y1 = c.bbox
        if heading_cell(c, block):
            x0 = block.bbox[0]
        right = min(
            [d.bbox[0] for d in block.cells if d is not c and d.row == c.row and d.bbox[0] >= x1 - 1 and d.text.strip()]
            + [x_end]
        )
        below = min(
            [
                d.bbox[1]
                for d in block.cells
                if d.row > c.row
                and d.bbox[1] > y0 + 1  # rows may overlap a little
                and d.bbox[0] < x1
                and d.bbox[2] > x0
            ]
            + [y_end]
        )
        out.append([x0, y0, max(x1, right - 2), max(y1, below - 1)])
    return out


def fit_attrs(block, room=0.0, scanned=False, group=None):
    """fit.js settings. `room`: pt of empty space below that the text may grow into. Blocks with the same
    label and original size share a data-group, which fit.js brings to one common size (`group` replaces
    it: a table's cells are grouped by column). `scanned`: the size came from an OCR text layer over a
    scan, which is often well off the print, so the text fills its box instead (up to 1.6 times that size)."""
    size = block.style.font_size
    group = group or f"{block.label}:{size}"
    if size and scanned:
        return f'data-fit="fill" data-max="{round(size * 1.6, 2)}" data-size="{size}" data-group="{group}"'
    if size:
        grow = f' data-room="{room}"' if room > 0 else ""
        return f'data-fit="shrink" data-size="{size}" data-group="{group}"{grow}'
    return f'data-fit="fill" data-max="{MAX_SIZE.get(block.label, 11)}"'


def layout_box(block, page, margin_left):
    """(box, align): the block's box, widened for single-line blocks so a longer translation needn't
    wrap or shrink: out to the right margin (both margins, centred, if the line was centred),
    stopping at any block or picture on the same line."""
    x0, y0, x1, y1 = block.bbox
    size = block.style.font_size or 0
    if not size or (y1 - y0) > 1.8 * size or block.label not in SINGLE_LINE_GROWABLE:
        return list(block.bbox), None
    right_edge = page.width - margin_left
    others = [b.bbox for b in page.blocks if b is not block] + obstacles_for(block, page)
    neighbours = [r for r in others if r[1] < y1 and r[3] > y0]
    # Never inside the block itself: a title wider than the body (Mamba's) would leave its original's ends showing.
    right_limit = max(min([r[0] for r in neighbours if r[0] >= x1 - 1] + [right_edge]), x1)
    left_limit = min(max([r[2] for r in neighbours if r[2] <= x0 + 1] + [margin_left]), x0)
    # Centred on the text column (margins can be uneven: Mamba's is 11 pt off the page's middle), and not a line
    # that starts at the left margin.
    column_right = max((b.bbox[2] for b in page.blocks), default=right_edge)
    centred = (
        abs((x0 + x1) / 2 - (margin_left + column_right) / 2) < 6 and x0 > margin_left + 3 and block.label != "List"
    )  # an indented list item can land near the middle by chance
    if centred:
        half = min((x0 + x1) / 2 - left_limit, right_limit - (x0 + x1) / 2)
        return [(x0 + x1) / 2 - half, y0, (x0 + x1) / 2 + half, y1], "center"
    return [x0, y0, max(x1, right_limit - 2), y1], None


def text_html(text, mark_color=None):
    """Escaped text. Footnote and citation markers ("[¹]", "x²") become one small raised run, as in the
    original, in the colour the original drew them (`mark_color`, links are often blue)."""
    color = f' style="color:{mark_color}"' if mark_color else ""
    marked = MARKERS.sub(
        lambda m: f'<sup class="ds-ref"{color}>{m.group(0).translate(PLAIN_DIGITS)}</sup>', html.escape(text)
    )
    return marked.replace("\n", "<br>")


def maths_html(text, block, asset):
    """`text` as HTML with each inline formula drawn from its crop of the original page, sized in em so it
    scales with the fitted text. `asset(rel)`: URL of a file in the document dir."""
    pattern, size = formula_pattern(block.maths), block.style.font_size or 10
    if pattern is None:
        return text_html(text, block.style.mark_color)
    crops = {}
    for m in block.maths:
        crops.setdefault(m.text, m)
    out, at = [], 0
    for found in pattern.finditer(text):
        m = crops[found.group(0)]
        out.append(text_html(text[at : found.start()], block.style.mark_color))
        out.append(
            f'<img class="ds-maths" src="{html.escape(asset(m.image))}" alt="{html.escape(m.text)}" '
            f'style="width:{(m.bbox[2] - m.bbox[0]) / size:.3f}em;height:{(m.bbox[3] - m.bbox[1]) / size:.3f}em;'
            f'vertical-align:{-m.descent / size:.3f}em">'
        )  # sized up front: fit.js may run before it loads
        at = found.end()
    return "".join(out) + text_html(text[at:], block.style.mark_color)


def rich_html(rich, block, asset):
    """`maths_html` for text with run tags (Block.rich): the tags are kept, anything else tag-like dropped."""
    return "".join(
        (p if RUN_TAG.fullmatch(p) else "") if p.startswith("<") else maths_html(p, block, asset)
        for p in TAG_SPLIT.split(rich)
    )


ITEM_MARK = re.compile(r"^((?:<[^>]+>)*)\s*([•◦▪▫‣●○■□➢►–—*·-]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)])\s+")


def items_html(inner):
    """Each line as its own item with its bullet or number in a fixed-width box, so wrapped lines (a hanging
    indent) start under the item's text."""
    marked = (ITEM_MARK.sub(r'\1<span class="ds-mark">\2</span>', line) for line in inner.split("<br>"))
    return "".join(f'<div class="ds-item">{line}</div>' for line in marked)


def overlap(a, b):
    """The area two boxes share."""
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def box_area(b):
    """A box's area, at least 1 so it can divide."""
    return max((b[2] - b[0]) * (b[3] - b[1]), 1)


def free_room(block, page):
    """The room below a block (ingest's `room`) stopping at any block that starts in its lower half or under it,
    in its columns: two lines of a form set as separate blocks whose boxes overlap (IRS 1040's "Digital Assets")."""
    x0, y0, x1, y1 = block.bbox
    below = [
        b.bbox[1]
        for b in page.blocks
        if b is not block and b.bbox[1] > (y0 + y1) / 2 and min(b.bbox[2], x1) > max(b.bbox[0], x0)
    ]
    return max(0.0, min([y1 + block.room, *below]) - y1)


def obstacles_for(block, page):
    """The page's pictures and line art this block's text must keep clear of: not one it sits on (a coloured panel,
    a table's frame, a banner), which holds at least half of the block."""
    if block.in_figure:
        return []  # a chart's labels sit on their chart
    x0, y0, x1, y1 = block.bbox
    area = max((x1 - x0) * (y1 - y0), 1)
    # Another section set inside this one's box (a photo's caption beside a wrapped paragraph) is kept clear too.
    inside = [
        [*b.bbox[:3], b.bbox[3] + (b.room or 0)]  # with the room it may grow down into
        for b in page.blocks
        if b is not block
        and not b.in_figure
        and (b.text or b.cells)
        and overlap(b.bbox, block.bbox) >= 0.8 * box_area(b.bbox)
    ]
    return [o for o in page.obstacles + inside if overlap(o, block.bbox) < 0.5 * area]


def wrap_html(block, box, page):
    """Empty floats where pictures reach at least a line into the block's box, on the side they're on, so the text
    wraps around them as it did in the original (a photo beside a paragraph, left or right)."""
    sides = {"left": [], "right": []}
    line = 0.8 * (block.style.font_size or 10)
    for o in obstacles_for(block, page):
        if min(o[2], box[2]) - max(o[0], box[0]) < 4 or min(o[3], box[3]) - max(o[1], box[1]) < line:
            continue  # only touches the box, less than a line (a caption under its photo, a banner's edge)
        x0, y0 = max(o[0] - WRAP_GAP, box[0]), max(o[1] - WRAP_GAP, box[1])
        x1, y1 = min(o[2] + WRAP_GAP, box[2]), min(o[3] + WRAP_GAP, box[3])
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        side = "left" if (x0 + x1) / 2 < (box[0] + box[2]) / 2 else "right"
        sides[side].append([y0, y1, x1 - box[0] if side == "left" else box[2] - x0])
    out = []
    for side, floats in sides.items():
        merged = []
        for top, bottom, width in sorted(floats):
            if merged and top <= merged[-1][1]:  # overlapping ones on one side: one float
                merged[-1][1], merged[-1][2] = max(merged[-1][1], bottom), max(merged[-1][2], width)
            else:
                merged.append([top, bottom, width])
        y = box[1]
        for top, bottom, width in merged:
            if top > y + 0.5:  # an empty float above, so this one starts where the picture does
                out.append(f'<span class="ds-wrap-{side}" style="width:0;height:{pt(top - y)}"></span>')
            out.append(f'<span class="ds-wrap-{side}" style="width:{pt(width)};height:{pt(bottom - top)}"></span>')
            y = bottom
    return "".join(out)


def cell_css(cell, block):
    """A cell's own weight, slant and colour ("ASSETS" in bold blue); older documents bold the header row."""
    s = cell.style
    if s is None:
        return ";font-weight:700" if cell.header or block.style.bold else ""
    return f";font-weight:{700 if s.bold else 400};font-style:{'italic' if s.italic else 'normal'}" + (
        f";color:{s.color}" if s.color else ""
    )


def crop_css(url, box, page):
    """The text-free page shown in `box` only: a translated section's own background over the original page.
    render.css paints it under every section's text (overlapping boxes: one's patch never hides another's words),
    0.75pt past the box all round (the PDF's text box can be a hair inside its ink)."""
    return (
        f";--patch:url('{url}') calc(0.75pt - {pt(box[0])}) calc(0.75pt - {pt(box[1])})/"
        f"{pt(page.width)} {pt(page.height)} no-repeat"
    )


def render_block(block, page, lang, covered=None, fonts=None, asset=lambda rel: rel, crop=None):
    """One block as HTML. `covered`: paint the block's background (original text is in the image).
    `fonts`: names of the document's reusable embedded fonts (their @font-face is on the page).
    `asset(rel)`: URL of a file in the document dir (inline formula crops).
    `crop`: the text-free page's URL when the page underneath is the original (a language view): a section in
    `lang` covers its box with the text-free page and draws its translation; any other section is left as the
    original's own pixels, its text kept invisible so it can still be selected and clicked."""
    if covered is None:
        covered = page.background == page.image
    if not block.text and not block.cells and not block.html:
        return ""  # pictorial / furniture blocks with nothing to draw
    t = chosen(block, lang)
    if crop and t and unchanged(block, t):
        t = None  # over the original page its own pixels say the same, in place (an S-box's column numbers)
    if t and t.style:  # a reviewer's look changes for this translation
        block = block.model_copy(update={"style": block.style.model_copy(update=t.style)})
    source_fonts = fonts
    if t:  # the embedded font is a subset of the original's glyphs: translated text would switch fonts mid-word
        fonts = None
    drawn = block.in_figure and page.figure_text_kept  # figure text whose original pixels are in the background
    covered = covered or bool(drawn and t)
    as_original = bool(crop and lang and not t)  # the original's pixels show through
    if as_original:
        drawn, covered = True, False

    def own(box):  # a translated section's own patch of the text-free page
        """CSS painting the box with its own patch of the text-free page, under a translation."""
        return crop_css(crop, box, page) if crop and t and not covered else ""

    status = (
        "translated" if t else ("untranslated" if block.translatable and not block.in_figure and lang else "source")
    )
    written = t and (t.lang or lang)  # an edit may have written it in another language
    direction = ' dir="rtl"' if written in RTL else ""
    if t and (block.style.line_height or 1.22) < TALL_SCRIPTS.get(written, 0):
        block = block.model_copy(
            update={"style": block.style.model_copy(update={"line_height": TALL_SCRIPTS[written]})}
        )
    lang_attr = f' lang="{written}"' if t else ""
    if t and written in TALL_SCRIPTS:
        lang_attr += f' data-tightest="{TALL_SCRIPTS[written]}"'  # fit.js never packs its lines tighter
    data = f'data-block-id="{block.id}" data-status="{status}"{direction}{lang_attr}'
    margin_left = min((b.bbox[0] for b in page.blocks), default=36)

    if block.cells:  # text-layer table: each cell at its own box, original borders stay in the background
        texts = t.cells if t and t.cells and len(t.cells) == len(block.cells) else [c.text for c in block.cells]
        size = block.style.font_size
        cells = []
        for c, text, (x0, y0, x1, y1) in zip(block.cells, texts, cell_boxes(block)):
            box = [x0 - block.bbox[0], y0 - block.bbox[1], x1 - block.bbox[0], y1 - block.bbox[1]]
            top = " ds-top" if y1 > c.bbox[3] + 2 else ""  # grown down: keep the text where it started
            # A cell the translation left as it was (a number) keeps the original's font: Noto's wider digits
            # would not fit a column set in a condensed face.
            same = (
                font_family(block, source_fonts) or f";font-family:var(--ds-{block.style.family}-stack)"
                if t and text == c.text
                else ""
            )
            align = "center" if heading_cell(c, block) else None
            cells.append(
                f'<div class="ds-cell{top}" style="{style_attr(block, box, covered, align=align)}{cell_css(c, block)}{same}" '  # noqa: E501
                f"{fit_attrs(block, group=f'{block.id}:c{c.col}')}><span>{text_html(text, block.style.mark_color)}</span></div>"  # noqa: E501
            )
        box = block.bbox
        return (
            f'<div class="{classes(block, "ds-table ds-drawn" if as_original else "ds-table")}" {data} '
            f'style="left:{pt(box[0])};top:{pt(box[1])};width:{pt(box[2] - box[0])};height:{pt(box[3] - box[1])};'
            f'font-size:{size or 10}pt{font_family(block, fonts)}{own(box)}">{"".join(cells)}</div>'
        )

    if block.html:  # OCR table: re-draw the whole table
        content = clean_table_html(t.html if t and t.html else block.html)
        paint = "" if as_original else f";background:{block.style.background or '#fff'}"
        return (
            f'<div class="{classes(block, "ds-table-html ds-drawn" if as_original else "ds-table-html")}" {data} '
            f'{fit_attrs(block)} style="{style_attr(block, block.bbox, not as_original)}{paint}'
            f'{font_family(block, fonts)}">'
            f"{content}</div>"
        )

    text, rich = (t.text, t.rich) if t else (block.text, block.rich)
    box, align = layout_box(block, page, margin_left)
    scanned = page.background == page.image and block.source == "text_layer"
    inner = rich_html(rich, block, asset) if rich else maths_html(text, block, asset)
    if block.style.hanging:
        inner = items_html(inner)
    if t and "align" in t.style:
        align = None  # the reviewer's alignment wins over a centred line's
    return (
        f'<div class="{classes(block, "ds-drawn" if drawn and not t else "")}" {data} {fit_attrs(block, free_room(block, page), scanned)} '  # noqa: E501
        f'style="{style_attr(block, box, covered, align=align)}{font_family(block, fonts)}{own(box)}">'
        f"{wrap_html(block, box, page)}{inner}</div>"
    )


def static_version():
    """Changes whenever render.css or fit.js does, so an open studio tab can swap in the files that match the HTML."""
    return "-".join(str(int((STATIC / f).stat().st_mtime)) for f in ("render.css", "fit.js"))


def render_page(page, lang, background_url, fonts=None, asset=lambda rel: rel, image_url=None):
    """`fonts`: the document's reusable embedded fonts, name -> URL. `asset(rel)`: URL of a document file.
    `image_url`: the original page raster. Given (the studio's language views), the page is the original and only
    the sections translated into `lang` are drawn again (see render_block's `crop`)."""
    crop = background_url if image_url and lang else None
    blocks = "".join(render_block(b, page, lang, fonts=fonts, asset=asset, crop=crop) for b in page.blocks)
    return (
        f'<div class="ds-page" data-page="{page.index}" data-static="{static_version()}" '
        f'style="width:{pt(page.width)};height:{pt(page.height)};'
        f"background-image:url('{image_url if crop else background_url}')\">{font_faces(page, fonts)}{blocks}</div>"
    )


def render_document(doc, lang, background_url, pages=None, font_url=lambda rel: rel):
    """A complete HTML document (all or some pages) that fits its text on load. Used for export
    and the full-document preview. `background_url(page)` gives each page's image URL, `font_url(rel)` the URL
    of any file in the document dir (fonts, inline formula crops)."""
    css = (STATIC / "render.css").read_text()
    js = (STATIC / "fit.js").read_text()
    chosen_pages = [p for p in doc.pages if pages is None or p.index in pages]
    first = chosen_pages[0] if chosen_pages else None
    page_rule = f"@page {{ size: {pt(first.width)} {pt(first.height)}; margin: 0; }}" if first else ""
    fonts = {name: font_url(rel) for name, rel in doc.fonts.items()}
    body = "".join(render_page(p, lang, background_url(p), fonts, font_url) for p in chosen_pages)
    return (
        f'<!doctype html><html lang="{lang or "und"}"><head><meta charset="utf-8">'
        f"<title>{html.escape(doc.filename)}</title>"
        f"<style>html,body{{margin:0;padding:0}} {page_rule} {css}</style>"
        f"<script>{js}</script></head>"
        f"<body>{body}<script>document.fonts.ready.then(() => {{ dsFit(document); "
        f"document.body.dataset.fitted = '1'; }});</script></body></html>"
    )
