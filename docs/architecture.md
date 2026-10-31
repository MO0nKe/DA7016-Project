# Architecture

## Overview

```text
 Browser (React studio, :5173)                 Backend (FastAPI, :8000)                     External APIs
┌──────────────────────────────┐   /api    ┌──────────────────────────────────────┐     ┌──────────────────┐
│ library/   Zotero-like home  │ ────────► │ api/       routers, one per area     │     │ Bodhan AI        │
│ studio/    pages, views,     │  (Vite    │ pipeline/  ingest · structure ·      │ ──► │ OCR, translate,  │
│            prompt box        │   proxy)  │            translate · render · edit │     │ transliterate    │
│ panels/    translations,     │ ◄──────── │ core/      model, storage, library,  │     ├──────────────────┤
│            sidebar           │  JSON +   │            jobs, languages, config   │ ──► │ OpenRouter       │
│ pdf.js     the Original view │  HTML     │ clients/   cache, ledger, pacing     │     │ edits, reviews   │
└──────────────────────────────┘           └──────────────┬───────────────────────┘     └──────────────────┘
                                                          │                  (or mock_server/ on :9000)
                                              data/{mock,live}/: documents, cache, usage ledger
```

**The idea:** a PDF is read once into a JSON **document model**: pages of positioned, labelled blocks. Every stage
reads and writes that model. Translating fills in each block's translation. The studio then draws a page again with
each block in its translation, at its original position and in its original style, over the page with its text
removed. A reviewer can revise one block with a prompt, and only that block is drawn again.

## The document model

`backend/core/models.py`, stored as `<data_dir>/documents/<id>/doc.json` by `core/store.py`. The frontend mirrors it
by hand in `frontend/src/api/types.ts`.

```text
Document  id (hash of the PDF bytes), filename, fonts, source_lang (detected), pages[]
└─ Page   index, width × height (PDF points), source: text_layer | ocr | pending_ocr,
          image (raster), background (raster with the text removed), review (structure fixes applied),
          obstacles (pictures and line art text must keep clear of)
   └─ Block  id, order (reading order), label (Title, Section-title, Paragraph, List, Table, Footnote…),
             bbox (points from the page's top-left), text, rich (text with <b>/<i>/<span> runs), style,
             cells (text-layer tables), html (OCR tables), maths (inline formula crops),
             room (empty space below), continues (next block's id),
             translations{lang}
      └─ Translation  text, rich, cells/html, status, style (a reviewer's look changes), lang, edits[]
```

- **Ids** are a hash of the PDF bytes, so uploading the same file again returns the existing document.
- **Locks:** hold `store.locks[doc_id]` while reading, changing and saving a document, and
  `store.locks[f"{doc_id}:annotations"]` for its annotations.

## The pipeline (`backend/pipeline/`)

### 1. Ingest (`ingest/`, free)

`ingest_pdf` reads every page with PyMuPDF, once per file. The package is split by concern, lowest layer first; each
module imports only from the ones above it in this list:

| Module | Owns |
| :--- | :--- |
| `text` | spans, visual lines (fragments on one baseline re-joined), text cleanup, text quality |
| `style` | font names and families, a block's dominant style, styled runs (`Block.rich`) |
| `fonts`, `webfonts` | the PDF's embedded fonts, converted into fonts a browser can load |
| `maths` | display equations kept as drawn; inline formula runs cropped from the page |
| `tables` | ruled grids, label/value columns (infoboxes), rows that share a line |
| `raster` | page rasters, the **text-free background**, link underlines, sampled colours, the room below a block |
| `blocks` | lines into blocks, list items, merging continuations, line metrics, XY-cut reading order |
| `regions` | the `pymupdf-layout` model's regions (blocks spanning two are split, and its labels refine ours); figures and photos |
| `labels` | headings, running heads, page numbers, footnotes, captions, furniture repeated across pages |
| `ocr` | the OCR path (below) |
| `document` | `ingest_pdf`: the orchestration |

- **Unusable pages:** a page with no usable text layer (a scan, or garbled Indic encodings) becomes `pending_ocr`.
  Pressing **Run OCR** sends its image to Bodhan `indic-ocr`, whose labelled blocks replace the page's blocks.
- **Scans:** a scan's text can't be removed from its image, so each OCR block is painted over the scan with a colour
  sampled from around it.

### 2. Structure review (`structure.py`, on upload, OpenRouter)

