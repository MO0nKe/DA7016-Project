"""The OCR path (Bodhan indic-ocr, costs credits, run per page on request): a scanned page's labelled
blocks replace its blocks, each painted over the scan with a colour sampled from around it."""

import io
import re
import unicodedata

from PIL import Image

from ...core.models import Block, Style
from .labels import FIGURE_LABELS, NON_TRANSLATABLE
from .raster import sample_background
from .text import SUPERSCRIPT, TAG, has_letters, rect_center_in

OCR_HYPHEN = re.compile(r"(?<=[a-zà-ÿ])-\n(?=[a-zà-ÿ])")


OCR_INLINE_MATHS = re.compile(r"\$([^$\n]{1,20})\$")


OCR_SUPERSCRIPT = re.compile(r"\$+\s*\^\{?([0-9+\-()=]+)\}?\s*\$+")  # "$$^1$$" from indic-ocr


# ---------------------------------------------------------------- OCR path


def ocr_text(raw):
    """indic-ocr text with words hyphenated at line ends rejoined, "$$^1$$" made a real superscript and
    simple inline maths ("$\\theta$", "$C_D$") as plain symbols."""
    text = OCR_SUPERSCRIPT.sub(lambda m: m[1].translate(SUPERSCRIPT), OCR_HYPHEN.sub("", raw))
    return OCR_INLINE_MATHS.sub(lambda m: latex_symbols(m[1]), text).strip()


def latex_symbols(tex):
    """Simple LaTeX as plain text: Greek letter commands as the letters, subscripts flattened ("C_D" → "CD")."""

    def greek(m):
        """The Greek letter a command names, or the command unchanged."""
        case = "CAPITAL" if m[1][0].isupper() else "SMALL"
        try:
            return unicodedata.lookup(f"GREEK {case} LETTER {m[1].upper()}")
        except KeyError:
            return m[0]

    return re.sub(r"_\{?([^}\s]+)\}?", r"\1", re.sub(r"\\([A-Za-z]+)", greek, tex))


async def ocr_page(doc, page_index, store, bodhan):
    """Replace one page's blocks with Bodhan OCR output. Costs one indic-ocr call (cached afterwards)."""
    page = doc.pages[page_index]
    png = (store.dir(doc.id) / page.image).read_bytes()
    result = await bodhan.ocr(png, table_format="html")
    img = Image.open(io.BytesIO(png)).convert("RGB")
    to_pt = 72 / page.dpi
    figures = [b["bbox_xyxy"] for b in result.blocks if b["label"] in FIGURE_LABELS]
    blocks = []
    for n, b in enumerate(sorted(result.blocks, key=lambda b: b["order"])):
        bbox = [round(v * to_pt, 2) for v in b["bbox_xyxy"]]
        raw = b.get("text") or ""
        is_table = b["label"] == "Table" and "<t" in raw
        text = re.sub(r"\s+", " ", TAG.sub(" ", raw)).strip() if is_table else ocr_text(raw)
        blocks.append(
            Block(
                id=f"p{page_index}-o{n}",
                order=n,
                label=b["label"],
                type=b.get("type", "Text"),
                bbox=bbox,
                text=text,
                html=raw if is_table else None,
                style=Style(background=sample_background(img, bbox, page.dpi / 72), color="#111111"),
                source="ocr",
                translatable=bool(text) and b["label"] not in NON_TRANSLATABLE and has_letters(text),
                in_figure=b["label"] not in FIGURE_LABELS and any(rect_center_in(b["bbox_xyxy"], f) for f in figures),
            )
        )
    page.blocks = blocks
    page.source = "ocr"
    page.background = page.image  # the scan still contains the original text; blocks cover it
    return page
