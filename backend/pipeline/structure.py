"""Structure review: a vision model checks how a text-layer page was split into blocks, and its fixes are applied.

The model (OpenRouter) sees the page raster with every block outlined and numbered, and a short list of the blocks.
It answers with fixes in five kinds; each is checked against the page before it is applied, using the PDF's own
lines through the ingest helpers, so the new blocks look like ingested ones:
  lines      one block per line: form fields, an author grid, items without bullets run together
  split      a new block starts at the given words: a missed paragraph break
  merge      consecutive blocks that are one paragraph (a line split off it)
  label      the right label for a block (a heading read as a paragraph)
  continues  block a's last sentence goes on in block b (the next column), or on the next page
Changed blocks lose their translations, so they are translated again. The fixes are kept on `Page.review`.
"""

import base64
import io
import json
import re

import pymupdf
from PIL import Image, ImageDraw

from ..core.models import Block
from .ingest.blocks import text_block
from .ingest.labels import NON_TRANSLATABLE, TYPE_OF
from .ingest.style import rich_text
from .ingest.text import has_letters, join_lines, rect_center_in, visual_lines

STRUCTURE_MODEL = "anthropic/claude-sonnet-5.5"
LABELS = [
    "Title",
    "Section-title",
    "Paragraph",
    "List",
    "Footnote",
    "Header",
    "Footer",
    "Page-number",
    "Image-caption",
    "Table-caption",
]

PROMPT = (
    """You check how one PDF page was split into text blocks before each block is translated on its own.
The image is the page with every block outlined in red and numbered. Below are the blocks: number | label |
lines | how the text starts ... and ends. Tables and text inside figures are listed but can't be changed.

Fix only clear mistakes, using the numbers:
- "lines": blocks that run together items each fixed in its own place on the page (form fields and their
  labels, a row of separate labels, list items without bullets): split into one block per line. Not for text
  that merely wraps (an author list or a paragraph): a longer translation must be able to re-wrap it.
- "split": a block holding several paragraphs, headings or items: the exact opening words (as written in the
  block's text) of each part after the first.
- "merge": groups of consecutive blocks that are one paragraph, one item or one wrapped list (a line split off
  it, an author list in pieces). Never across an equation, a figure or a gap: those stay separate blocks.
- "label": blocks with a wrong label. Labels: """
    + ", ".join(LABELS)
    + """.
- "continues": pairs [a, b] where block a's last sentence goes on in block b (the next column, or after a figure).
- "next_page": blocks whose last sentence goes on at the top of the next page.

Reply with JSON only, empty lists where the page is fine:
{"lines": [n, ...], "split": [{"block": n, "starts": ["opening words", ...]}], "merge": [[n, n, ...]],
 "label": {"n": "Label"}, "continues": [[a, b]], "next_page": [n]}"""
)


def page_lines(pdf_page):
    """The page's text lines, as ingest reads them."""
    flags = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_DEHYPHENATE
    return [
        l
        for b in pdf_page.get_text("dict", flags=flags)["blocks"]
        if b["type"] == 0
        for l in b["lines"]
        if "".join(s["text"] for s in l["spans"]).strip()
    ]


def lines_of(block, lines):
    """A text block's own visual lines, top to bottom: inside its box and part of its text (a form block's box
    also covers line numbers and leader dots that are blocks of their own)."""
    own = squash(block.text)
    return [
        l
        for l in visual_lines([l for l in lines if rect_center_in(l["bbox"], block.bbox)])
        if has_letters(t := squash(join_lines([l])).rstrip("-")) and t in own
    ]  # not a leader dot or a line
    # number; "improve-" is in "improvement"


