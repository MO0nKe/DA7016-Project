"""Tables: ruled grids, label/value columns and rows that share a line."""

import re
from collections import Counter

import pymupdf

from ...core.models import Cell
from .style import dominant_style, same_look
from .text import baseline, join_lines, union, visual_lines

FIELD_NUMBER = re.compile(r"^\(?\d+[a-z]?\)?(\s|$)|^[a-z]$")  # "(2) Last name", "11b", "b"


def wordless(line):
    """Exponents, equation numbers and stray symbols: no word of two or more letters."""
    return not re.search(r"[^\W\d_]{2}", "".join(s["text"] for s in line["spans"]))


def layout_grid(table):
    """A ruled form or a framed statement rather than a data table: mostly empty grid cells, or
    one cell holding most of it. Its text is laid out line by line, not as table cells."""
    cells = [c for row in table.rows for c in row.cells]
    filled = [pymupdf.Rect(c) for c in cells if c is not None]
    area = pymupdf.Rect(table.bbox).get_area()
    return len(filled) < 0.5 * len(cells) or max(c.get_area() for c in filled) > 0.5 * area


def pieces(line):
    """A line split where its spans are more than 1 em apart (form fields, statement columns)."""
    out = [[line["spans"][0]]]
    for s in line["spans"][1:]:
        prev = out[-1][-1]
        if s["bbox"][0] - prev["bbox"][2] > prev["size"]:
            out.append([])
        out[-1].append(s)
    return [
        {**line, "spans": run, "bbox": union([s["bbox"] for s in run])}
        for run in out
        if "".join(s["text"] for s in run).strip()
    ]


def shared_rows(page, ruled):
    """A ruled row that holds several label/value pairs (an infobox ruled only between groups), as one row per
    pair: a pair starts at each line of the first column with a value on its baseline, and a line running across
    a column edge, or alone in a value column but not where the values begin (a centred heading), is a row of its
    own. ({col: lines} above the first pair, [[(col, lines)]] per row), or None to keep the row."""
    if len(ruled) < 2:
        return None
    lines = visual_lines(
        [
            l
            for b in page.get_text("dict", clip=pymupdf.Rect(union([c for _, c in ruled])))["blocks"]
            if b["type"] == 0
            for l in b["lines"]
            if "".join(s["text"] for s in l["spans"]).strip()
        ]
    )
    edges = dict(ruled)
    col_of = lambda l: next((c for c, e in ruled if e[0] - 1 <= l["bbox"][0] < e[2]), ruled[-1][0])  # noqa: E731
    first, last = ruled[0][0], ruled[-1][0]
    beside = lambda l, cols: any(col_of(v) in cols and abs(baseline(v) - baseline(l)) < 3 for v in lines)  # noqa: E731
    labels = [l for l in lines if col_of(l) == first and beside(l, set(edges) - {first})]
    values = Counter(round(l["bbox"][0]) for l in lines if col_of(l) != first and beside(l, {first}))
    start = values.most_common(1)[0][0] if values else None  # where the values' text begins
    headings = [
        l
        for l in lines
        if col_of(l) != last
        and l["bbox"][2] > edges[col_of(l)][2] + 3  # across an edge
        or col_of(l) != first
        and start is not None
        and not beside(l, {first})
        and abs(l["bbox"][0] - start) > 5
    ]
    starts = sorted({baseline(l) for l in headings + labels})
    if len(starts) < 2:
        return None
    rows = [{} for _ in starts] + [{}]  # the last: lines above the first pair
    for l in sorted(lines, key=baseline):
        k = max([n for n, s in enumerate(starts) if s <= baseline(l) + 3], default=-1)
        if k < 0 and col_of(l) == first:
            k = 0
        rows[k].setdefault(col_of(l), []).append(l)  # k = -1: a value wrapped past the rule, kept with the row above
    return rows[-1], [sorted(r.items()) for r in rows[:-1] if r]


def label_value_tables(blocks):
    """Short labels down one edge with values beside them, line for line ("Stream:  IETF", a Wikipedia
    infobox's "जन्म  2 अक्टूबर 1869"), as a two-column table. The run of blocks starts at a block with
    lines at the label edge; any line further right is a value, wherever its block begins."""
    out, i = [], 0
    while i < len(blocks):
        run = []
        if blocks[i]["kind"] == "text" and not blocks[i]["list"] and not blocks[i].get("fixed"):
            edge = min(l["bbox"][0] for l in blocks[i]["lines"])
            for c in blocks[i:]:
                if not (
                    c["kind"] == "text"
                    and not c["list"]
                    and not c.get("fixed")
                    and all(abs(l["bbox"][0] - edge) < 3 or l["bbox"][0] > edge + 30 for l in c["lines"])
                ):
                    break
                run.append(c)
        lines = [l for c in run for l in c["lines"]]
        labels = [l for l in lines if abs(l["bbox"][0] - edge) < 3] if run else []
        values = [l for l in lines if not any(l is x for x in labels)]
        rows_apart = all(baseline(b) - baseline(a) > 2 for a, b in zip(labels, labels[1:]))
        beside = [
            min((v["bbox"][0] for v in values if abs(baseline(l) - baseline(v)) < 3), default=None) for l in labels
        ]
        starts = [
            x for x in beside if x is not None
        ]  # values start at one x, give or take a flag icon (not a garbled text layer)
        if (
            len(labels) < 3
            or not rows_apart
            or any(len(join_lines([l])) > 30 for l in labels)
            or len(starts) < 0.8 * len(labels)
            or max(starts) - min(starts) > 20
        ):
            out.append(blocks[i])
            i += 1
            continue
        cells = []
        for r, l in enumerate(labels):
            top, bottom = baseline(l) - 3, baseline(labels[r + 1]) - 3 if r + 1 < len(labels) else float("inf")
            row = [v for v in values if top <= baseline(v) < bottom]
            label = dominant_style(l["spans"])
            cells.append(
                Cell(
                    row=r,
                    col=0,
                    bbox=[round(v, 2) for v in l["bbox"]],
                    text=join_lines([l]),
                    header=label.bold,
                    style=label,
                )
            )  # infobox labels are bold
            if row:
                cells.append(
                    Cell(
                        row=r,
                        col=1,
                        bbox=[round(v, 2) for v in union([v["bbox"] for v in row])],
                        text=" ".join(join_lines([v]) for v in row),
                        style=dominant_style([s for v in row for s in v["spans"]]),
                    )
                )
        out.append(
            {
                "kind": "table",
                "bbox": union([c["bbox"] for c in run]),
                "cells": cells,
                "style": dominant_style([s for l in lines for s in l["spans"]]),
            }
        )
        i += len(run)
    return out


