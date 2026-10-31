# Structure preservation: research and the flow we will follow

Written 2026-10-27. Covers three faults the user saw: translated text overflowing its box, mixed fonts in translated
text, and LaTeX-heavy papers (maths mangled or missing).

## 1. What we found in our own pipeline

Reproduced with fake Hindi (the mock's `pseudo_text`, 1.3× length) on Mamba, LLaMA, FIPS-197, Monsoon and the NASA
fact sheet, and with the real live translations (NIST slides → bn, Bengali Taj Mahal → en).

| Fault | Cause in the code |
|---|---|
| **Overflow** | `fit.js` only shrinks the font, per block, down to 55%; past that the text spills (`overflow: visible`). Only single-line blocks may widen (`render.layout_box`); paragraphs never use the free space below them. Table cells get no extra room (Taj Mahal infobox: "Ustad Ahmad Lahori" runs into the next row). |
| **Uneven sizes** | Each block shrinks on its own, so neighbouring paragraphs of the same original size end up at different sizes (Taj Mahal: the third paragraph is much smaller than the first). This reads as "a mix of fonts". |
| **Mixed fonts** | `render.font_family` puts the PDF's own *embedded subset* font first. A subset only has the glyphs the original used, so in translated text some Latin letters, digits and punctuation come from the PDF font and the rest fall back to Liberation, while Indic falls back to Noto. One line can switch fonts several times. |
| **Inline maths** | Only *display* equations are kept as drawn (`is_maths`, `maths_line`). Inline maths stays in the paragraph text and goes to Bodhan: Mamba p2 sends 127 maths-font characters, FIPS p1 27. Subscripts and superscripts are flattened (x⁸ becomes "x8"), and Unicode maths letters (𝑨, ℎ) depend on whatever system font has them. |
| **Ghost marks** | Link underlines and other thin line art stay in the text-free background at the original word positions and cut through the translation (Taj Mahal, every link). |

Display equations themselves mostly survive: `pymupdf-layout` finds 5 formula regions on these pages, and our
maths heuristic already keeps all of them as drawn.

## 2. How other tools do it

**IBM Docling** is an extractor, not a translator.
- **Pipeline:** a parser gives text cells with exact positions, a layout model (Heron, RT-DETR, DocLayNet labels)
  draws labelled regions, TableFormer rebuilds tables, and a rule-based reading order assembles a `DoclingDocument`.
- **Maths:** "formula enrichment" (off by default) turns *display* formula regions into LaTeX with a VLM. Inline maths
  is not handled.
- **Fonts and redrawing:** it keeps labels and boxes but no font name, size or colour, and it never redraws a page;
  output is Markdown, HTML or JSON.
- **Cost:** PyTorch, about 500 MB of models, about 1 page/s on CPU.
- **For us:** borrow the idea (*a layout model's regions, filled with the parser's exact text*), not the tool. We
  already measured it losing on text quality (`eval/conversion/docling`).

**PDFMathTranslate (pdf2zh) and BabelDOC** solve exactly our problem, for Chinese.
- **Maths, by character:** a character is maths if its font matches a TeX-font pattern (`CM[^R]|MS.M|…|.*Math`),
  its Unicode class is a symbol or Greek, it is less than 0.79× its neighbour's size (sub/superscript), or a layout
  model (DocLayout-YOLO, ONNX) marks the area as a formula. Bracket depth keeps `( … )` together.
- **Maths through translation:** each inline formula becomes a placeholder `{v0}`, `{v1}` before translating, and is
  put back afterwards *as its original glyphs in the original font*, never re-typeset.
- **Fitting (BabelDOC):**
  - It tries scales from 1.0 down in 5% steps.
  - Below 0.7 it **grows the box into free space**, down then right, and starts again.
  - It **clamps every paragraph to the document's common scale**, so sizes stay consistent.
- **Fonts:** all translated text is drawn in the target fonts; the original fonts are used only for formulas and
  text passed through untranslated.
- **Not usable directly:** both write glyphs one code point at a time with no HarfBuzz shaping, so Devanagari
  conjuncts and Tamil vowel signs break. Our Chrome-based renderer already shapes Indic correctly; keep it.

**MinerU and Marker** recognise maths as LaTeX (UniMERNet, Surya) and output Markdown. That's useful for
extraction, not for keeping a page's look.

**Found locally:** `pymupdf-layout` 2.0 is already installed in `.venv`, but it isn't in `pyproject.toml` and
nothing uses it.
- **What it is:** PyMuPDF's own layout model. ONNX, no PyTorch, 51 MB.
- **Output:** labelled boxes (title, section-header with a level, text, list-item, caption, picture, table,
  formula, footnote, page-header/footer) with their text lines.
- **Speed:** 0.6 s for both Mamba pages on CPU.
- **Verdict:** this is the "local layout model" from the 2026-10-26 handoff, without the PyTorch cost.

## 3. The flow

Every step is checked on the 17-document corpus before the next starts. No step spends credits except the probe
in step 4 (about 6 calls) and the final live check (asked for first).

### Step 0: measure first — done 2026-10-27
- **Fake-translation check:** `uv run scripts/check_render.py --lang hi` fills `pseudo_text` translations
  (about 1.3× longer, in the target script) and prints per document:
  - `overflowing`: blocks whose text still spills out of the box. Boxes come from the original page, so this
    stands in for "overlaps another block".
  - `median_scale`, `shrunk_below_0.8`: how far the text had to shrink.
  - `size_spread`, `uneven_groups` (`evaluate.size_spread`): blocks that started alike (same label and size)
    but ended at different sizes.
  - `mean_families`, `blocks_3plus_families`: font families drawing each translated block, read back from the
    printed PDF.
- **Baseline and results:** measured with `scripts/check_render.py` before each step. Every later step must improve them.

### Step 1: one font per script (mixed fonts) — done 2026-10-27
- **Translated blocks:** drop the embedded PDF font. Use one matched family: Noto Serif or Noto Sans for Latin,
  plus the same family's Indic font (Noto Serif Devanagari, Noto Sans Tamil…), chosen from the block's serif or sans
  style.
- **Keep the embedded font** only where the original text is drawn: untranslated blocks and maths.
- **Not done: bundling the fonts** as WOFF2 under `backend/static/fonts/`. Every font in the stack is installed here
  (`fonts-noto`), and the old stack relied on system fonts too. Bundle them only if the app must run on a machine
  without Noto.

### Step 2: fit in BabelDOC's order (overflow, uneven sizes) — done 2026-10-27
Rework `fit.js` and `render.layout_box` (as built: room is measured at ingest, `Block.room`; growing right,
cells growing into empty cells, and the "Shorten" button were left out; overflowing blocks get a dashed amber
outline in the studio):
1. **Common scale:** measure each block's fitting scale, then give every block in a group (same label, same
   original size) the group's scale, so sibling paragraphs match. Blocks that still don't fit go on.