def overlay(png, blocks, scale, max_side=1600):
    """The page raster with each block outlined and numbered from 1, as a JPEG data URL."""
    img = Image.open(io.BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(img)
    for n, b in enumerate(blocks, 1):
        x0, y0, x1, y1 = (v * scale for v in b.bbox)
        draw.rectangle([x0, y0, x1, y1], outline=(220, 0, 0), width=2)
        draw.rectangle([x0, max(0, y0 - 14), x0 + 8 + 8 * len(str(n)), y0], fill=(220, 0, 0))
        draw.text((x0 + 3, max(0, y0 - 13)), str(n), fill=(255, 255, 255))
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def listing(blocks, lines):
    """The blocks as numbered rows for the review prompt: label, line count and text (long text shortened); tables and
    figure text marked as fixed."""
    rows = []
    for n, b in enumerate(blocks, 1):
        if b.cells or b.html or b.in_figure:
            rows.append(f"{n} | {'Table' if b.cells or b.html else 'Figure text'} | can't be changed")
            continue
        text = b.text.replace("\n", " ")
        shown = text if len(text) <= 120 else f"{text[:70]} ... {text[-45:]}"
        rows.append(f"{n} | {b.label} | {len(lines_of(b, lines))} | {shown}")
    return "\n".join(rows)


def parse(reply, count):
    """The model's fixes with every block number checked (1..count), or empty fixes."""
    m = re.search(r"\{.*\}", reply, re.S)
    try:
        raw = json.loads(m.group(0)) if m else {}
    except ValueError:
        raw = {}
    ok = lambda n: isinstance(n, int) and 1 <= n <= count  # noqa: E731
    return {
        "lines": [n for n in raw.get("lines", []) if ok(n)],
        "split": [
            {"block": s["block"], "starts": [t for t in s.get("starts", []) if isinstance(t, str) and t.strip()]}
            for s in raw.get("split", [])
            if isinstance(s, dict) and ok(s.get("block"))
        ],
        "merge": [g for g in raw.get("merge", []) if isinstance(g, list) and len(g) > 1 and all(ok(n) for n in g)],
        "label": {
            int(k): v for k, v in raw.get("label", {}).items() if str(k).isdigit() and ok(int(k)) and v in LABELS
        },
        "continues": [
            p for p in raw.get("continues", []) if isinstance(p, list) and len(p) == 2 and all(ok(n) for n in p)
        ],
        "next_page": [n for n in raw.get("next_page", []) if ok(n)],
    }


def squash(text):
    """`text` lower-cased with its whitespace collapsed, for comparing texts."""
    return re.sub(r"\s+", " ", text).strip().lower()


def piece(parent, lines, n):
    """A block made of some of `parent`'s lines, styled and labelled like it."""
    b = text_block(lines, parent.label == "List")
    style = b["style"].model_copy(update={"background": parent.style.background, "mark_color": parent.style.mark_color})
    return Block(
        id=f"{parent.id}s{n}",
        order=parent.order,
        label=parent.label,
        type=parent.type,
        bbox=[round(v, 2) for v in b["bbox"]],
        text=b["text"],
        rich=rich_text(lines, style, b["text"]),
        style=style,
        source=parent.source,
        translatable=parent.translatable and has_letters(b["text"]),
        in_figure=parent.in_figure,
        maths=[m for m in parent.maths if m.text in b["text"]],
    )


def stacked(members):
    """Blocks directly above one another, at most a line apart: one paragraph in pieces. A display equation or a
    figure between two paragraphs leaves a larger gap, and a merged box would be drawn over it."""
    ordered = sorted(members, key=lambda m: m.bbox[1])
    return all(b.bbox[1] - a.bbox[3] < 1.0 * (a.style.font_size or 10) for a, b in zip(ordered, ordered[1:]))


def covers(block, parts):
    """Whether the new blocks keep all of the block's words (a line the matching missed would be lost)."""
    return len(squash(" ".join(p.text for p in parts))) >= 0.97 * len(squash(block.text))


def apply(page, fixes, lines):
    """Apply checked fixes to `page.blocks` in place; returns the fixes that took effect (by block id)."""
    blocks = sorted(page.blocks, key=lambda b: b.order)
    text_blocks = {n: b for n, b in enumerate(blocks, 1) if not (b.cells or b.html or b.in_figure) and b.text}
    done = {"lines": [], "split": [], "merge": [], "label": {}, "continues": [], "next_page": []}
    replace = {}  # block id -> blocks in its place ([] for blocks merged away)

    for n in fixes["lines"]:
        b, ls = text_blocks.get(n), lines_of(text_blocks[n], lines) if n in text_blocks else []
        if b and len(ls) > 1 and covers(b, parts := [piece(b, [l], k) for k, l in enumerate(ls)]):
            replace[b.id] = parts
            replace[b.id][-1].room = b.room
            done["lines"].append(b.id)
    for s in fixes["split"]:
        b = text_blocks.get(s["block"])
        if not b or b.id in replace:
            continue
        ls = lines_of(b, lines)
        starts = [squash(t)[:20] for t in s["starts"]]
        groups = [[]]
        for l in ls:
            head = squash("".join(sp["text"] for sp in l["spans"]))
            if groups[-1] and any(head.startswith(t) for t in starts):
                groups.append([])
            groups[-1].append(l)
        if len(groups) > 1 and covers(b, parts := [piece(b, g, k) for k, g in enumerate(groups)]):
            replace[b.id] = parts
            replace[b.id][-1].room = b.room
            done["split"].append(b.id)
    for group in fixes["merge"]:
        members = [text_blocks.get(n) for n in sorted(group)]
        if any(m is None or m.id in replace for m in members) or not stacked(members):
            continue
        ls = [l for m in members for l in lines_of(m, lines)]
        merged = piece(members[0], visual_lines(ls), 0) if ls else None
        if merged and len(squash(merged.text)) >= 0.97 * len(squash(" ".join(m.text for m in members))):
            merged.translatable = any(m.translatable for m in members) and has_letters(merged.text)
            merged.room = max(members, key=lambda m: m.bbox[3]).room
            replace[members[0].id] = [merged]
            replace.update({m.id: [] for m in members[1:]})
            done["merge"].append([m.id for m in members])

    out = []
    for b in blocks:
        out += replace.get(b.id, [b])
    for k, b in enumerate(out):
        b.order = k
    page.blocks = out

    first = {b.id: b for b in out}
    for n, label in fixes["label"].items():
        b = text_blocks.get(n)
        if b and b.id in first and b.label != label:
            b.label, b.type = label, TYPE_OF.get(label, "Text")
            b.translatable = label not in NON_TRANSLATABLE and has_letters(b.text)
            done["label"][b.id] = label
    for a, c in fixes["continues"]:
        x, y = text_blocks.get(a), text_blocks.get(c)
        if x and y and x.id in first and y.id in first and x.id != y.id:
            x.continues = y.id
            done["continues"].append([x.id, y.id])
    for n in fixes["next_page"]:
        b = text_blocks.get(n)
        if b and b.id in first:
            b.continues = "next-page"
            done["next_page"].append(b.id)
    changed = (
        set(done["lines"])
        | set(done["split"])
        | {i for g in done["merge"] for i in g}
        | {i for p in done["continues"] for i in p}
        | set(done["next_page"])
    )  # a pair is translated together
    for b in out:
        if b.id in changed or b.id.rsplit("s", 1)[0] in changed:
            b.translations = {}
    return done


async def review_page(doc, page_index, store, openrouter, model=STRUCTURE_MODEL):
    """Ask the model about one text-layer page and apply its fixes. Returns the fixes applied."""
    page = doc.pages[page_index]
    if page.source != "text_layer" or not page.blocks:
        return None
    with pymupdf.open(store.dir(doc.id) / "source.pdf") as pdf:
        lines = page_lines(pdf[page_index])
    blocks = sorted(page.blocks, key=lambda b: b.order)
    png = (store.dir(doc.id) / page.image).read_bytes()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT + "\n\nBlocks:\n" + listing(blocks, lines)},
                {"type": "image_url", "image_url": {"url": overlay(png, blocks, page.dpi / 72)}},
            ],
        }
    ]
    result = await openrouter.chat(messages, model=model, max_tokens=2000, temperature=0)
    done = apply(page, parse(result.text, len(blocks)), lines)
    page.review = {"model": model, "cost_usd": result.cost_usd, **done}
    return done


def link_next_pages(doc):
    """Resolve "next-page" continuations to the first body block of the next page."""
    for i, page in enumerate(doc.pages):
        for b in page.blocks:
            if b.continues == "next-page":
                following = doc.pages[i + 1].blocks if i + 1 < len(doc.pages) else []
                target = next(
                    (
                        c
                        for c in sorted(following, key=lambda c: c.order)
                        if c.label in ("Paragraph", "List") and c.text and not (c.cells or c.html)
                    ),
                    None,
                )
                b.continues = target.id if target else None