- **What it does:** right after an upload, a background job sends each text-layer page to Claude Sonnet. The page
  goes as an image with every block outlined and numbered, plus a short listing of the blocks.
- **What can come back:** checked fixes. A block can be split into lines or at given words, stacked blocks can be
  merged, labels changed, and a sentence that runs on into another block or page marked as continuing.
- **How they're applied:** with the PDF's own lines, through the ingest helpers. A fix that would lose words is
  refused, and the fixes that took effect are recorded on `Page.review`.
- **Timing:** about 10 s and $0.01 a page, cached. A translation started meanwhile waits for it.

### 3. Translation (`translate/` and `markup.py`, Bodhan)

- **What is sent:** one `indic-translate` call per unit (`translate/units.py`). Table cells go one by one, an OCR
  table's HTML text nodes one by one, and plain text otherwise.
  - Text already in the target language is skipped, and so are codes and numbers.
  - A continuation pair (`Block.continues`) is translated as one sentence and cut back in proportion.
- **Inline markup survives translation** (`markup.py`):
  - Styled runs travel as their tags.
  - Inline formulas travel as `⟦n⟧` placeholders and are put back as their original text.
  - Footnote markers leave the text and return after their sentence; powers like "2⁸" stay in place.
  - A truncated answer is retried sentence by sentence.
- **The heading pass** (`translate/headings.py`): short headings translated on their own are revised by OpenRouter,
  given the start of their section. The revision is recorded as an edit, so it can be undone.
- **As a job:** `translate/run.py` runs a whole document as a background job (`core/jobs.py`), one language after
  another. Live Bodhan calls are paced to the rate limit.

### 4. Rendering (`render.py`, `static/render.css`, `static/fit.js`)

A page becomes an HTML fragment of absolutely positioned blocks.

- **In the studio** (`render_page(..., image_url=…)`): a language view starts from the **original raster**.
  - A section translated into that language covers its own box with that patch of the text-free background, then
    draws its translation.
  - Every other section stays as the original's own pixels. Its text is kept invisible, so it can still be
    selected and clicked.
  - That's why an untranslated section looks exactly like the Original view, and a partial view reads as "the
    original, with these in Tamil".
- **Fonts:** translated text is drawn in Noto, one family per script; never the PDF's embedded subset fonts, which
  only hold the original's glyphs.
