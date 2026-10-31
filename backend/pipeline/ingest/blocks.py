"""Blocks from a page's text: lines grouped into blocks, list items, continuations merged, line metrics,
and reading order."""

import re

import pymupdf

from ...core.models import Cell, Style
from .maths import is_maths, maths_line
from .raster import scan_like
from .style import dominant_style, same_look, size_change
from .tables import grid_blocks, label_value_tables, layout_grid, pieces, shared_rows, wordless
from .text import collapse_repeated_marks, horizontal, join_lines, rect_center_in, union, visual_lines

EQUATION_NUMBER = re.compile(r"^\(\d+(\.\d+)?[a-z]?\)$")


def bullets_on(page):
    """Small filled shapes: list bullets drawn as graphics rather than text."""
    out = []
    for d in page.get_drawings():
        r = d["rect"]
        if d.get("fill") is not None and 1 < r.width < 8 and 1 < r.height < 8 and abs(r.width - r.height) < 2:
            out.append(r)
    return out


def starts_item(line, bullets):
    """Whether the line starts a list item: it begins with a bullet character, or a drawn bullet sits just left of
    it."""
    x0, y0, _, y1 = line["bbox"]
    first = "".join(s["text"] for s in line["spans"]).lstrip()[:1]
    if first and first in "•◦▪●○■–-":  # ("" is in every string)
        return True
    return any(x0 - 22 <= b.x1 <= x0 + 1 and b.y0 < y1 and b.y1 > y0 for b in bullets)


