"""Text as PyMuPDF gives it: spans, visual lines, joining and cleaning, a few shared geometry helpers."""

import re
import unicodedata
from functools import cache

from nltk.corpus import wordnet

SUPERSCRIPT = str.maketrans("0123456789+-()=", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾⁼")


TAG = re.compile(r"<[^>]+>")


HYPHEN_END = re.compile(r"[a-zà-ÿ]-$")  # Latin only: Indic scripts don't hyphenate at line ends


LEADER_DOTS = re.compile(r"(?:\s*\.){4,}|(?:\s\.)+$")  # 4+ dots ("..." stays an ellipsis), or spaced dots at the end


def collapse_repeated_marks(text):
    """PyMuPDF sometimes emits an Indic vowel sign twice (e.g. "ग्राामीण"); a doubled identical
    combining mark is never valid, so keep one."""
    out = []
    for ch in text:
        if out and ch == out[-1] and unicodedata.category(ch) in ("Mn", "Mc"):
            continue
        out.append(ch)
    return "".join(out)


SUPERSCRIPT_FLAG, ITALIC_FLAG, BOLD_FLAG = 1, 2, 16


# ---------------------------------------------------------------- small helpers


def has_letters(text):
    """Whether the text has any letter."""
    return any(ch.isalpha() for ch in text)


def words(text):
    """How many words of 4+ letters (Indic vowel signs count; Python's \\w doesn't match them)."""
    return sum(sum(c.isalpha() or unicodedata.category(c)[0] == "M" for c in w) >= 4 for w in text.split())


def text_quality(text):
    """1.0 = clean Unicode text; lower = replacement/private-use characters or broken Indic shaping
    (a vowel sign starting a word means the extractor emitted glyphs in visual order)."""
    chars = [c for c in text if not c.isspace()]
    if len(chars) < 20:
        return 0.0
    bad = sum(1 for c in chars if c == "�" or 0xE000 <= ord(c) <= 0xF8FF or 0x80 <= ord(c) <= 0x9F)
    bad += sum(1 for word in text.split() if unicodedata.category(word[0]) in ("Mn", "Mc"))
    return round(1 - bad / len(chars), 4)


def hex_color(value):
    """A PyMuPDF colour int as "#rrggbb"; None for anything else."""
    return f"#{value:06x}" if isinstance(value, int) else None


def rect_center_in(bbox, outer, pad=1.0):
    """Whether the centre of `bbox` lies in `outer`, give or take `pad`."""
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return outer[0] - pad <= cx <= outer[2] + pad and outer[1] - pad <= cy <= outer[3] + pad


# ---------------------------------------------------------------- text-layer extraction


@cache
def english():
    """WordNet, or None when its data isn't installed (`make install` fetches it)."""
    try:
        wordnet.ensure_loaded()
    except LookupError:
        return None
    return wordnet


@cache
def lost_ligature(word):
    """`word` with the "fi", "fl" or "ff" that a PDF's broken Unicode map read as a bare "f" put back ("fnite" →
    "finite", "coeffcients" → "coefficients"), when only the repaired word is English."""
    wn = english()
    # WordNet has no function words: "of" would become "off".
    if wn is None or len(word) < 4 or word.isupper() or wn.morphy(word.lower()):
        return word
    for i, c in enumerate(word):
        for extra in "ilf" if c in "fF" else "":
            fixed = word[: i + 1] + extra + word[i + 1 :]
            if wn.morphy(fixed.lower()):
                return fixed
    return word


F_WORD = re.compile(r"[A-Za-z]*[fF][A-Za-z]*")
TEX_SYMBOLS = re.compile(r"CMSY\d")  # TeX's symbol font: its "0" is the prime (s′)


def span_text(span):
    """A span's text with lost ligatures put back, TeX's symbol-font "0" as a prime, and a superscript in Unicode
    superscripts."""
    text = F_WORD.sub(lambda m: lost_ligature(m.group()), span["text"])
    if TEX_SYMBOLS.search(span.get("font", "")):
        text = text.replace("0", "′")
    if span["flags"] & SUPERSCRIPT_FLAG and text.strip():
        return text.strip().translate(SUPERSCRIPT)
    return text


FOOTNOTE_MARKER = re.compile(r"^[\d*†‡§]+$")


def true_superscripts(line):
    """The line with the superscript flag only on spans smaller than its text. PyMuPDF's flag means "higher than
    the span before": everything after a lowered span (a fraction's denominator) has it, and a footnote's own
    marker, first on its line, doesn't. Only markers are raised by us: an OCR layer's words wobble in size and
    height."""
    size = max(s["size"] for s in line["spans"])
    base = next(s["origin"][1] for s in line["spans"] if s["size"] >= 0.9 * size)

    def raised(s):
        """Whether the span is set above the line: a smaller superscript, or a small raised footnote marker."""
        if s["flags"] & SUPERSCRIPT_FLAG:
            return s["size"] < 0.9 * size
        marker = FOOTNOTE_MARKER.match(s["text"].strip())
        return bool(marker) and s["size"] < 0.8 * size and base - s["origin"][1] > 0.15 * size

    spans = [{**s, "flags": s["flags"] & ~SUPERSCRIPT_FLAG | SUPERSCRIPT_FLAG * raised(s)} for s in line["spans"]]
    return {**line, "spans": spans}


def over(num, den, text):
    """`num` sits over `den` as a fraction: the same small size, overlapping columns, `den` just below `num`, and
    the line's `text` baseline between them."""
    width = min(num["bbox"][2] - num["bbox"][0], den["bbox"][2] - den["bbox"][0])
    overlap = min(num["bbox"][2], den["bbox"][2]) - max(num["bbox"][0], den["bbox"][0])
    return (
        len(den["text"].strip()) in range(1, 5)
        and abs(den["size"] - num["size"]) <= 0.1
        and overlap >= 0.5 * width
        and num["bbox"][3] - 0.3 * num["size"] <= den["bbox"][1] < num["bbox"][3] + 0.5 * num["size"]
        and num["origin"][1] < text["origin"][1] < den["origin"][1]
    )


def stacked_fractions(lines):
    """`lines` with each inline TeX fraction (a small numerator on a line of its own, over a small denominator
    in the text's line) made one span "2⁄3" in the text's line.
    shortcut: a numerator sharing its fragment with other text isn't found; widen if a PDF needs it."""
    out = list(lines)
    for top in lines:
        inked = [s for s in top["spans"] if s["text"].strip()]
        if len(inked) != 1 or len(inked[0]["text"].strip()) > 4:
            continue
        num = inked[0]
        for n, line in enumerate(out):
            spans = line["spans"]
            text = next((s for s in spans if s["text"].strip() and s["size"] >= 1.15 * num["size"]), None)
            i = next((i for i, den in enumerate(spans) if text and over(num, den, text)), None)
            if line is top or i is None:
                continue
            after = spans[i + 1]["text"][:1] if i + 1 < len(spans) else ""
            fraction = {
                **spans[i],
                "text": f"{num['text'].strip()}⁄{spans[i]['text'].strip()}" + (" " if after.isalnum() else ""),
                "bbox": tuple(union([num["bbox"], spans[i]["bbox"]])),
                "origin": (num["bbox"][0], text["origin"][1]),  # on the text's baseline
                "flags": spans[i]["flags"] & ~SUPERSCRIPT_FLAG,
            }
            out[n] = {
                **line,
                "spans": [*spans[:i], fraction, *spans[i + 1 :]],
                "bbox": union([line["bbox"], num["bbox"]]),
            }
            out = [l for l in out if l is not top]
            break
    return out


def visual_lines(lines):
    """Re-join line fragments on the same baseline (PyMuPDF splits lines at links and at broken
    Indic shaping, sometimes across blocks), top to bottom, each left to right. Fragments a column
    gap apart stay separate lines."""
    lines = [true_superscripts(l) for l in stacked_fractions(lines)]

    def base(l):
        """The baseline of the line's largest span."""
        return max(l["spans"], key=lambda s: s["size"])["origin"][1]

    rows = []  # fragments whose baselines are within half an em (scans are slightly skewed)
    for l in sorted(lines, key=base):
        size = max(s["size"] for s in l["spans"])
        if rows and base(l) - base(rows[-1][0]) < 0.5 * size:
            rows[-1].append(l)
        else:
            rows.append([l])
    out = []
    for row in rows:
        row.sort(key=lambda l: l["bbox"][0])
        out.append(row[0])
        for l in row[1:]:
            prev, size = out[-1], max(s["size"] for s in l["spans"])
            gap = l["bbox"][0] - prev["bbox"][2]
            if not -0.3 * size <= gap < size:
                out.append(l)
                continue
            spaced = prev["spans"][-1]["text"].endswith(" ") or l["spans"][0]["text"].startswith(" ")
            space = [{**l["spans"][0], "text": " "}] if gap > 0.1 * size and not spaced else []
            out[-1] = {**prev, "spans": prev["spans"] + space + l["spans"], "bbox": union([prev["bbox"], l["bbox"]])}
    return out


def join_lines(lines):
    """The lines' text as one cleaned string, with words hyphenated at a line end rejoined."""
    text = ""
    for l in lines:
        line = "".join(span_text(s) for s in l["spans"]).strip()
        if HYPHEN_END.search(text) and line[:1].islower():
            text = text[:-1] + line  # "improve-" + "ment": a word hyphenated at the line end
        else:
            text = f"{text} {line}" if text else line
    return clean_text(text)


def clean_text(text):
    """One spaced line: leader dots ("Total income . . . . 9") dropped, doubled vowel signs fixed."""
    text = "".join(c for c in text if unicodedata.category(c) != "Cc")  # glyphs with no Unicode mapping
    return collapse_repeated_marks(re.sub(r"\s+", " ", LEADER_DOTS.sub(" ", text)).strip())


def union(boxes):
    """The smallest box holding all `boxes`."""
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def horizontal(line):
    """Whether the line runs left to right, not rotated."""
    return line["dir"][0] > 0.99  # rotated text (an arXiv margin stamp, an axis label) is not


def baseline(line):
    """The y of the line's first baseline."""
    return line["spans"][0]["origin"][1]
