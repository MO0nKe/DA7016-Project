"""Sections and chapters: the PDF's own bookmarks when it has them, else our heading blocks."""

import re

import pymupdf

NUMBERED = re.compile(r"^(\d{1,2}(\.\d{1,2})*\.?|[A-Z]\.\d{1,2}(\.\d{1,2})*\.?|chapter)\s+\S", re.I)
UNNUMBERED = re.compile(
    r"^(abstract|summary|introduction|conclusions?|references|bibliography|acknowledge?ments?|"
    r"appendix|contents|preface|foreword)\b",
    re.I,
)
HEADING_LEVEL = {"Title": 1, "Chapter-title": 1, "Section-title": 2, "Sub-section-title": 3, "Sub-sub-section-title": 4}


def heading_level(block):
    """ "5.1.2 ShiftRows" sits under "5.1" and "5"; otherwise the label decides."""
    m = NUMBERED.match(block.text)
    if block.label == "Title" or not m or not m.group(1)[0].isdigit():
        return HEADING_LEVEL[block.label]
    return min(1 + len(m.group(1).rstrip(".").split(".")), 4)


def outline(doc, pdf_path):
    """[{level, title, page, top, block_id}]; `top` in PDF points from the page top, `block_id`
    only for headings we found ourselves (so the studio can show their translation)."""
    with pymupdf.open(pdf_path) as pdf:
        toc = pdf.get_toc(simple=False)
        heights = [p.rect.height for p in pdf]
    if toc:
        items = []
        for level, title, page, dest in toc:
            if page < 1:
                continue  # bookmark pointing nowhere
            point = dest.get("to") if isinstance(dest, dict) else None
            # Bookmark targets use PDF coordinates (origin bottom-left); ours are top-down.
            top = max(0.0, heights[page - 1] - point.y) if point is not None else 0.0
            items.append(
                {"level": level, "title": title.strip(), "page": page - 1, "top": round(top, 1), "block_id": None}
            )
        return items
    blocks = [(p, b) for p in doc.pages for b in p.blocks if b.label in HEADING_LEVEL and b.text.strip()]
    # Papers and standards number their sections. Then an unnumbered big or bold line is a section only
    # if it comes after the first real one and looks like the numbered ones: not the authors and
    # affiliations under the title, nor a figure's own title.
    numbered = [b for _, b in blocks if NUMBERED.match(b.text)]
    if numbered:
        fonts = {b.style.font for b in numbered}
        first = next(i for i, (_, b) in enumerate(blocks) if NUMBERED.match(b.text) or UNNUMBERED.match(b.text))
        blocks = [
            (p, b)
            for i, (p, b) in enumerate(blocks)
            if b.label == "Title"
            or NUMBERED.match(b.text)
            or UNNUMBERED.match(b.text)
            or (i > first and b.style.font in fonts)
        ]
    titles = {b.text for _, b in blocks if b.label == "Title"}  # an infobox often repeats the title
    return [
        {"level": heading_level(b), "title": b.text, "page": p.index, "top": b.bbox[1], "block_id": b.id}
        for p, b in blocks
        if b.label == "Title" or b.text not in titles
    ]
