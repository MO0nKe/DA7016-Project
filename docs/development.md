# Development

Read [architecture.md](architecture.md) first; this page is about working on the code.

## Everyday commands

```bash
make install            # once, and after dependency changes
make mock / make backend / make frontend
make check              # lint + format check + type-check + fast tests: what every change should pass
make test               # all tests, including the Chrome one
make format             # ruff format + autofix
make help               # everything else
```

One test, or one file:

```bash
uv run pytest backend/tests/test_ingest.py::test_text_cleanup
uv run pytest backend/tests/test_edit.py -q
```

## Repository layout

```text
backend/
  main.py, app.py      the uvicorn entry point and the app factory
  core/                settings, the document model, languages, storage, the library, jobs (imports nothing above it)
  clients/             Bodhan and OpenRouter: cache, ledger, retries, pacing
  pipeline/            the work: ingest/, structure, translate/, markup, render, edit, outline, glossary, export, evaluate
  api/                 the routers, their shared services (deps.py) and request bodies (schemas.py)
  services/            the offline dictionary
  static/              render.css and fit.js, shared by the studio and the scripts
  tests/               backend tests (pytest)
frontend/src/
  api/, lib/, ui/      the backend client and types, helpers, generic components
  library/, studio/, panels/   the features (see architecture.md)
mock_server/           the stand-in for Bodhan and OpenRouter, with its tests
scripts/               command-line tools (below)
eval/conversion/       the conversion-quality study (see its README)
fixtures/              sample PDFs and recorded API responses used by the tests
documents/             the 17-excerpt test corpus (sources in documents/SOURCES.md)
docs/                  this documentation; docs/reference/ holds design write-ups
```

## Conventions

- **Python is managed with uv only:** `uv add`, `uv sync`, `uv run`; never bare `pip`.
- **Dependencies point one way:** `api` → `pipeline` → `core`, and nothing imports upward. Inside
  `pipeline/ingest/`, each module imports only from the layers listed above it in its `__init__.py`. Function-level
  imports used to dodge a cycle are a sign the code is in the wrong module.
- **One concern per module**, which opens with a docstring saying what it owns. Public functions get a docstring
  saying what they return. Comments explain *why*; the code says what. Keep modules under about 350 lines.
- **Style:** `ruff` enforces the Python style (120 columns, rules in `pyproject.toml`), and `oxlint` plus `tsc` the
  TypeScript. Commit only with `make check` passing.
- **The frontend's model types** (`frontend/src/api/types.ts`) mirror `backend/core/models.py` by hand. Change both
  together.
- **UI:** clean and minimal, with little on-screen text: labels of a word or two, tooltips for the rest, one-line
  empty states. Follow and update [style-guide.md](style-guide.md). Use `LanguagePicker` for language choices, never
  a native `<select>`.
- **Studio state** goes in the hook that owns its concern (`studio/hooks/`), not in `StudioPage`. Derive values
  instead of correcting state in effects, and key components that must start fresh for a new input.
- **Interaction styles** for rendered pages (selected and picked outlines) live in `frontend/src/styles/index.css`.
  `backend/static/render.css` is only for drawing pages, and is shared with the scripts.

## Tests

| Where | What | Notes |
| :--- | :--- | :--- |
| `backend/tests/` | ingest, structure, translation, rendering, edits, glossary, library, annotations, clients, evaluation | The API runs in-process against the mock app; no network, no credits |
| `mock_server/tests/` | the mock's shapes, errors and replay | |
| `-m slow` | prints a document with Chrome | Needs Google Chrome; `make test-fast` skips it |

The tests use the PDFs in `fixtures/inputs/` and `documents/`. Don't regenerate `fixtures/inputs/` casually
(`scripts/make_samples.py`): document ids are hashes of the PDF bytes.

**Refactors:** besides the tests, compare the ingest and render output of the whole corpus before and after; it must
stay byte-identical. The restructure did this with a snapshot script that ingested every corpus PDF and rendered each
page in four modes.

## Scripts

| Script | Use it to | Cost |
| :--- | :--- | :--- |
| `scripts/refresh_documents.py` | **After any ingest or layout change:** re-ingest every stored document and translate it again into its languages. Prompt edits are lost; they're listed first and backed up to `data/refresh-backup/`. Run against the running backend (`make refresh-documents`). | Cached translations free; structure review about $0.01 a page |
| `scripts/check_render.py` | Measure rendering on the corpus: structure kept, text fit, overflow, size spread, font families, side-by-side images in `data/check/` | Free; `--live` translates for real |
| `scripts/evaluate.py` | Evaluate one PDF and language for the report (JSON and Markdown in `data/<mode>/eval/`) | Free by default; `--back-translate`, `--judge` cost credits |
| `scripts/smoke_test.py` | One real call per API, recorded to `fixtures/recorded/` | A few calls; `--dry-run` sends nothing |
| `scripts/refresh_mock_cache.py` | Drop the mock's cached invented answers that a live recording now covers; restart the mock after | Free |
| `scripts/make_assets.py` | Make the tab icons (`favicon.ico`, `apple-touch-icon.png`) in the accent colour | Free |
| `scripts/make_samples.py` | Rebuild the sample PDFs in `fixtures/inputs/` with Chrome | Free (but changes their ids) |

Every script has `--help`.

## Mock, live and data

The base URLs alone decide mock or live (`backend/core/config.py`). Mock and live keep separate data folders, and the
mock replays everything ever recorded live. Live calls are fine for testing (credits are ample); the rate limit is
the real constraint, so lean on the cache. [external-apis.md](external-apis.md) has the details. When a stored
document looks stale after a pipeline change, refresh it (above) rather than patching its JSON.

## Evaluation

- **Scripts:** `scripts/evaluate.py` and `scripts/check_render.py` measure translation and rendering quality.
- **`eval/conversion/`** compares how well our ingest captures each page's structure against Docling, judged
  blind by a vision model. See its README.
- **Design write-ups:** `docs/reference/Structure-Flow.md` explains the fitting and structure decisions, and
  `docs/reference/Bodhan-Issues-2026-10-31.md` records the Bodhan answers the app has to guard against.

## Adding things

- **An endpoint:**
  1. Add it to the router for its area in `backend/api/`; take `svc: ServicesDep` for the shared services, and use
     the `deps` lookups for documents, pages and blocks.
  2. Add its request body to `schemas.py`.
  3. Add the call to `frontend/src/api/client.ts`, and a row to [api.md](api.md).
  4. Test it through the `api` fixture in `backend/tests/conftest.py`.
- **An ingest heuristic:** put it in the `pipeline/ingest/` module that owns that concern. Check it against the
  corpus with `scripts/check_render.py`, then refresh the stored documents.
- **A studio feature:** give it its own hook in `studio/hooks/` when it has state and effects, and a component next
  to its feature. Keep `StudioPage` to layout and wiring.

## Branches

`main` shows translations by redrawing whole pages. The `slips` branch keeps an abandoned approach: translations as
slips pinned over the original page.
