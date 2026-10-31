"""Mathematics: display equations, inline formula runs (cropped from the page and drawn as images)."""

import re

from .style import MATH_FONT, font_name
from .text import ITALIC_FLAG, clean_text, span_text, union, words

MATHS_DPI = 300  # inline formula crops, sharp at the studio's zoom


def is_maths(lines):
    """Set in maths fonts with at most one real word around it: a display equation, or a figure
    label (often without a usable Unicode mapping). Drawn as-is; re-typesetting maths as running
    text breaks it. TeX sets digits, brackets and "exp" in the roman font, so count words, not chars."""
    spans = [s for l in lines for s in l["spans"]]
    maths = [bool(MATH_FONT.search(font_name(s["font"]))) for s in spans]
    prose = sum(words(s["text"]) for s, m in zip(spans, maths) if not m)
    return any(m and s["text"].strip() for s, m in zip(spans, maths)) and prose <= 1


def maths_line(line):
    """One line of a display equation: at most one real word, and a quarter of it maths-font
    characters or one- and two-letter italic variables (FIPS sets x in Times Italic, + in CMR10)."""
    spans = [s for s in line["spans"] if s["text"].strip()]
    chars = sum(len(s["text"].strip()) for s in spans)
    maths = sum(
        len(s["text"].strip())
        for s in spans
        if MATH_FONT.search(font_name(s["font"])) or s.get("flags", 0) & ITALIC_FLAG and len(s["text"].strip()) <= 2
    )
    prose = sum(words(s["text"]) for s in spans if not MATH_FONT.search(font_name(s["font"])))
    return chars > 0 and prose <= 1 and maths >= 0.25 * chars


MATHS_CHAR = re.compile(r"[Ͱ-Ͽ∀-⋿⟀-⟯⦀-⫿\U0001d400-\U0001d7ff∂∇ℎℓ′″⁄]")  # ⁄: a stacked fraction (text.stacked_fractions)


MATHS_BRIDGE = re.compile(r"^[\s()\[\]{}|,.=+\-−0-9]+$")  # spaces, brackets, digits or operators between maths spans


def maths_runs(lines):
    """Inline formulas in a block's lines, as [(text, bbox, descent)], the way PDFMathTranslate finds them.
    A span is maths when it is set in a maths font, or is only symbols, Greek and maths letters. Smaller
    spans next to maths (sub- and superscripts) and short bits between two maths spans (brackets, digits)
    join it. A run is kept only when it would not survive as plain text: it uses a maths font or maths
    letters, or has two or more characters with a symbol. A lone "×" in the body font, or maths-font
    punctuation, stays text."""
    runs = []
    for line in lines:
        spans, inked = line["spans"], [s for s in line["spans"] if s["text"].strip()]
        if not inked:
            continue
        size = max(s["size"] for s in inked)
        baseline = next(s["origin"][1] for s in inked if s["size"] >= 0.9 * size)
        font = [bool(s["text"].strip() and MATH_FONT.search(font_name(s["font"]))) for s in spans]
        maths = [
            f
            or (
                bool(MATHS_CHAR.search(s["text"]))
                and not any(c.isalpha() and not MATHS_CHAR.match(c) for c in s["text"])
            )
            for f, s in zip(font, spans)
        ]
        for _ in range(2):  # twice, so x₁₂ and A⁽ᵀ⁾ chains join
            for i, s in enumerate(spans):
                near = (i and maths[i - 1]) or (i + 1 < len(spans) and maths[i + 1])
                if not maths[i] and near and s["text"].strip() and s["size"] < 0.79 * size:
                    maths[i] = True
        for i in range(1, len(spans)):  # bridges: a row of brackets, spaces and digits between two maths spans
            if maths[i - 1] and not maths[i]:
                j = i
                while j < len(spans) and not maths[j] and MATHS_BRIDGE.match(spans[j]["text"]):
                    j += 1
                if j < len(spans) and maths[j]:
                    maths[i:j] = [True] * (j - i)
        i = 0
        while i < len(spans):
            if not maths[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(spans) and maths[j + 1]:
                j += 1
            run = spans[i : j + 1]
            text = clean_text("".join(span_text(s) for s in run))
            worth = (
                any(font[i : j + 1])
                or re.search(r"[\U0001d400-\U0001d7ffℎ]", text)
                or len(text) > 1
                and MATHS_CHAR.search(text)
            )
            if worth and (MATHS_CHAR.search(text) or any(c.isalpha() for c in text)):
                box = union([s["bbox"] for s in run if s["text"].strip()])
                runs.append((text, [round(v, 2) for v in box], round(box[3] - baseline, 2)))
            i = j + 1
    return runs
