# External APIs: Bodhan and OpenRouter

The app uses two paid APIs. **Bodhan AI** is required by the course brief, and does all OCR, translation and
transliteration. **OpenRouter** handles general LLM work: prompt edits (a prompt that asks for another language is
translated by Bodhan), the heading pass and the structure review. Both have tight limits, so every request is cached and logged, and development runs against a
local mock (see [the mock server](#the-mock-server)).

Bodhan's docs: <https://console.bodhan.ai/api-docs/>. **Where the docs and the live API disagree, the live API wins.**
Everything below was measured against the live APIs; the dates say when.

## Bodhan

All models are called through `POST https://api.bodhan.ai/v1/chat/completions`. The documented `/translate` and
`/transliterate` routes return 404; only `/v1/chat/completions` and `GET /v1/models` exist. **Each key works for
exactly one model**: `BODHAN_OCR`, `BODHAN_TRANSLATE`, `BODHAN_TRANSLITERATE`.

| Model | Used for | Request and gotchas |
| :--- | :--- | :--- |
| `indic-ocr` | Layout and text of a scanned page | PNG or JPEG only, one image per call, as a base64 data URI. Returns `blocks[]`: a 37-class `label`, `bbox_xyxy` in image pixels, and `text`. Headings are *not* marked up in the markdown, so use `label`. Tables come back as HTML. A block over `max_tokens` gives a 502; the client retries once with `max_tokens=4096`. Headers and footers can come back with `text: ""`. |
| `indic-translate` | Translating one text unit | One user message holding the text, plus a top-level `target_language`. There's no source-language field. Unsupported codes (`bho`, `bhb`) are rejected with 400. There's no `truncated` field: check `finish_reason == "length"`. |
| `indic-transliterate` | Romanised reading of a translation | One user message plus a top-level **`target_language`** (not the documented `language`) and `script`. **Unknown fields are ignored silently**, and without `target_language` the model may *translate* instead. |

**Limits** (measured 2026-10-24):
- **Context:** `indic-translate` has a 32,768-token context. The gateway rejects (413) prompts over **14,894
  tokens** and keeps the rest for the answer, about 1.2× the prompt. English runs about 5 characters a token, so
  about 70k characters per request. Indic text runs 2–3 characters a token, so selections are capped at 20,000
  characters.
- **Rate:** the headers advertise 120 requests per key and 10 in parallel, but **indic-translate allows 15
  requests, then 429s**, while the headers still say 119 left. The window looked like about 60 s, and retries that
  hit a 429 count against it.
- **What the client does about it:** it paces live Bodhan calls to `BODHAN_PER_MINUTE` (default 15) per model,
  and waits a full window after a 429. The OCR and transliterate limits are unmeasured; the same default applies.

**Inline markup** survives translation like this:
- **Styling tags** (probed 2026-10-25, 9 calls): `indic-translate` keeps HTML tags (`<b>`, `<i>`, `<sup>`) and
  moves them onto the translated words, even when the word order changes. That was exact in 4 of 5 (hi, ta, bn).
  Bengali once returned a nameless closing `</>`, and Tamil once pulled the final full stop inside `<i>`.
- **Colour spans** (probed 2026-10-27): `<span style="color:#…">`, alone or around `<b>`, came back exact and on
  the right words in 4 of 4.
- **Square brackets** (`[b]…[/b]`): not reliable; Tamil dropped them.
- **The result:** styled runs travel as HTML tags, parsed tolerantly, with plain text as the fallback
  (`backend/pipeline/markup.py`).

**Formula placeholders** (probed 2026-10-27): standalone `⟦1⟧`, `⟦2⟧`… in running text are kept and moved with the
word order (hi 2/2, ta 2/2, bn 1/2). Bengali writes the numbers in Bengali digits (`⟦২⟧`), and once dropped one
placeholder. So placeholders are read in any script's digits, and a block that loses one is translated piece by
piece between its formulas.

**Footnote markers** placed right after a full stop or comma are often dropped. So markers leave the text before
translation and are put back after their sentence; powers like "2⁸" stay in place.

**Error envelope:** `{"error": {"message", "type", "param", "code"}}`, where `code` is the HTTP status as a string
(`"400"`), not the symbolic codes in the docs.

## OpenRouter

| Use | Model | Cost |
| :--- | :--- | :--- |
| Prompt edits | `anthropic/claude-sonnet-5.5` (`edit.EDIT_MODEL`) | $0.002–0.01 per edit (it writes the whole section back); about $0.002 for a change of language, where it only names the language and Bodhan translates |
| Translation judge (`scripts/evaluate.py`) | `google/gemini-2.5-flash-lite` (`OPENROUTER_MODEL`) | well under $0.001 a request |
| Heading pass (short headings revised after Bodhan) | `anthropic/claude-sonnet-5.5` | about $0.001 per heading |
| Structure review (a page image with its blocks outlined) | `anthropic/claude-sonnet-5.5` | about $0.01 per page |

Avoid `:free` models, which were rate-limited upstream. Avoid reasoning models too: they can spend the whole
`max_tokens` on thinking. `OpenRouterClient.chat(..., use_cache=False)` forces a fresh answer (the edit menu's "Try
again").

## How the client protects the credits

`backend/clients/`:

- **Request cache:** the response to each request is stored under `<data_dir>/cache/<host>/<model>/<sha256>.json`,
  keyed by the request's path and body, so nothing is paid for twice. OCR images are stored as `<sha256:…>`
  references.
- **Usage ledger:** every call, cache hits and failures included, appends a line to `<data_dir>/usage.jsonl`.
  `GET /api/usage` totals it per host and model.
- **Bounded and paced:** at most 4 Bodhan calls run at a time per client, live Bodhan calls are paced, and
  429/500/503/504 are retried twice with backoff. Other errors raise `ApiError` (`status`, `kind`, `message`).
- **Nothing wasted:** blank text is never sent, nor is text already in the target language. Page numbers, codes
  and numbers pass through unchanged.

## The mock server

`mock_server/` is a small FastAPI app that serves the same paths, request and response shapes, and errors as Bodhan
and OpenRouter. The backend talks to it by default (`BODHAN_BASE_URL` and `OPENROUTER_BASE_URL` decide), so the
real client code (headers, errors, retries, caching) runs in development and in the tests.

```bash
uv run uvicorn mock_server.app:app --port 9000   # start it
uv run pytest mock_server                         # its tests
```

It answers from these sources, in order. Each response says which in its `x-mock-source` header (`replay`,
`synthetic`, `forward` or `injected`):

1. **Replay:** a request matching a recording gets the real response back. Recordings come from
   `fixtures/recorded/`, `fixtures/synthetic/` and the live request cache (`data/live/cache/…`). Restart the mock
   after live runs so it picks up new recordings.
2. **Synthetic:** fake words in the target script, about 1.3× longer, keeping numbers, punctuation, line breaks and
   HTML tags. OCR returns a plausible fake page layout sized to the image.
3. **Forward** (`MOCK_LLM=forward`): OpenRouter calls go to a free model when readable text matters. Paid models are
   refused.

**Failures on demand:**
- Put `[[mock:429]]` in the input text (also `401`, `403`, `500`, `502`, `truncate`), or
  `POST /_mock/fail {"errors": [...]}`.
- `MOCK_ERROR_RATE=0.1` fails 10% of requests at random.
- Like the live API, it enforces each key's one-model scope (403) and 120 requests per 60 s per key.
- It is stricter than live in one place: transliterate without `target_language` is a 400.

**Stale mock answers:** the backend caches the mock's invented answers too, and those shadow live answers recorded
later for the same request. `uv run scripts/refresh_mock_cache.py` drops them.

## Recording real responses

`scripts/smoke_test.py` makes one tiny real call per API and saves the request, the response and the rate-limit
headers under `fixtures/recorded/` (`--dry-run` shows the requests without sending them). It was run on 2026-10-20
to verify every key and record the formats above.
