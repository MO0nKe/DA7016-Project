"""Our side for the image-only scan: ingest, Bodhan OCR (live; cached after), flowing HTML.
Usage (repo root, project venv): ocr_naca.py <out dir>"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pymupdf

sys.path.insert(0, ".")
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("BODHAN_BASE_URL", "https://api.bodhan.ai")
os.environ.setdefault("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
from ours_html import page_html

from backend.clients import make_clients
from backend.core.config import load_settings
from backend.core.store import DocumentStore
from backend.pipeline.ingest import ingest_pdf, ocr_page


async def main(out):
    """Ingest and OCR the NACA scan, then write each page as flowing HTML to `out`."""
    f = "documents/en_scanned_naca-report-1381-image-only.pdf"
    store = DocumentStore(Path(tempfile.mkdtemp()))
    doc = ingest_pdf(Path(f).read_bytes(), Path(f).name, store)
    bodhan, openrouter = make_clients(load_settings())
    async with bodhan, openrouter:
        for p in doc.pages:
            if p.source == "pending_ocr":
                await ocr_page(doc, p.index, store, bodhan)
        print(bodhan.ledger.summary())
    pdf = pymupdf.open(f)
    for p in doc.pages:
        Path(out, f"{Path(f).stem}-p{p.index + 1}.html").write_text(page_html(pdf[p.index], p))
        print(p.index, p.source, len(p.blocks), "blocks", sorted({b.label for b in p.blocks}))


asyncio.run(main(sys.argv[1]))
