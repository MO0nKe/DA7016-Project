# Getting started

## 1. Prerequisites

| Tool | Why | Install |
| :--- | :--- | :--- |
| [uv](https://docs.astral.sh/uv/) | Python 3.12+ and every Python dependency (never use bare `pip`) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node 22 and npm | The studio (React + Vite) | <https://nodejs.org> or your package manager |
| Google Chrome | Only for one slow test and two measurement scripts (`check_render`, `evaluate`), via Playwright | <https://www.google.com/chrome/> |
| Noto and Liberation fonts | Translated pages are drawn in Noto (one family per script) and the source in metric-compatible Liberation fonts. Without them the browser falls back to whatever it has, and the layout suffers. | Ubuntu/Debian: `sudo apt install fonts-noto-core fonts-noto-extra fonts-liberation`; macOS: install the [Noto families](https://fonts.google.com/noto) you need |

## 2. Install

```bash
git clone <this repository> && cd DA7016-Project
make install
```

`make install` runs `uv sync` (a `.venv` with the Python packages), `npm install --prefix frontend`, and downloads
WordNet for the offline dictionary (**Define** in the studio). Run `make help` to list every command.

## 3. Run it

The app has three processes. Start each in its own terminal:

```bash
make mock        # fake Bodhan + OpenRouter on http://localhost:9000
make backend     # the API on http://localhost:8000 (reloads when backend code changes)
make frontend    # the studio on http://localhost:5173 (proxies /api to the backend)
```

Open <http://localhost:5173>. The top bar shows **Mock** in green: no request leaves your machine.

### Mock or live

What the backend talks to is decided by two base URLs alone (`backend/core/config.py`). Both default to the mock.

| | Mock (default) | Live |
| :--- | :--- | :--- |
| Start the backend with | `make backend` | `make backend-live` (or set the base URLs in `.env` and use `make backend`) |
| Top bar | **Mock** (green) | **Live** (red) |
| Translations | Made-up text in the target script, about 1.3× longer, unless a live answer to the same request was recorded | Real |
| Costs | None | Bodhan and OpenRouter credits (see below) |
| Data folder | `data/mock/` | `data/live/` |

For live mode, copy `.env.example` to `.env` and fill in your keys: `BODHAN_OCR`, `BODHAN_TRANSLATE` and
`BODHAN_TRANSLITERATE` (Bodhan issues one key per model), and `OPENROUTER`. The backend logs a warning at startup
whenever it will spend credits.

### Settings

All settings are environment variables, read from `.env` too; real environment variables win. See
[`.env.example`](../.env.example) for the full list with defaults.

| Variable | Default | What it does |
| :--- | :--- | :--- |
| `BODHAN_BASE_URL` | `http://localhost:9000` (mock) | `https://api.bodhan.ai` to go live |
| `OPENROUTER_BASE_URL` | `http://localhost:9000/api/v1` (mock) | `https://openrouter.ai/api/v1` to go live |
| `BODHAN_OCR`, `BODHAN_TRANSLATE`, `BODHAN_TRANSLITERATE`, `OPENROUTER` | empty | API keys (live only) |
| `OPENROUTER_MODEL` | `google/gemini-2.5-flash-lite` | Model for the evaluation's translation judge (prompt edits use Claude Sonnet 5.5) |
| `BODHAN_PER_MINUTE` | `15` | Pace of live Bodhan calls per model (`indic-translate` rejects more) |
| `DATA_DIR` | `data/live` or `data/mock` | Where documents, the cache and the usage ledger live |
| `MOCK_LATENCY_MS`, `MOCK_ERROR_RATE`, `MOCK_LLM` | `0`, `0`, `echo` | Mock server only: slow it down, fail at random, or forward OpenRouter calls to a free model |

## 4. Your first document

1. Drop a PDF onto the library (or use the **Add a PDF** button). Reading its text layer is free, and a re-upload of
   the same file opens the copy you already have.
2. Choose a language in the dialog and press **Translate**. The document opens and its pages translate in the
   background. **About N minutes** is the wait at the live rate limit.
3. The tabs above the pages switch between **Original** and each language. Select text or click a section, then type
   a change in the box under the pages.

The [user guide](user-guide.md) covers the rest.

## 5. Where things are kept

Everything lives under the data folder (`data/mock/` or `data/live/`), which git ignores:

```text
documents/<id>/        one folder per document; <id> is a hash of the PDF, so re-uploading finds it again
  doc.json             the document model: pages, blocks, translations and their edit history
  source.pdf           the uploaded file
  pages/               page rasters and their text-free backgrounds
  fonts/, maths/       embedded fonts reused for redrawing, crops of inline formulas (when there are any)
  annotations.json     your highlights, notes and text boxes (once you make one)
library.json           folders and which document is in each
glossary.json          pinned term translations
cache/<host>/<model>/  every API response, so no request is paid for twice
usage.jsonl            one line per API call (cache hits too): `GET /api/usage` totals it
eval/                  reports from scripts/evaluate.py
```

Reading positions, the library's open folder and each document's language tabs are kept in the browser's local
storage.

## 6. Costs and limits (live)

- **Free:** ingesting a PDF's text layer, translating the same text twice (the cache answers), Define, and
  everything in mock mode.
- **Bodhan:** one `indic-translate` call per block (table cells one by one), and one `indic-ocr` call per scanned
  page, run only when you press **Run OCR**. The real constraint is the rate limit: 15 translations a minute, so a
  20-page document takes a few minutes.
- **OpenRouter:**
  - The structure review on upload: about $0.01 a page.
  - Prompt edits: about $0.0002 each.
  - The heading pass: about $0.001 a heading.

## 7. Troubleshooting

| Symptom | Cause and fix |
| :--- | :--- |
| The top bar says **Live** but you meant mock | `.env` sets `BODHAN_BASE_URL`/`OPENROUTER_BASE_URL`; remove them, or start with `make backend` from a shell without them |
| Every request fails with "connection refused" | The mock isn't running: `make mock` |
| Scanned pages show blank in the Original view | pdf.js needs its WebAssembly decoders; they're set up in `frontend/src/lib/pdf.ts`. Hard-refresh the page. |
| Translated text looks wrong in an open studio tab after a backend update | The studio swaps in the renderer's new CSS and fit script by itself; if it doesn't, reload the page |
| A document lays out worse than others after an update | Layouts are computed once, at upload. Run `make refresh-documents` (with the backend running) to re-ingest and re-translate stored documents. |
| Mock translations look like gibberish where live ones existed | The backend cached the mock's invented answers before the live ones were recorded: `uv run scripts/refresh_mock_cache.py`, then restart the mock |
| `429` errors on live | The Bodhan rate limit; the client waits and retries. Translate fewer pages at once. |
| **Define** says the dictionary is unavailable | Run `uv run python -m nltk.downloader wordnet` (part of `make install`) |