def rows_of(items):
    """Pieces grouped into rows: a piece joins the row whose first piece its middle lies in."""
    rows = []
    for p in sorted(items, key=lambda p: (p["bbox"][1], p["bbox"][0])):
        mid = (p["bbox"][1] + p["bbox"][3]) / 2
        row = next((r for r in rows[-3:] if r[0]["bbox"][1] <= mid <= r[0]["bbox"][3]), None)
        (row.append(p) if row is not None else rows.append([p]))
    return [sorted(r, key=lambda p: p["bbox"][0]) for r in rows]


def stacked(pieces):
    """A form's labels wrapped over several lines ("If more" / "than four" / "dependents,") as one piece
    each; a numbered field below ("(2) Last name") stays separate."""
    out = []
    for p in pieces:
        size = p["style"].font_size or 10
        above = next(
            (
                q
                for q in reversed(out)
                if abs(q["bbox"][0] - p["bbox"][0]) < 2
                and 0 <= p["bbox"][1] - q["bbox"][3] < 0.6 * size
                and same_look(q["style"], p["style"])
            ),
            None,
        )
        if above is None or FIELD_NUMBER.match(p["text"]):
            out.append(p)
            continue
        above["lines"] += p["lines"]
        above["text"] = join_lines(above["lines"])
        above["bbox"] = union([above["bbox"], p["bbox"]])
    return out


def grid_blocks(items):
    """A ruled grid's pieces as a table when they line up in columns (a financial statement), with
    one-cell rows above and below it (title, notes) as text; otherwise the pieces row by row (a form)."""
    rows = rows_of(items)
    spans = []  # column extents: x ranges of pieces in rows with 2+ pieces, merged where they overlap
    for x0, x1 in sorted((p["bbox"][0], p["bbox"][2]) for r in rows if len(r) > 1 for p in r):
        if spans and x0 < spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], x1)
        else:
            spans.append([x0, x1])
    multi = [i for i, r in enumerate(rows) if len(r) > 1]
    if len(spans) < 2 or len(multi) < 3 or len(multi) < 0.5 * len(rows):
        return stacked([p for r in rows for p in r])
    first, last = multi[0], multi[-1]
    body = []
    for r in rows[first : last + 1]:
        cells = {}
        for p in r:
            mid = (p["bbox"][0] + p["bbox"][2]) / 2
            col = next(
                (n for n, (x0, x1) in enumerate(spans) if x0 - 1 <= mid <= x1 + 1),
                next((n for n, (x0, x1) in enumerate(spans) if p["bbox"][0] < x1), len(spans) - 1),
            )
            cells.setdefault(col, []).append(p)
        prev = body[-1] if body else {}
        label = " ".join(p["text"] for p in prev.get(0, []))
        if (
            0 in prev
            and 0 in cells
            and (
                set(prev) == {0}
                and cells[0][0]["text"][:1].islower()
                or label.count("(") > label.count(")")
                and not set(prev) - {0} & set(cells)
            )
        ):
            for col, ps in body.pop().items():  # a label wrapped onto a second line: "...(of which" / "respectively)",
                cells[col] = ps + cells.get(col, [])  # "...(including ... as of" / "December 31, …)" with its note
            cells = dict(sorted(cells.items()))
        body.append(cells)
    table = [
        Cell(
            row=r,
            col=c,
            bbox=[round(v, 2) for v in union([p["bbox"] for p in ps])],
            text=" ".join(p["text"] for p in ps),
            header=r == 0,
            style=dominant_style([s for p in ps for l in p["lines"] for s in l["spans"]]),
        )
        for r, cells in enumerate(body)
        for c, ps in sorted(cells.items())
    ]
    spans_all = [s for r in rows[first : last + 1] for p in r for l in p["lines"] for s in l["spans"]]
    block = {
        "kind": "table",
        "bbox": union([c.bbox for c in table]),
        "cells": table,
        "style": dominant_style(spans_all),
    }
    return [p for r in rows[:first] for p in r] + [block] + [p for r in rows[last + 1 :] for p in r]
