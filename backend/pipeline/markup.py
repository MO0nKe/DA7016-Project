"""Inline markup inside block text, shared by every stage that reads or writes it.

- **Run tags:** words styled apart from their block travel as `<b>`, `<i>` and `<span style="color:#rrggbb">`
  (`Block.rich`, `Translation.rich`).
- **Footnote and citation markers** ("¹", "[²][³]") are taken out of text before translation and put back after
  their sentence; powers ("2⁸", "x⁶", "km²") are not markers and stay in place.
- **Formula placeholders:** inline formulas travel through translation as ⟦1⟧, ⟦2⟧… and are put back as their
  original text.
"""

import re

TAG_SPLIT = re.compile(r"(<[^>]+>)")
SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾⁼"

PLACEHOLDER = re.compile(r"⟦\s*(\d+)\s*⟧")
MARKERS = re.compile(f"(?:\\[?[{SUPERSCRIPTS}]+\\]?)+")  # "¹", "[²][³]"; strip_markers skips powers ("km²")
SENTENCE_BREAK = re.compile(r"(?<=[.!?।॥۔])\s+")


def formula_pattern(maths):
    """Regex for a block's formula texts, longest first. A formula that starts or ends with a letter must
    stand apart from other letters, so the variable "d" doesn't match inside "model"."""
    texts = sorted({m.text for m in maths}, key=len, reverse=True)
    if not texts:
        return None
    edge = lambda t: (r"(?<!\w)" if t[0].isalnum() else "") + re.escape(t) + (r"(?!\w)" if t[-1].isalnum() else "")  # noqa: E731
    return re.compile("|".join(edge(t) for t in texts))


def protect(text, maths):
    """(text with each formula swapped for ⟦n⟧, the formulas in order)."""
    pattern, found = formula_pattern(maths), []
    if pattern is None:
        return text, found

    def swap(m):
        """Record the formula and return its placeholder."""
        found.append(m.group(0))
        return f"⟦{len(found)}⟧"

    return "".join(
        p if p.startswith("<") else pattern.sub(swap, p) for p in TAG_SPLIT.split(text)
    ), found  # not "b" in <b>


UNITS = {"km", "cm", "mm", "m", "ft", "in", "mi", "yd", "s", "sec", "kg", "g"}  # "km²" is an exponent, not a footnote


def exponent(text, start):
    """Whether the superscript run at `start` is a power: right after a digit ("2⁸", "10⁹"), a formula, a lone letter
    ("x⁶") or a unit ("km²"), and not in brackets ("[²]" is a citation)."""
    before = re.sub(r"(?:<[^>]*>)+$", "", text[:start])  # "<i>x</i>⁶": the power of the italic x
    if text[start] == "[" or not before:
        return False
    if before[-1].isdigit() or before[-1] == "⟧":  # "2⁸", or a formula's placeholder ("⟦1⟧⁶" for x⁶)
        return True
    # A PDF can set a gap between a variable and its power ("−x ⁴"); after a whole word it's still a footnote.
    word = re.search(r"[^\W\d_]+(?=\s?$)", re.sub(r"(?:<[^>]*>)+(?=\s?$)", "", before))
    return bool(word) and (len(word.group()) == 1 or word.group().lower() in UNITS)


def strip_markers(text):
    """(text without footnote and citation markers, [(sentence number, marker)]). Live Bodhan drops placeholders
    that follow a full stop or a comma, which is where markers sit, so markers leave the text instead. Powers
    ("GF(2⁸)", "x⁶") stay where they are."""
    kept, marks, at = [], [], 0
    for m in MARKERS.finditer(text):
        if exponent(text, m.start()):
            continue
        kept.append(text[at : m.start()])
        at = m.end()
        first = not TAG_SPLIT.sub("", "".join(kept)).strip()  # a footnote's own number, before its text
        marks.append((-1 if first else len(SENTENCE_BREAK.findall("".join(kept).rstrip())), m.group(0)))
    return "".join(kept) + text[at:], marks


def attach_markers(text, marks):
    """`text` with each marker after its sentence (the last one, if the translation has fewer); a footnote's own
    number (sentence -1) first."""
    ends = [m.start() for m in SENTENCE_BREAK.finditer(text)] + [len(text.rstrip())]
    at = {}
    for k, mark in marks:
        at.setdefault(0 if k < 0 else ends[min(k, len(ends) - 1)], []).append(mark)
    for pos in sorted(at, reverse=True):
        text = text[:pos] + "".join(at[pos]) + text[pos:]
    return text


RUN_TAG = re.compile(r'</?(b|i|span)>|<span style="color:#[0-9a-f]{6}">')


def runs_intact(text):
    """Whether `text`'s tags are all ingest's run tags (Block.rich), each closed in order."""
    open_ = []
    for tag in TAG_SPLIT.split(text)[1::2]:
        m = RUN_TAG.fullmatch(tag)
        if not m:
            return False
        name = m.group(1) or "span"
        if not tag.startswith("</"):
            open_.append(name)
        elif not open_ or open_.pop() != name:
            return False
    return not open_


def untagged(text):
    """`text` with its tags stripped and runs of spaces collapsed."""
    return re.sub(r" {2,}", " ", re.sub(r"<[^>]*>", "", text)).strip()


def restore(text, formulas):
    """`text` with its placeholders put back, or None unless each came back exactly once."""
    numbers = sorted(int(n) for n in PLACEHOLDER.findall(text))
    if numbers != list(range(1, len(formulas) + 1)):
        return None
    return PLACEHOLDER.sub(lambda m: formulas[int(m.group(1)) - 1], text)
