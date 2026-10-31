"""How text looks: font names and families, a block's dominant style, styled runs (Block.rich)."""

import re
from collections import Counter

from ...core.models import Style
from .text import BOLD_FLAG, ITALIC_FLAG, SUPERSCRIPT_FLAG, TAG, clean_text, hex_color, join_lines, span_text

MONO_FONTS = ("mono", "courier", "consola", "inconsolata", "menlo", "code", "nimbusmon", "typewriter")


SANS_FONTS = (
    "sans",
    "helvetica",
    "arial",
    "franklin",
    "gothic",
    "segoe",
    "calibri",
    "aptos",
    "verdana",
    "tahoma",
    "roboto",
    "inter",
    "frutiger",
    "myriad",
    "gill",
    "futura",
    "avenir",
    "univers",
    "dejavusans",
    "nimbussan",
    "lato",
    "montserrat",
    "candara",
    "trebuchet",
    "century gothic",
    "grotesk",
)


SERIF_FONTS = (
    "serif",
    "times",
    "roman",
    "georgia",
    "garamond",
    "libertine",
    "cambria",
    "minion",
    "palatino",
    "book",
    "baskerville",
    "caslon",
    "bodoni",
    "charter",
    "utopia",
    "cmr",
    "lmroman",
    "nimbusrom",
    "sabon",
    "constantia",
    "didot",
    "bembo",
    "mincho",
)


# TeX and OpenType maths fonts. Not "Symbol": Word documents use it for bullets and Greek in prose.
MATH_FONT = re.compile(
    r"math|^(cm(mi|sy|ex|bsy)|ms(am|bm)|tx(mi|sy|ex)|px(mi|sy|ex)|eu(fm|sm|ex)|rsfs|esint|wasy)", re.I
)


def font_name(font):
    """The PDF font name without its subset prefix."""
    return font.split("+")[-1]  # "ABCDEF+Calibri-Bold" -> "Calibri-Bold"


def family_of(font):
    """serif / sans / mono from the PDF font name (PyMuPDF's serif flag is unreliable: it marks
    Helvetica and Noto Sans as serif). Unknown names default to serif, as most body text is."""
    name = font.lower().split("+")[-1]  # drop a subset prefix like ABCDEF+
    if any(k in name for k in MONO_FONTS):
        return "mono"
    if any(k in name for k in SANS_FONTS):  # before serif: "sans" wins over "serif" in "NotoSansSerif"…
        return "sans"
    if any(k in name for k in SERIF_FONTS):
        return "serif"
    return "serif"


def dominant_style(spans):
    """Char-weighted majority style of the non-superscript spans."""
    body = [s for s in spans if not s["flags"] & SUPERSCRIPT_FLAG and s["text"].strip()] or spans

    def vote(key):
        """The value of `key` over the most characters."""
        c = Counter()
        for s in body:
            c[key(s)] += len(s["text"].strip())
        return c.most_common(1)[0][0]

    return Style(
        font_size=round(vote(lambda s: round(s["size"] * 2) / 2), 1),
        bold=vote(lambda s: bool(s["flags"] & BOLD_FLAG)),
        italic=vote(lambda s: bool(s["flags"] & ITALIC_FLAG)),
        color=vote(lambda s: hex_color(s.get("color"))),
        family=vote(lambda s: family_of(s.get("font", ""))),
        font=vote(lambda s: font_name(s.get("font", ""))) or None,
    )


def size_change(a, b):
    """A heading and its paragraph in one PDF block: the text size changes by more than 15%."""
    sa, sb = (dominant_style(l["spans"]).font_size or 1 for l in (a, b))
    return max(sa, sb) > 1.15 * min(sa, sb)


def run_tags(span, style):
    """(opening, closing) tags for a span drawn bolder, in italics or in another colour than its block."""
    if (
        span["flags"] & SUPERSCRIPT_FLAG
        or not any(c.isalnum() for c in span["text"])
        or MATH_FONT.search(font_name(span.get("font", "")))
    ):
        return "", ""  # markers and formulas travel on their own; an italic comma isn't worth a tag
    tags = []
    color = hex_color(span.get("color"))
    if color and color != style.color:
        tags.append(("span", f'<span style="color:{color}">'))
    if span["flags"] & BOLD_FLAG and not style.bold:
        tags.append(("b", "<b>"))
    if span["flags"] & ITALIC_FLAG and not style.italic:
        tags.append(("i", "<i>"))
    return "".join(t for _, t in tags), "".join(f"</{n}>" for n, _ in reversed(tags))


RUN_SEAM = re.compile(r"((?:</[a-z]+>)+)(\s*)((?:<[a-z][^>]*>)+)")


def rich_text(lines, style, text):
    """`text` with inline tags around runs styled apart from `style` ("<b>Note:</b> the…"), or None when no
    run is, or when the tags would not strip back to exactly `text`."""
    tagged = []
    for l in lines:
        spans = []
        for s in l["spans"]:
            body, (start, end) = span_text(s), run_tags(s, style)
            core = body.strip()
            spans.append(
                {
                    **s,
                    "flags": s["flags"] & ~SUPERSCRIPT_FLAG,  # span_text already raised it
                    "text": body.replace(core, f"{start}{core}{end}", 1) if start and core else body,
                }
            )
        tagged.append({**l, "spans": spans})
    closing = lambda opening: "".join(f"</{n}>" for n in reversed(re.findall(r"<([a-z]+)", opening)))  # noqa: E731
    rich = RUN_SEAM.sub(lambda m: m.group(2) if closing(m.group(3)) == m.group(1) else m.group(0), join_lines(tagged))
    if "<" not in rich or clean_text(TAG.sub("", rich)) != text:
        return None
    return rich


def same_look(a, b):
    """Two blocks typeset the same way (line spacing and alignment may differ on one-line pieces)."""
    keys = ("font_size", "bold", "italic", "color", "family", "font")
    return all(getattr(a, k) == getattr(b, k) for k in keys)
