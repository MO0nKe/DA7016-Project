# API reference

The backend serves everything under `/api` (`backend/api/`, one router per section below). Interactive docs with
every schema are at <http://localhost:8000/docs> while the backend runs.

- **Request and response models:** see `backend/api/schemas.py` (requests) and `backend/core/models.py` (`Document`,
  `Block`, `Translation`, `Annotation`…). The frontend calls every endpoint through `frontend/src/api/client.ts`.
- **Errors:** errors are `{"detail": "…"}`.

| Status | When |
| :--- | :--- |
| `400` | bad input |
| `404` | an unknown document, page, block, folder, term or job |
| `409` | a translation is already running for the document |
| `413` | a selection too long for one request |
| `502` | Bodhan or OpenRouter failed |
| `503` | the offline dictionary isn't installed |

## Documents (`documents.py`)

| Method | Path | Does |
| :--- | :--- | :--- |
| `POST` | `/api/documents` | Upload a PDF (multipart `file`). Ingests it (free; the same file returns the existing document) and starts the structure review in the background. Returns a `DocumentSummary`. |
| `GET` | `/api/documents` | Every document, as summaries |
| `GET` | `/api/documents/{doc_id}` | The whole document model |
| `DELETE` | `/api/documents/{doc_id}` | Delete it and its files |
| `GET` | `/api/documents/{doc_id}/source.pdf` | The uploaded PDF |
| `GET` | `/api/documents/{doc_id}/outline` | Contents: the PDF's bookmarks, or its headings |
| `GET` | `/api/documents/{doc_id}/pages/{index}/original.png` | The page raster |
| `GET` | `/api/documents/{doc_id}/pages/{index}/background.png` | The page with its text removed |
| `GET` | `/api/documents/{doc_id}/fonts/{filename}` | An embedded font, for redrawing the original's text |
| `GET` | `/api/documents/{doc_id}/maths/{filename}` | A crop of an inline formula |
| `POST` | `/api/documents/{doc_id}/ocr` | `{"pages": [n]}`: OCR scanned pages with Bodhan (one call each) |
| `POST` | `/api/documents/{doc_id}/structure` | `{"pages": [n]}`: run the structure review on pages now |

## Translation (`translation.py`)

| Method | Path | Does |
| :--- | :--- | :--- |
| `GET` | `/api/documents/{doc_id}/estimate?langs=hi,ta&pages=0,1&blocks=…&force=&include_figures=` | Blocks, calls (cached and not), output tokens and the wait in `minutes` (null on the mock) before translating |
| `POST` | `/api/documents/{doc_id}/translate` | `TranslateRequest` (`langs`, optional `pages`, `block_ids`, `force`, `include_figures`): start a background job; returns the `Job`. `409` if one is running. |
| `GET` | `/api/documents/{doc_id}/job` | The document's running job, if any (a translation before a structure review) |
| `GET` | `/api/jobs/{job_id}` | A job's progress: `status`, `done`/`total`, `failed`, `phase` |
| `POST` | `/api/translate-text` | `{"text", "langs"}`: translate a selection into each language; not stored |
| `POST` | `/api/transliterate-text` | `{"text", "lang"}`: romanise text written in `lang`; not stored |

## Rendering (`rendering.py`)

| Method | Path | Does |
| :--- | :--- | :--- |
| `GET` | `/api/documents/{doc_id}/pages/{index}/render?lang=` | One page as HTML: the original raster with the sections translated into `lang` drawn over it |
| `GET` | `/api/documents/{doc_id}/blocks/{block_id}/render?lang=` | One block as HTML |
| `GET` | `/api/documents/{doc_id}/preview?lang=` | The whole document as one printable HTML page |

The fragments need `/api/static/render.css` and `/api/static/fit.js` on the host page; the studio's `index.html`
loads both.

## Edits (`edits.py`)

Each returns `{"block", "page", "lang", "html"}`: the changed block, the language the change landed in, and its new
HTML.

| Method | Path | Does |
| :--- | :--- | :--- |
| `POST` | `/api/documents/{doc_id}/blocks/{block_id}/edit` | `{"lang", "instruction", "regenerate"}`: a prompt edit (OpenRouter). Lands in the language the answer is written in; a change of language is translated by Bodhan. |
| `POST` | `/api/documents/{doc_id}/blocks/{block_id}/revert` | `{"lang"}`: undo the last edit |

## Library (`library.py`)

| Method | Path | Does |
| :--- | :--- | :--- |
| `GET` | `/api/library` | Folders and which folder each document is in |
| `POST` | `/api/folders` | `{"name", "parent"}`: a new folder |
| `PATCH` | `/api/folders/{folder_id}` | `{"name"}` to rename; `{"parent", "move": true}` to move |
| `DELETE` | `/api/folders/{folder_id}` | Delete it; its documents and subfolders move up |
| `PUT` | `/api/documents/{doc_id}/folder` | `{"folder_id"}`: file a document (null: unfiled) |

## Annotations (`annotations.py`)

| Method | Path | Does |
| :--- | :--- | :--- |
| `GET` | `/api/documents/{doc_id}/annotations` | Highlights, notes and text boxes |
| `POST` | `/api/documents/{doc_id}/annotations` | Add one (`kind`, `page`, `rects` in PDF points, `color`, `quote`, `comment`, `font_size`, `lang`: `""` for the original or a language view's code) |
| `PUT` | `/api/documents/{doc_id}/annotations/{ann_id}` | Replace its content (its id, creation time and page stay) |
| `DELETE` | `/api/documents/{doc_id}/annotations/{ann_id}` | Delete it |

## Glossary (`glossary.py`)

| Method | Path | Does |
| :--- | :--- | :--- |
| `GET` | `/api/glossary` | Pinned terms |
| `POST` | `/api/glossary` | `{"source", "lang", "target"}`: pin a term |
| `DELETE` | `/api/glossary/{term_id}` | Unpin it |
| `GET` | `/api/documents/{doc_id}/glossary-check?lang=` | Translated sections that don't use a pinned term |

## Reading and status (`reading.py`)

| Method | Path | Does |
| :--- | :--- | :--- |
| `GET` | `/api/health` | The APIs in use and whether calls spend credits |
| `GET` | `/api/usage` | API calls, tokens and cost per host and model, from the ledger |
| `GET` | `/api/languages` | Target languages (`code`, `name`, `rtl`) |
| `GET` | `/api/define?word=` | English definitions from offline WordNet |

## Static files

`/api/static/render.css` and `/api/static/fit.js`, served with `Cache-Control: no-cache`.