2. **Grow into free space:** downward to the next block, kept equation or picture, or the bottom margin, and to the
   right for any block, not just single lines. `render.py` computes the free box and passes it as
   `data-room`. Table cells may grow into empty neighbouring cells.
3. **Tighten the line height** from 1.22 to no less than 1.1. Indic vowel signs need the room, so it goes no lower.
4. **Shrink** to the existing 55% floor.
5. **If it still doesn't fit:** clip the text and mark the block `data-overflow`. The studio shows a badge with a
   "Shorten" prompt-edit (the existing `edit.py` route; OpenRouter, about $0.0002 each).

### Step 3: clean background (ghost marks) — done 2026-10-27
- **What to remove:** after redaction, also remove thin horizontal line art lying just under a text line (link
  underlines, strike-throughs) inside translatable blocks.
- **What stays:** table rules and figure strokes, which lie outside text lines or inside figure areas.

### Step 4: inline maths through translation (LaTeX) — done 2026-10-27
- **Find inline maths by character,** with pdf2zh's rules inside paragraph lines:
  - a maths font (our `MATH_FONT` plus pdf2zh's list)
  - Unicode symbol or Greek, or a maths alphanumeric (U+1D400–1D7FF)
  - smaller than 0.79× its neighbour
  - inside brackets with any of the above

  Adjacent maths characters form one run; each run's box is kept.
- **Protect it in translation:** replace each run with a numbered placeholder `⟦1⟧`. docs/external-apis.md records that these survive
  Bodhan exactly, 2 of 2, which is too small a sample, so first probe about 6 calls on hi, ta and bn.
  - If a placeholder is lost or duplicated, retry the block once, then show the source text for that block.
  - Placeholders never count as text to translate: a block that is only maths is not sent.
- **Draw the run as itself:** each placeholder is put back as an inline image cropped from the original page at a
  high DPI (or `page.get_svg_image(clip=…)`), sized to the run's height and baseline-aligned. The LaTeX looks exactly
  as typeset, subscripts included, with no LaTeX rendering and no font coverage problem.
- **Display equations:** unchanged. They stay as drawn in the background, and the formula regions from step 5 make
  their detection more reliable.

### Step 5: regions from a layout model (structure) — done 2026-10-27, to judge by eye
- **Add the model:** add `pymupdf-layout` to `pyproject.toml` (`uv add`). Run it per page in `ingest.py`.
- **Model gives regions, PyMuPDF gives text:** each PyMuPDF line is assigned to the model region holding it, and
  the region becomes the block. Its label maps to ours (section-header level → Section-title / Sub-section-title,
  formula → kept as drawn, picture → `in_figure`, page-header/footer → furniture).
- **Keep our own code where it is better:** ruled-grid tables, label/value tables, running heads, XY-cut order
  between regions.
- **Fallback:** if the model fails or returns nothing, use today's heuristics.
- **Scans unchanged:** they still use Bodhan `indic-ocr`, which already returns regions.
- **Judge it** by eye in `eval/conversion/compare.html` against today's ingest and the saved Docling baseline.

### Step 6: check live
- **Ask first:** about 4 documents × 2 pages into hi, about 60 Bodhan calls. Cheap, but it is a bulk run, so ask
  before starting.
- **Then:** re-ingest (the document hash keys the ingest, so delete and re-upload) and update the handoff and
  README.

### Later, not in this flow
- **Translations closer to a serif original's look** (user, 2026-10-27: "keep it as a note, can try later"). The
  Tiro Indic fonts (Tiro Devanagari Hindi, Tiro Bangla, Tiro Tamil… on Google Fonts) carry Latin drawn to sit beside
  Times. Using them for serif blocks instead of Noto Serif would bring serif translations nearer the original. Sans
  stays on Noto Sans. None is installed, so the font files would be added to the repo.
- **Inline formatting** (bold, italics, links) as HTML tags through Bodhan.
- **Paragraphs continued across pages.**
- **Redrawing as a real PDF** with PyMuPDF `insert_htmlbox`, which shapes Indic with HarfBuzz. Only if Chrome
  rendering ever becomes the bottleneck.