def raw_blocks(page):
    """(blocks, keep): text blocks and tables of one page in reading order, before labelling, and
    the boxes of text that is left drawn as-is in the background (rotated lines, maths)."""
    tables, grids = [], []
    for t in page.find_tables().tables:
        if layout_grid(t):
            grids.append(t.bbox)
            continue
        cells, r = [], 0
        for row in t.rows:
            ruled = [(c, cell) for c, cell in enumerate(row.cells) if cell is not None]
            if split := shared_rows(page, ruled):
                above, pairs = split
                for c, ls in above.items():  # continues the previous row's cell in that column
                    prev = next((p for p in reversed(cells) if p.row == r - 1 and p.col == c), None)
                    if prev:
                        prev.text = f"{prev.text} {join_lines(ls)}".strip()
                        prev.bbox = [round(v, 2) for v in union([prev.bbox] + [l["bbox"] for l in ls])]
                    else:
                        top = dict(pairs[0])
                        top[c] = ls + top.get(c, [])
                        pairs[0] = sorted(top.items())
                for pair in pairs:
                    cells += [
                        Cell(
                            row=r,
                            col=c,
                            bbox=[round(v, 2) for v in union([l["bbox"] for l in ls])],
                            text=join_lines(ls),
                            style=dominant_style([s for l in ls for s in l["spans"]]),
                        )
                        for c, ls in pair
                    ]
                    r += 1
                continue
            label = next((x for x in cells if x.row == r - 1 and x.col == ruled[0][0]), None)
            alone = [page.get_text("text", clip=pymupdf.Rect(cell)).strip() for _, cell in ruled]
            words = [b for b in page.get_text("dict", clip=pymupdf.Rect(ruled[0][1]))["blocks"] if b["type"] == 0]
            if (
                label
                and label.text
                and alone[0]
                and not any(alone[1:])
                and words
                and words[0]["bbox"][1] - label.bbox[3] < 0.3 * (label.style.font_size if label.style else 10)
            ):
                label.text = f"{label.text} {collapse_repeated_marks(re.sub(r'\s+', ' ', alone[0]))}"  # a wrapped label
                label.bbox = [round(v, 2) for v in union([label.bbox, words[0]["bbox"]])]
                continue
            for c, cell in ruled:
                text = collapse_repeated_marks(
                    re.sub(r"\s+", " ", page.get_text("text", clip=pymupdf.Rect(cell))).strip()
                )
                inside = [
                    s
                    for b in page.get_text("dict", clip=pymupdf.Rect(cell))["blocks"]
                    if b["type"] == 0
                    for l in b["lines"]
                    for s in l["spans"]
                    if s["text"].strip()
                ]
                # The text's own left edge, not the rule's: something drawn before it (a flag) stays clear.
                x0 = max(cell[0], min((s["bbox"][0] for s in inside if s["text"].strip()), default=cell[0]) - 1)
                cells.append(
                    Cell(
                        row=r,
                        col=c,
                        bbox=[round(v, 2) for v in (x0, *cell[1:])],
                        text=text,
                        header=r == 0,
                        style=dominant_style(inside) if inside else None,
                    )
                )
            r += 1
        if cells:
            spans = [
                s
                for b in page.get_text("dict", clip=pymupdf.Rect(t.bbox))["blocks"]
                if b["type"] == 0
                for l in b["lines"]
                for s in l["spans"]
                if s["text"].strip()
            ]
            tables.append(
                {
                    "kind": "table",
                    "bbox": list(t.bbox),
                    "cells": cells,
                    "style": dominant_style(spans) if spans else Style(),
                }
            )

    bullets = bullets_on(page)
    out, keep = list(tables), []
    in_grid = {}  # grid index -> its pieces, which are ordered row by row as one unit
    flags = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_DEHYPHENATE
    for b in page.get_text("dict", flags=flags)["blocks"]:
        if b["type"] != 0 or any(rect_center_in(b["bbox"], t["bbox"]) for t in tables):
            continue
        lines = [l for l in b["lines"] if "".join(s["text"] for s in l["spans"]).strip()]
        # A display equation is drawn as-is: the whole block when most of it is maths (exponents and
        # equation numbers count), else just its maths lines, leaving the prose around them as text.
        maths = is_maths(lines)
        keep += [l["bbox"] for l in lines if maths or not horizontal(l)]
        lines = visual_lines([l for l in lines if not maths and horizontal(l)])
        marks = [maths_line(l) for l in lines]
        if any(marks):
            whole = sum(m or wordless(l) for m, l in zip(marks, lines)) >= 0.5 * len(lines)
            drop = [whole or m or wordless(l) for m, l in zip(marks, lines)]
            prose = [l for l, d in zip(lines, drop) if not d]
            # Brackets or a subscript set into a prose line (the tall parentheses of "GF(2⁸)") aren't a display
            # line: their pixels pasted back would show through the line's translation.
            keep += [l["bbox"] for l, d in zip(lines, drop) if d and not any(inside_line(l, p) for p in prose)]
            lines = prose
        if not lines:
            continue
        # In forms, and in one-line blocks like "Title    2    Running head", each piece stays where it is.
        grid = next((n for n, g in enumerate(grids) if rect_center_in(b["bbox"], g)), None)
        if grid is not None or len(lines) == 1 and len(pieces(lines[0])) > 1:
            for piece in (p for l in lines for p in pieces(l)):
                text = join_lines([piece])
                if text.strip("."):  # not a leader dot
                    item = {
                        "kind": "text",
                        "bbox": piece["bbox"],
                        "text": text,
                        "style": dominant_style(piece["spans"]),
                        "list": False,
                        "fixed": True,
                        "lines": [piece],
                    }
                    (in_grid.setdefault(grid, []) if grid is not None else out).append(item)
            continue
        # Split into list items where a bullet starts a line.
        groups, current = [], []
        for line in lines:
            if current and (starts_item(line, bullets) or size_change(current[-1], line)):
                groups.append(current)
                current = []
            current.append(line)
        groups.append(current)
        is_list = any(starts_item(g[0], bullets) for g in groups[1:]) or starts_item(lines[0], bullets)
        for g in groups:
            spans = [s for l in g for s in l["spans"]]
            out.append(
                {
                    "kind": "text",
                    "bbox": union([l["bbox"] for l in g]),
                    "text": join_lines(g),
                    "style": dominant_style(spans),
                    "list": is_list,
                    "lines": g,
                }
            )
    numbers = [
        b
        for b in out
        if b["kind"] == "text"
        and EQUATION_NUMBER.match(b["text"])
        and any(k[1] < b["bbox"][3] and b["bbox"][1] < k[3] for k in keep)
    ]  # "(4.2)" beside an equation
    keep += [b["bbox"] for b in numbers]
    out = [b for b in out if not any(b is n for n in numbers)]
    out += [{"kind": "grid", "bbox": union([p["bbox"] for p in items]), "items": items} for items in in_grid.values()]
    ordered = []
    for b in reading_order(out):
        ordered += grid_blocks(b["items"]) if b["kind"] == "grid" else [b]
    if not scan_like(page):  # an OCR text layer splits lines into fragments that look like labels
        ordered = label_value_tables(ordered)
    return merge_continuations(ordered), keep


