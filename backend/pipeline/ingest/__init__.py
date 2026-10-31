"""PDF -> document model.

Text-layer path (free): PyMuPDF text, fonts and tables, labelled with font-size/position heuristics and the
pymupdf-layout model. The page background is rasterised with all text removed, so translated text sits on the
original graphics (table borders, coloured boxes, figures, bullets).

OCR path (costs Bodhan credits; run only on request): for scanned pages or garbled text layers. The page image goes
to indic-ocr, whose labelled blocks become the page's blocks. The original text can't be removed from a scan, so
each block gets a fill colour sampled from around it.

Modules, lowest layer first (each imports only from those above it in this list):

- `text`: spans, visual lines, joining and cleaning text
- `style`: font names and families, dominant style, styled runs
- `fonts`, `webfonts`: the PDF's embedded fonts as browser fonts
- `maths`: display equations and inline formula runs
- `tables`: ruled grids, label/value columns
- `raster`: page rasters, text-free backgrounds, sampled colours
- `blocks`: lines into blocks, merges, reading order
- `regions`: the layout model's regions; figures and photos
- `labels`: headings, running heads, footnotes, captions, furniture
- `ocr`: the OCR path
- `document`: `ingest_pdf`, the orchestration
"""

from .document import UnreadablePDF, ingest_pdf
from .ocr import ocr_page

__all__ = ["UnreadablePDF", "ingest_pdf", "ocr_page"]
