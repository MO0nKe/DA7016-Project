# Conversion-quality study

How well does our ingest capture a page's structure (reading order, headings, tables, figures, footnotes)? Each corpus
page is converted into flowing HTML, by our ingest and by [Docling](https://github.com/docling-project/docling) as a
baseline. A vision model then judges each pair blind against the original page.

| File | What it is |
| :--- | :--- |
| `ours_html.py` | Our side: flowing HTML per page from the current ingest. `ours_html.py <out dir> <pdf>...` |
| `ocr_naca.py` | Our side for the image-only scan (ingest, Bodhan OCR, HTML). Live once, cached after. |
| `docling_html.py` | Docling's HTML export per page; runs in a separate Docling environment |
| `docling/` | Docling's saved output (the baseline, committed) |
| `orig_png.py` | Page images of the originals, into `orig/` (git-ignored) |
| `compare.html` | Each original page beside our conversion; serve the repo root (`python3 -m http.server 8100`) and open `/eval/conversion/compare.html` |
| `blind.py` | Blind image sets per page (original, A, B), with A/B swapped in a second pass; the mapping goes to `key.json` |
| `judge.py` | The pairwise judge (OpenRouter, cached): which conversion captures the page better? A point counts only where both orders agree |
| `tally.py` | Maps A/B back to converters and tallies the points into `tally.json` |
| `results/` | The judges' answers per pass |

Run everything from the repository root with the project environment (`uv run python eval/conversion/<script>`),
except `docling_html.py`.