def inside_line(piece, line):
    """`piece` lies within `line`'s width and covers at least half of its height."""
    (a0, b0, a1, b1), (x0, y0, x1, y1) = piece["bbox"], line["bbox"]
    return x0 - 1 <= a0 and a1 <= x1 + 1 and min(b1, y1) - max(b0, y0) >= 0.5 * (y1 - y0)


def reading_order(blocks, gap=8):
    """Recursive XY-cut: split at the widest vertical gutter (columns, left before right), else into
    horizontal bands; bands are read together where they share a gutter, so a column continues past
    a gap that happens to line up with one in the next column, or stay within one column."""
    if len(blocks) < 2:
        return blocks
    cut = gutter(blocks, gap)
    if cut is not None:
        left = [b for b in blocks if b["bbox"][2] <= cut]
        return reading_order(left, gap) + reading_order([b for b in blocks if b["bbox"][2] > cut], gap)
    bands = []
    for b in sorted(blocks, key=lambda b: b["bbox"][1]):
        if bands and b["bbox"][1] < max(x["bbox"][3] for x in bands[-1]) - 1:
            bands[-1].append(b)
        else:
            bands.append([b])
    if len(bands) == 1:
        return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))
    left, right = min(b["bbox"][0] for b in blocks), max(b["bbox"][2] for b in blocks)

    def narrow(group):  # within one column (which may start beside a picture rather than text)
        """Whether the blocks fit in one column's width."""
        return max(b["bbox"][2] for b in group) - min(b["bbox"][0] for b in group) < 0.6 * (right - left)

    groups = [bands[0]]
    for band in bands[1:]:
        if gutter(groups[-1] + band, gap) is not None or narrow(groups[-1] + band):
            groups[-1] += band
        else:
            groups.append(band)
    if len(groups) == 1:  # nothing to split on
        return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))
    return [b for g in groups for b in reading_order(g, gap)]


def gutter(blocks, gap):
    """x in the middle of the widest gap (at least `gap` wide) that no block crosses, or None."""
    best, right = None, None
    for x0, _, x1, _ in sorted(b["bbox"] for b in blocks):
        if right is not None and x0 - right >= gap and (best is None or x0 - right > best[1] - best[0]):
            best = (right, x0)
        right = x1 if right is None else max(right, x1)
    return None if best is None else (best[0] + best[1]) / 2


