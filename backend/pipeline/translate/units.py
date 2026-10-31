"""What is sent to Bodhan for each block: text pieces and units, sentences, formulas and markers taken out
and put back, text already in the target language, and English casing of the result."""

import html
import re
import unicodedata

from ...core.languages import detect_language, in_script_ratio
from ..markup import SUPERSCRIPTS, TAG_SPLIT, attach_markers, protect, restore, strip_markers, untagged

SENTENCE_END = re.compile(f"(?<=[.!?।॥۔])[{SUPERSCRIPTS}]*\\s+")


def prepare(block):
    """(the text sent for a text block, its formulas, its markers). Styled runs travel as their tags."""
    sent, formulas = protect(block.rich or block.text, block.maths)
    sent, marks = strip_markers(sent)
    return sent, formulas, marks


def finish(out, formulas, marks):
    """The translation of `prepare`'s text with markers and formulas back, or None if a formula was lost."""
    restored = restore(attach_markers(out, marks), formulas)
    return restored


BYTES = re.compile(r"^(?:(?:0x)?[0-9a-fA-F]{1,2}(?:\s+|$))+$")  # "7c", "b6 e3": S-box cells and byte dumps


def has_letters(text):
    """Worth translating: a word of two or more letters (vowel signs count, so Tamil "கை" is one), and not just
    hex bytes. A lone "A" or "7c" is a code."""

    def word(w):
        """Whether `w` is a word of two or more letters."""
        return any(c.isalpha() for c in w) and sum(c.isalpha() or unicodedata.category(c)[0] == "M" for c in w) >= 2

    return any(word(w) for w in text.split()) and not BYTES.match(text.strip())


def already_in(text, lang):
    """Whether `text` is already written in `lang` (an English quote in a Bengali page, into English): its script,
    and no other language detected in that script. Sent anyway, it comes back paraphrased or garbled.
    shortcut: short Latin text with few telling words counts as English (detect_language), so a short Spanish
    line isn't translated into English; fine for Indic and English sources, revisit for other European ones."""
    plain = untagged(text)
    return (in_script_ratio(plain, lang) or 0) >= 0.9 and detect_language(plain) in ((lang, None), (None, None))


LEAD = r"^((?:<[^>]*>|[^\w<])*)"  # tags, quotes and brackets before the first word


HEADINGS = {"Title", "Section-title"}


def english_case(text, heading=False):
    """English output from a caseless script, tidied: the first letter capitalised ("garden" -> "Garden"), and in a
    short heading the article the model added dropped ("The introduction" -> "Introduction"; Indic languages have
    none). A first word that is a URL, a number or mixed case ("iPhone") is left alone."""
    if heading and len(untagged(text).split()) <= 4:
        text = re.sub(LEAD + r"(?:the|a|an)\s+(?=\w)", r"\1", text, count=1, flags=re.I)
    return re.sub(
        LEAD + r"([a-z])(?=[a-z]*(?:[\s,.;:!?)'\"<]|$))(?![a-z]*://)",
        lambda m: m.group(1) + m.group(2).upper(),
        text,
        count=1,
    )


def sentences(text):
    """Split after sentence-final punctuation, keeping footnote markers with their sentence."""
    out, start = [], 0
    for m in SENTENCE_END.finditer(text):
        out.append(text[start : m.end()].strip())
        start = m.end()
    out.append(text[start:].strip())
    return [s for s in out if s]


def units(text, lang=None):
    """The strings sent to the model for one piece of text; mirrors translate_text."""
    return [strip_markers(text)[0].strip()] if has_letters(text) and not (lang and already_in(text, lang)) else []


def pieces(block):
    """The block's translatable text pieces, in order: cells, HTML text nodes, or the text."""
    if block.cells:
        return [c.text for c in block.cells]
    if block.html:
        return [html.unescape(p) for p in TAG_SPLIT.split(block.html) if p and not p.startswith("<")]
    return [prepare(block)[0]]


def units_of_block(block, lang=None):
    """Every string sent to the model to translate the block; mirrors translate_block."""
    return [u for p in pieces(block) for u in units(p, lang)]
