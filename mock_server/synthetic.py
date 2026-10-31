"""Deterministic fake outputs: placeholder text in the right script, and a plausible OCR page.

The text is gibberish, but it is in the target script and ~1.3x longer than the source, so
fonts, shaping and text expansion get exercised without spending credits.
"""

import hashlib
import random
import re
import unicodedata
from functools import cache

from .languages import LANG_SCRIPT

# Brahmic scripts share the ISCII-derived layout: same offsets inside each 128-char block.
BRAHMIC_BLOCKS = {
    "devanagari": 0x0900,
    "bengali": 0x0980,
    "gurmukhi": 0x0A00,
    "gujarati": 0x0A80,
    "oriya": 0x0B00,
    "tamil": 0x0B80,
    "telugu": 0x0C00,
    "kannada": 0x0C80,
    "malayalam": 0x0D00,
}
FULL_STOP = {"devanagari": "।", "bengali": "।", "gurmukhi": "।", "oriya": "।", "arabic": "۔"}

TOKEN_SPLIT = re.compile(r"(<[^>]*>|⟦\s*\d+\s*⟧|\s+)")  # keep HTML tags, formula placeholders and whitespace as-is


def _chars(start, end, categories, name_part=""):
    return [
        chr(c)
        for c in range(start, end)
        if unicodedata.category(chr(c)) in categories and name_part in unicodedata.name(chr(c), "")
    ]


@cache
def inventory(script):
    """(letters, vowel_signs) used to build pseudo-syllables for a script."""
    if script in BRAHMIC_BLOCKS:
        base = BRAHMIC_BLOCKS[script]
        return (_chars(base + 0x15, base + 0x3A, {"Lo"}), _chars(base + 0x3E, base + 0x4D, {"Mn", "Mc"}, "VOWEL SIGN"))
    if script == "arabic":
        return _chars(0x0628, 0x064B, {"Lo"}), []
    if script == "meetei":
        return _chars(0xABC0, 0xABDB, {"Lo"}), _chars(0xABE3, 0xABEB, {"Mn", "Mc"})
    if script == "olchiki":
        return _chars(0x1C5A, 0x1C78, {"Lo"}), []
    return list("bcdfghjklmnprstvwy"), list("aeiou")


def _pseudo_word(word, script, ratio):
    rng = random.Random(hashlib.sha256(f"{script}:{word}".encode()).digest())
    letters, signs = inventory(script)
    target = max(1, round(len(word) * ratio))
    out = []
    while len("".join(out)) < target:
        out.append(rng.choice(letters))
        if signs and rng.random() < 0.6:
            out.append(rng.choice(signs))
    return "".join(out)


def _is_punct(ch):
    return unicodedata.category(ch)[0] in "PS"


def pseudo_text(text, lang, ratio=1.3):
    """Replace every word with a deterministic fake word in `lang`'s script.

    Numbers, punctuation, whitespace and HTML tags survive unchanged, so tables and
    line structure stay intact.
    """
    script = LANG_SCRIPT.get(lang, "latin")
    parts = []
    for token in TOKEN_SPLIT.split(text):
        if not token or token.startswith(("<", "⟦")) or token.isspace():
            parts.append(token)
            continue
        start, end = 0, len(token)
        while start < end and _is_punct(token[start]):
            start += 1
        while end > start and _is_punct(token[end - 1]):
            end -= 1
        core = token[start:end]
        if not any(ch.isalpha() for ch in core):
            parts.append(token)
            continue
        tail = token[end:]
        if script in FULL_STOP:
            tail = tail.replace(".", FULL_STOP[script])
        parts.append(token[:start] + _pseudo_word(core, script, ratio) + tail)
    return "".join(parts)


SAMPLE_SENTENCES = [
    "The committee reviewed the annual report and approved the proposed budget.",
    "Students are required to submit the assignment before the end of the week.",
    "Rainfall in the northern districts was higher than the seasonal average.",
    "The new policy aims to improve access to primary healthcare in rural areas.",
    "All participants must register online at least two days before the event.",
    "The results indicate a steady improvement in literacy over the past decade.",
]

LABEL_TYPE = {
    "Section-title": "SectionHeader",
    "Paragraph": "Text",
    "Table": "Table",
    "Footnote": "Footnote",
    "Page-number": "PageNumber",
    "Footer": "PageFooter",
}


def ocr_blocks(image_sha, width, height, table_format="html"):
    """A plausible page layout: title, paragraphs, a small table, a footnote, page furniture."""
    rng = random.Random(image_sha)

    def para(n):
        """`n` random sample sentences as one paragraph."""
        return " ".join(rng.choice(SAMPLE_SENTENCES) for _ in range(n))

    if table_format == "markdown":
        table = "| Item | Quantity |\n| --- | --- |\n| Rice | 40 |\n| Wheat | 25 |"
    else:
        table = (
            "<table><tr><th>Item</th><th>Quantity</th></tr>"
            "<tr><td>Rice</td><td>40</td></tr><tr><td>Wheat</td><td>25</td></tr></table>"
        )
    layout = [  # (label, x0, y0, x1, y1 as page fractions, text)
        ("Section-title", 0.08, 0.06, 0.70, 0.11, f"Synthetic Page {image_sha[:6]}"),
        ("Paragraph", 0.08, 0.14, 0.92, 0.32, para(3)),
        ("Paragraph", 0.08, 0.34, 0.92, 0.50, para(2)),
        ("Table", 0.08, 0.53, 0.60, 0.70, table),
        ("Paragraph", 0.08, 0.73, 0.92, 0.84, para(2)),
        ("Footnote", 0.08, 0.87, 0.92, 0.91, "1. " + rng.choice(SAMPLE_SENTENCES)),
        ("Page-number", 0.90, 0.94, 0.94, 0.97, "1"),
        ("Footer", 0.05, 0.93, 0.95, 0.98, ""),
    ]
    return [
        {
            "order": i,
            "label": label,
            "type": LABEL_TYPE[label],
            "bbox_xyxy": [round(x0 * width, 1), round(y0 * height, 1), round(x1 * width, 1), round(y1 * height, 1)],
            "conf": round(rng.uniform(0.6, 0.95), 3),
            "text": text,
        }
        for i, (label, x0, y0, x1, y1, text) in enumerate(layout)
    ]
