"""Turn a PDF's embedded fonts into fonts a browser loads: TrueType/OpenType get a Unicode cmap,
bare CFF and Type1 programs are wrapped in OpenType. PDF subsets often address glyphs by id or by
name only, so the cmap is rebuilt from what the PDF itself draws (or, for Type1, from glyph names)."""

import io
import logging

from fontTools import agl
from fontTools.cffLib import CFFFontSet
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.t1Lib import T1Font
from fontTools.ttLib import TTFont

logging.getLogger("fontTools").setLevel(logging.ERROR)  # PDF subsets trip many harmless warnings


def simple(u):
    """Not a complex script (Hebrew/Arabic through the Indic scripts to Mongolian), where a drawn
    glyph is often a conjunct or reordered form and mapping a letter to it would garble the text."""
    return not 0x0590 <= u < 0x1E00


def names_cmap(order):
    """{codepoint: glyph} from glyph names, where the font has real ones ("A", "uni0915"; not
    "cid00042" or an alternate like "a.sc")."""
    cmap = {}
    for glyph in order:
        text = "" if "." in glyph[1:] else agl.toUnicode(glyph)
        if len(text) == 1 and simple(ord(text)):
            cmap.setdefault(ord(text), glyph)
    return cmap


def drawn_glyphs(pairs):
    """{codepoint: glyph id} from traced (codepoint, glyph id) pairs. A glyph traced for several
    codepoints is a ligature (PyMuPDF gives "fi" as f and i on one glyph): mapping a letter to it
    would draw "fi" for every "f"."""
    by_glyph = {}
    for u, g in pairs:
        by_glyph.setdefault(g, set()).add(u)
    return {u: g for g, us in by_glyph.items() if len(us) == 1 for u in us}


def webfont(ext, buf, drawn, ascender=0.8, descender=-0.2):
    """(font bytes, "ttf" | "otf"), or None if the program can't be read.

    `drawn`: {codepoint: glyph id} as PyMuPDF traced this font's text (glyph ids index the font's
    own glyph order for TrueType and CFF), without ligature glyphs (see drawn_glyphs). `ascender`/`descender`: em
    fractions, from the PDF."""
    try:
        if ext in ("ttf", "otf"):
            return with_cmap(buf, drawn), ext
        if ext == "cff":
            return from_outlines(*cff_glyphs(buf), drawn, ascender, descender), "otf"
        if ext in ("pfa", "pfb"):
            return from_outlines(*type1_glyphs(buf), None, ascender, descender), "otf"
    except Exception:  # a damaged or unusual font program: the text falls back to a system font
        return None
    return None


def with_cmap(buf, drawn):
    """A TrueType or OpenType font with its cmap filled from glyph names and the drawn text, and the tables Chrome needs
    added."""
    font = TTFont(io.BytesIO(buf))
    for tag in [t for t in font.reader.tables if font.reader.tables[t].length == 0]:
        del font[tag]  # subsetters leave empty tables (e.g. cvt); Chrome rejects the whole font
    order = font.getGlyphOrder()
    cmap = {**names_cmap(order), **(font.getBestCmap() or {})} if "cmap" in font else names_cmap(order)
    for u, g in drawn.items():  # only fill gaps: the font's own cmap is right where it has one
        if u not in cmap and simple(u) and g < len(order):
            cmap[u] = order[g]
    fb = FontBuilder(font=font)
    fb.setupCharacterMap(cmap)
    name = font["name"].getBestFullName() if "name" in font else None
    if not name:  # Chrome rejects fonts without these tables; PDF subsets often drop them
        fb.setupNameTable({"familyName": "PDF font", "styleName": "Regular"})
    if "OS/2" not in font:
        fb.setupOS2()
    if "post" not in font:
        fb.setupPost()
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()


def cff_glyphs(buf):
    """(glyph order, glyphs, units per em, PostScript name) of a bare CFF program."""
    cff = CFFFontSet()
    cff.decompile(io.BytesIO(buf), None)
    top = cff[cff.fontNames[0]]
    return top.charset, top.CharStrings, round(1 / top.FontMatrix[0]), cff.fontNames[0]


def type1_glyphs(buf):
    """(glyph order, glyphs, units per em, PostScript name) of a Type 1 program."""
    font = T1Font.__new__(T1Font)  # T1Font only reads from a path
    font.data, font.encoding = buf, "ascii"
    font.parse()
    glyphs = font.getGlyphSet()
    order = [".notdef"] + [n for n in font.font["CharStrings"] if n != ".notdef"]
    name = font.font.get("FontName", "Type1").split("+")[-1]
    return order, glyphs, round(1 / font.font.get("FontMatrix", [0.001])[0]), name


def from_outlines(order, glyphs, upem, name, drawn, ascender, descender):
    """An OpenType-CFF font from glyph outlines."""
    charstrings, metrics = {}, {}
    for glyph in order:
        rec = RecordingPen()
        glyphs[glyph].draw(rec)  # also sets the width of CFF glyphs
        width = round(glyphs[glyph].width)
        pen, bounds = T2CharStringPen(width, None), BoundsPen(None)
        rec.replay(pen)
        rec.replay(bounds)
        charstrings[glyph] = pen.getCharString()
        metrics[glyph] = (width, round(bounds.bounds[0]) if bounds.bounds else 0)
    cmap = names_cmap(order)
    for u, g in (drawn or {}).items():  # then what the PDF draws, for the rest
        if u not in cmap and simple(u) and g < len(order):
            cmap[u] = order[g]
    ascent, descent = round(ascender * upem), round(descender * upem)
    fb = FontBuilder(upem, isTTF=False)
    fb.setupGlyphOrder(list(order))
    fb.setupCharacterMap(cmap)
    fb.setupCFF(name, {"FullName": name}, charstrings, {})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ascent, descent=descent)
    fb.setupNameTable({"familyName": name, "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=ascent, sTypoDescender=descent, usWinAscent=ascent, usWinDescent=-descent)
    fb.setupPost()
    out = io.BytesIO()
    fb.save(out)
    return out.getvalue()