def line_metrics(lines, size):
    """(line height as a multiple of the font size, alignment: "justify", "center" or None) from a block's own
    lines."""
    if len(lines) < 2 or not size:
        return None, None
    baselines = [l["spans"][0]["origin"][1] for l in lines if l["spans"]]
    gaps = sorted(b - a for a, b in zip(baselines, baselines[1:]) if b > a)
    line_height = round(min(max(gaps[len(gaps) // 2] / size, 0.9), 3.0), 3) if gaps else None
    # Justified: (nearly) every line but the last ends at the block's right edge, or at the first line's edge
    # where the text wraps around a photo. A hyphen or a trailing space can move one line's edge by a point or two.
    rights = [l["bbox"][2] for l in lines[:-1]]
    justified = len(lines) >= 3 and sum(
        min(abs(e - r) for e in (max(rights), rights[0])) < 2.5 for r in rights
    ) >= 0.8 * len(rights)
    # Centred: the lines' middles line up while their left edges don't (a title or author list over two lines).
    lefts = [l["bbox"][0] for l in lines]
    middles = sorted((l["bbox"][0] + l["bbox"][2]) / 2 for l in lines)
    centred = max(lefts) - min(lefts) > 5 and all(abs(m - middles[len(middles) // 2]) < 3 for m in middles)
    return line_height, "center" if centred else "justify" if justified else None


DEFAULT_LINE_HEIGHT = 1.22  # render.css .ds-block line-height


def text_box(bbox, lines, size, line_height):
    """The box CSS needs to put each line on its PDF baseline: one line box (line height × size) per
    line, the first baseline half a line box plus ~0.34 em below the top (where Times, Arial and Noto
    centre their glyphs). PDF glyph boxes can be far shorter than the type (0.46 em for Libertine),
    which made the fitter shrink text that fits."""
    if not size or not lines:
        return bbox
    base = [max(l["spans"], key=lambda s: s["size"])["origin"][1] for l in lines if l["spans"]]
    half = (line_height or DEFAULT_LINE_HEIGHT) * size / 2
    return [bbox[0], min(base) - half - 0.34 * size, bbox[2], max(base) + half - 0.34 * size]


def same_column(a, b):
    """b continues a's column: same left edge, or (a line split across blocks) starting on a's last
    line and within its width."""
    size = b["style"].font_size or 10
    on_last_line = b["bbox"][1] < a["bbox"][3] - 0.5 * size
    return abs(a["bbox"][0] - b["bbox"][0]) < 2 or (
        on_last_line and a["bbox"][0] <= b["bbox"][0] and b["bbox"][2] <= a["bbox"][2] + 2
    )


def merge_continuations(blocks):
    """Re-join paragraphs the PDF split (e.g. where a superscript changed the line height)."""
    out = []
    for b in blocks:
        prev = out[-1] if out else None
        if (
            prev
            and prev["kind"] == b["kind"] == "text"
            and not prev["list"]
            and not b["list"]
            and not prev.get("fixed")
            and not b.get("fixed")
            and same_look(prev["style"], b["style"])
            and same_column(prev, b)
            and b["bbox"][1] - prev["bbox"][3] < 0.6 * (b["style"].font_size or 10)
            and b["bbox"][3] > prev["bbox"][3]
        ):  # below it, or overlapping it (one paragraph the PDF split)
            prev["lines"] = visual_lines(prev["lines"] + b["lines"])
            prev["text"] = join_lines(prev["lines"])
            prev["bbox"] = union([prev["bbox"], b["bbox"]])
            continue
        out.append(b)
    # Line spacing and alignment are measured on whole paragraphs (some PDFs store one block per line).
    for b in out:
        if b["kind"] == "text":
            b["style"].line_height, align = line_metrics(b["lines"], b["style"].font_size)
            b["bbox"] = text_box(b["bbox"], b["lines"], b["style"].font_size, b["style"].line_height)
            if align:
                b["style"].align = align
    return out


def text_block(lines, is_list):
    """A text block from its lines: box, joined text, dominant style, line height and alignment."""
    spans = [s for l in lines for s in l["spans"]]
    b = {
        "kind": "text",
        "bbox": union([l["bbox"] for l in lines]),
        "text": join_lines(lines),
        "style": dominant_style(spans),
        "list": is_list,
        "lines": lines,
    }
    b["style"].line_height, align = line_metrics(lines, b["style"].font_size)
    b["bbox"] = text_box(b["bbox"], lines, b["style"].font_size, b["style"].line_height)
    if align:
        b["style"].align = align
    return b