- **Keeping clear of pictures:** ingest stores each page's `obstacles` (`regions.drawn_areas`: pictures and
  clusters of line art, not rules or page-sized frames). `render.obstacles_for` drops the ones a section sits on
  (holding half of it or more: a panel, a banner, a table's frame) and all of them for text inside a figure.
  Single-line blocks widen to the right margin but stop at them (`layout_box`), and a picture reaching a line or
  more into a paragraph's box becomes an empty float on its side (`wrap_html`, left or right), so the text wraps.
- **Fitting:** `fit.js` fits each block in BabelDOC's order. It tightens the lines first, then grows into the room
  below, then shrinks down to 55%, then to a readable floor (40%, not under 5.5 pt), then gives alike blocks a
  common size. What still doesn't fit is marked `data-overflow` and clipped to its box (`render.css`), never
  drawn over a picture; the studio says so in a toast (`PageView` reports the clipped sections), with **Show**
  opening the first one's full text in the panel.
- **One renderer everywhere:** the same files serve the studio and the measurement scripts, so they draw
  identically. The studio swaps in new versions of `render.css` and `fit.js` itself when the backend changes them;
  each rendered page carries their version.

### 5. Edits (`edit.py`)

- **Prompt edits:**
  - **What the model sees:** the block's original and its current translation, with run tags, plus its look and
    the pinned glossary terms.
  - **What it answers:** JSON with the revised `translation`, the `language` it wrote in, and any `style` changes
    (bold, italic, colour, alignment, hanging indent).
  - **Where the result goes:** if the answer is in another language than the view's, the edit lands in that
    language's translation (`api/edits.py`), creating it if needed.
  - **Who translates:** the model never writes a translation. When the section would change language, it leaves
    `translation` null and only names the `language` (and any `style`). `api/edits.py` then fills the text in:
    Bodhan's translation of the block's original (`bodhan_translation`, the same `translate_block` as a
    translation job), or for the document's own language ("keep it in English"), the original itself
    (`edit.original_value`). The model's look changes are kept.
- **Undo:** every edit is recorded with what it replaced, so undo restores the text, the
  runs and the look. An edit that created a translation removes it.
- **Concurrency:** the model is asked before the document lock is taken, so several sections are edited at once.

### Supporting pieces

- **`outline.py`:** the PDF's bookmarks, or our headings.
- **`glossary.py`:** pinned terms, and which translated sections don't use them.
- **`evaluate.py`:** metrics for the report.
- **`export.py`:** HTML printed to PDF with Chrome, used by the measurement scripts.

## The API (`backend/api/`)

- **`app.py`** creates the app. It builds the shared `Services` once (settings, store, library, glossary, jobs and
  both API clients) and mounts the routers and the renderer's static files.
- **Routes** receive the services through FastAPI's `Depends` (`api/deps.py`), along with the shared lookups that
  return a document, page or block, or a 404.
- **Request bodies** are in `api/schemas.py`; responses are the core models.
- See [api.md](api.md) for every endpoint.

## API clients (`backend/clients/`)

`make_clients(settings)` builds the Bodhan and OpenRouter clients. They share one request cache and one usage ledger.

- **Cache:** every response under `cache/<host>/<model>/<sha256>.json`.
- **Ledger:** a line in `usage.jsonl` for every call.
- **Limits:** at most 4 Bodhan calls at a time, live calls paced, and retries with backoff on 429 and 5xx.

The base URLs alone decide mock or live. [external-apis.md](external-apis.md) has the verified API behaviour.

## The frontend (`frontend/src/`)

| Folder | Holds |
| :--- | :--- |
| `api/` | `types.ts` (the model mirror) and `client.ts` (every backend call) |
| `library/` | the home page: `LibraryPage` (folders, table, details), `DocumentDetails`, `TranslateDialog` |
| `studio/` | `StudioPage` (layout only), `StudioToolbar`, `PromptBox`, `SelectionToolbar`, `PickBar`, `pages/` (`PageView`, `OriginalPage`, `Highlights`) |
| `studio/hooks/` | one hook per concern (below) |
| `panels/translations/` | the Translations panel: `DocumentView`, `BlockView`, cards, `EditMenu`, define/romanise |
| `panels/sidebar/` | Contents, Pages, Search, Notes and Glossary |
| `ui/` | generic pieces: icons, `LanguagePicker`, `ContextMenu`, `Toast` |
| `lib/` | pdf.js setup, display formatting, reading positions, small hooks |

`StudioPage` composes one hook per concern and lays out the result:

| Hook | Owns |
| :--- | :--- |
| `useStudioDocument` | the document model, its PDF, block changes swapped into the pages, OCR |
| `useLanguageViews` | the tabs, the shown language and view (derived, never corrected by effects) |
| `useReadingPosition` | zoom, scroll, current page, `goTo`, the position remembered per document |
| `useSelection` | what the panel shows, and the sections the prompt box edits |
| `usePromptEdits` | prompt edits and undo across the selected sections, landing in the right view |
| `useTranslationJob` | polling the running job, and picking up a translation that waited for the review |
| `usePicks` | Shift-picked sections and the pick bar |
| `useAnnotations` | highlights, comments and text boxes |
| `usePanels` | the two side panels, inline or sliding |

How each view is drawn:
- **The Original view** is pdf.js: a canvas plus a text layer, for exact selection and highlights.
- **A language view** is the backend's HTML fragment for that page, fitted by `fit.js`. After an edit, only the
  edited block's HTML is swapped in.

## A prompt edit, end to end

1. You select sections and type "put this in Tamil". `usePromptEdits` sends one
   `POST /api/documents/{id}/blocks/{block}/edit` per section, all at once.
2. `api/edits.py` asks OpenRouter (`edit.ask_edit`) without holding the lock, and reads the language of the answer.
   The model answers with no text, the language `ta` and any look changes; Bodhan translates the block's original
   into Tamil for the text.
3. Under the document lock, `edit.apply_edit` writes the answer into the block's Tamil translation, creating it,
   and records the edit (model "… + Bodhan"). The document is saved.
4. The response carries the block, the language it landed in (`ta`), and its HTML drawn over the text-free patch.
5. The studio replaces the block in its model and switches to the Tamil tab. It swaps in just that block's HTML, or
   draws the pages again when several sections changed. The sections stay selected, and **Undo** removes the Tamil
   translation again.
