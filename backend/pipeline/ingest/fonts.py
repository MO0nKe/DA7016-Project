"""The PDF's embedded fonts, extracted as files the browser can load to redraw text in its own face."""

import re

import pymupdf

from .style import font_name
from .webfonts import drawn_glyphs, webfont

# Reuse an embedded font only if its own text maps through its cmap; subsets of complex-script
# fonts often don't (glyphs are addressed by id), and half-mapped text would break shaping.
MIN_FONT_COVERAGE = 0.98


def extract_fonts(pdf, doc_dir):
    """Save browser-loadable versions of the embedded fonts that can draw this PDF's own text
    (see fonts.webfont). Returns {font name: relative path}. Type3 and non-embedded fonts are skipped."""
    chars = {}  # font name -> the characters it draws, as the extracted text has them
    for page in pdf:
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    chars.setdefault(font_name(s["font"]), set()).update(ch for ch in s["text"] if not ch.isspace())
    traced, metrics, names = {}, {}, {}  # xref -> {(codepoint, glyph id)}; name -> (ascender, descender); xref -> name
    for page in pdf:
        on_page, tagged = {}, {}  # name -> xrefs; xref -> name with its subset tag ("ABCDEF+Name")
        for xref, _ext, _type, basefont, *_ in page.get_fonts(full=True):
            on_page.setdefault(font_name(basefont), []).append(xref)
            tagged[xref] = basefont
        for span in page.get_texttrace():
            name = font_name(span["font"])
            # MuPDF cuts long names in the text it extracts ("…Std-Demi" -> "…Std-Dem").
            xrefs = on_page.get(name) or [
                x for n, xs in on_page.items() if len(name) >= 20 and n.startswith(name) for x in xs
            ]
            names.update((x, name) for x in xrefs)
            # The trace drops subset tags: two different subsets of one font on a page make glyph ids ambiguous.
            if len({tagged[x] for x in xrefs}) == 1:
                for x in xrefs:
                    traced.setdefault(x, set()).update((u, g) for u, g, *_ in span["chars"] if g > 0)
            metrics[name] = (span["ascender"], span["descender"])
    best = {}  # name -> (coverage, ext, buffer); a font can be embedded as several subsets
    for xref, name in names.items():
        used = chars.get(name)
        if not used:
            continue
        _, ext, _, buf = pdf.extract_font(xref)
        converted = webfont(ext, buf, drawn_glyphs(traced.get(xref, ())), *metrics[name]) if buf else None
        if not converted:
            continue
        buf, ext = converted
        try:
            font = pymupdf.Font(fontbuffer=buf)
        except Exception:  # a damaged font program: just don't reuse it
            continue
        coverage = sum(font.has_glyph(ord(ch)) > 0 for ch in used) / len(used)
        if coverage > best.get(name, (0,))[0]:
            best[name] = (coverage, ext, buf)
    out = {}
    for base, (coverage, ext, buf) in best.items():
        if coverage >= MIN_FONT_COVERAGE:
            rel = f"fonts/{re.sub(r'[^A-Za-z0-9_-]', '_', base)}.{ext}"
            (doc_dir / "fonts").mkdir(exist_ok=True)
            (doc_dir / rel).write_bytes(buf)
            out[base] = rel
    return out
