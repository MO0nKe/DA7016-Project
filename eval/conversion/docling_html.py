"""Docling's own HTML export, one file per page (for the conversion comparison).
Usage (Docling venv): docling_html.py <out dir> <pdf>..."""

import sys
import time
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ImageRefMode

options = PdfPipelineOptions(do_ocr=True, do_table_structure=True, generate_picture_images=True, images_scale=1.5)
converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
for f in sys.argv[2:]:
    t = time.time()
    doc = converter.convert(f).document
    pages = sorted(doc.pages)
    for n in pages:
        (out / f"{Path(f).stem}-p{n}.html").write_text(doc.export_to_html(page_no=n, image_mode=ImageRefMode.EMBEDDED))
    print(f"{Path(f).stem}: {len(pages)} pages in {time.time() - t:.1f}s", flush=True)
