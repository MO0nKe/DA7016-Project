"""Block labels from position and typography: titles and headings, running heads and page numbers,
footnotes, captions, and the furniture repeated across pages."""

import re
from collections import Counter

from .text import words

TYPE_OF = {
    "Title": "Title",
    "Chapter-title": "Title",
    "Section-title": "SectionHeader",
    "Sub-section-title": "SectionHeader",
    "Sub-sub-section-title": "SectionHeader",
    "Paragraph": "Text",
    "List": "Text",
    "Footnote": "Footnote",
    "Header": "PageHeader",
    "Footer": "PageFooter",
    "Page-number": "PageNumber",
    "Table": "Table",
    "Image-caption": "Caption",
    "Table-caption": "Caption",
}


# Labels that are drawn as-is, never translated.
NON_TRANSLATABLE = {
    "Page-number",
    "Image",
    "Chart",
    "Diagram",
    "Equation",
    "Expression",
    "Code",
    "Website-link",
    "Flag",
    "Placeholder-text",
    "Advertisement",
    "Contact-info",
}


FIGURE_LABELS = {"Image", "Chart", "Diagram"}  # OCR blocks whose text inside is figure text


PAGE_NUMBER = re.compile(r"^(page\s*)?\d+(\s*(of|/)\s*\d+)?$", re.I)


YEAR = re.compile(r"^(19|20)\d\d$")  # "2025" on a form, not page 2025


CAPTION = re.compile(r"^(fig(ure)?|chart|diagram|image)\.?\s*\d", re.I)


RUNNING_HEAD = re.compile(r"^\d+\s+\D|\D\s+(page\s*)?\d+$", re.I)  # "6 VARIATION…", "…Track Page 1"


MID_PAGE_NUMBER = re.compile(r"\D\s\d{1,4}\s+\D")  # "Mars Science Laboratory/Curiosity 2 NASA Facts"


TABLE_CAPTION = re.compile(r"^table\s*\d", re.I)


FOOTNOTE_START = re.compile(r"^[\d¹²³⁴⁵⁶⁷⁸⁹⁰*†‡]+\s")


FOOTNOTE_MARK = re.compile(r"^[\d¹²³⁴⁵⁶⁷⁸⁹⁰*∗†‡]")  # "∗Equal contribution", "1https://…"


# ---------------------------------------------------------------- labelling


def body_size(all_blocks):
    """The body text size: the font size carrying the most characters (10 pt when there's no text)."""
    sizes = Counter()
    for b in all_blocks:
        if b["kind"] == "text":
            sizes[b["style"].font_size] += len(b["text"])
    return sizes.most_common(1)[0][0] if sizes else 10.0


def furniture_key(text):
    """Running heads differ only in their page number and where it sits: "6 VARIATION." / "VARIATION. 4"."""
    return re.sub(r"[\W\d_]+", "", text.lower())


def furniture_band(bbox, h):
    """ "top", "bottom" or None: where running heads, feet and page numbers sit."""
    return "top" if bbox[3] < 0.1 * h else "bottom" if bbox[1] > 0.85 * h else None


def repeated_furniture(pages_blocks, heights):
    """Texts that recur at the top/bottom of several pages: running headers/footers."""
    if len(pages_blocks) < 2:
        return set(), set()
    seen = {"top": Counter(), "bottom": Counter()}
    for blocks, h in zip(pages_blocks, heights):
        on_page = {(furniture_band(b["bbox"], h), furniture_key(b["text"])) for b in blocks if b["kind"] == "text"}
        for band, key in on_page:
            if band and key:
                seen[band][key] += 1
    return ({k for k, n in seen["top"].items() if n >= 2}, {k for k, n in seen["bottom"].items() if n >= 2})


def label_for(b, page_index, page_h, body, largest_on_page, headers, footers, scanned=False, busy=()):
    """`scanned`: the text layer is OCR over a page image, whose font sizes are noise. `busy`: bands
    ("top"/"bottom") holding more than a running head would (the top of a form)."""
    if b["kind"] == "table":
        return "Table"
    text, style, (_, y0, _, y1) = b["text"], b["style"], b["bbox"]
    size = style.font_size or body
    key, band = furniture_key(text), furniture_band(b["bbox"], page_h)
    if PAGE_NUMBER.match(text) and not YEAR.match(text) and (y1 < 0.12 * page_h or y0 > 0.8 * page_h):
        return "Page-number"
    # A running head: repeated, smaller than the text at the very top, or one short line with the page number.
    running = band not in busy and len(text) < 90 and y1 - y0 < 2 * size and RUNNING_HEAD.search(text)
    if band == "top" and (key in headers or size < body and band not in busy or running):
        return "Header"
    footer_like = (
        running or band not in busy and len(text) < 90 and MID_PAGE_NUMBER.search(text) and not CAPTION.match(text)
    )
    if band == "bottom" and (key in footers or footer_like):
        return "Footer"
    if page_index == 0 and size >= 1.3 * body and size >= largest_on_page:
        return "Title"
    if TABLE_CAPTION.match(text):
        return "Table-caption"
    if CAPTION.match(text):
        return "Image-caption"
    if b["list"]:
        return "List"
    short = len(text) < 90 and not text.endswith(".")
    heading_like = words(text) and (not scanned or text.isupper())
    if heading_like and (size >= 1.15 * body or (style.bold and size >= body and short)):
        return "Section-title"
    if (
        size <= 0.8 * body
        and (y0 > 0.6 * page_h or FOOTNOTE_START.match(text))
        or size < body
        and y0 > 0.75 * page_h
        and FOOTNOTE_MARK.match(text)
    ):
        return "Footnote"
    return "Paragraph"
