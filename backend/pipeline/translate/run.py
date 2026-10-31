"""Translating with Bodhan: one text, one block, a continuation pair, or a document as a background job."""

import asyncio
import html
import re

from ...clients import ApiError
from ...core.models import Translation
from ..markup import PLACEHOLDER, TAG_SPLIT, attach_markers, runs_intact, strip_markers, untagged
from .headings import refine_headings
from .units import HEADINGS, already_in, english_case, finish, has_letters, prepare, sentences, units_of_block


async def translate_text(text, lang, bodhan, call=None):
    """(translation, truncated). Non-text passes through unchanged and free. `call` swaps the model
    (romanisation passes bodhan.transliterate); markers and truncation are handled the same way."""
    if not has_letters(text) or call is None and already_in(text, lang):
        return text, False
    call = call or bodhan.translate
    body, marks = strip_markers(text)
    body = body.strip()
    result = await call(body, lang)
    out, truncated = result.text.strip(), result.truncated
    parts = sentences(body)
    if truncated and len(parts) > 1:
        results = await asyncio.gather(*(translate_text(s, lang, bodhan, call) for s in parts))
        out, truncated = " ".join(r[0] for r in results), any(r[1] for r in results)
    return attach_markers(out, marks), truncated


async def translate_block(block, lang, bodhan):
    """The block translated into `lang` by Bodhan: table cells and HTML text one by one, text with its formulas and
    markers kept; an error translation when Bodhan fails."""
    try:
        tidy = (lambda t, heading=False: english_case(t, heading)) if lang == "en" else (lambda t, heading=False: t)  # noqa: E731
        if block.cells:
            results = await asyncio.gather(*(translate_text(c.text, lang, bodhan) for c in block.cells))
            return Translation(
                cells=[r[0] if already_in(c.text, lang) else tidy(r[0]) for c, r in zip(block.cells, results)],
                status="truncated" if any(r[1] for r in results) else "done",
            )
        if block.html:
            parts = TAG_SPLIT.split(block.html)

            async def one(part):
                """(translated part, truncated) for one piece of table HTML; tags pass through."""
                if not part or part.startswith("<"):
                    return part, False
                out, truncated = await translate_text(html.unescape(part), lang, bodhan)
                return html.escape(out, quote=False), truncated

            results = await asyncio.gather(*(one(p) for p in parts))
            translated = "".join(r[0] for r in results)
            return Translation(
                html=translated,
                text=re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", translated)).strip(),
                status="truncated" if any(r[1] for r in results) else "done",
            )
        sent, formulas, marks = prepare(block)
        out, truncated = await translate_text(sent, lang, bodhan)
        restored = finish(out, formulas, marks)
        if restored is None:  # the model lost or repeated a placeholder: translate the words between formulas
            parts = PLACEHOLDER.split(sent)  # text, number, text, number, ...
            texts = parts[::2]
            results = await asyncio.gather(*(translate_text(t, lang, bodhan) for t in texts))
            spaced = [
                t[: len(t) - len(t.lstrip())] + r[0].strip() + t[len(t.rstrip()) :] if t.strip() else t
                for t, r in zip(texts, results)
            ]  # keep the spaces around each formula
            joined = "".join(
                t + (f"⟦{parts[2 * n + 1]}⟧" if 2 * n + 1 < len(parts) else "") for n, t in enumerate(spaced)
            )
            restored = finish(joined, formulas, marks)
            truncated = any(r[1] for r in results)
        status = "truncated" if truncated else "done"
        if not already_in(sent, lang):
            restored = tidy(restored, block.label in HEADINGS)
        if block.rich:  # live Bodhan keeps <b>/<i> 4 times in 5; otherwise the runs are lost, not the words
            return Translation(text=untagged(restored), rich=restored if runs_intact(restored) else None, status=status)
        return Translation(text=restored, status=status)
    except ApiError as exc:
        return Translation(status="error", error=str(exc))


def joinable(block):
    """Text a continuation can be translated with: no cells or formulas to keep apart (styled runs travel)."""
    return bool(block.text) and not (block.cells or block.html or block.maths)


async def translate_pair(first, second, lang, bodhan):
    """A sentence split across two blocks (a column or page break) translated whole, then cut back at the word
    boundary nearest to where the original broke, in proportion. Styled runs travel as their tags; a half whose
    tags don't come back balanced keeps its words without them."""
    left, right = first.rich or first.text, second.rich or second.text
    joined = (
        left[:-1] + right if re.search(r"[a-zà-ÿ]-$", left) and right[:1].islower() else f"{left} {right}"
    )  # "fol-" + "lowed"
    try:
        out, truncated = await translate_text(joined, lang, bodhan)
    except ApiError as exc:
        return Translation(status="error", error=str(exc)), Translation(status="error", error=str(exc))
    cut = len(out) * len(left) / len(joined)
    outside = [m.start() for m in re.finditer(r"\s", out) if out[: m.start()].count("<") == out[: m.start()].count(">")]
    k = min(outside or [len(out)], key=lambda s: abs(s - cut))
    halves = [out[:k].strip(), out[k:].strip()]
    if lang == "en" and not already_in(untagged(joined), lang):
        halves[0] = english_case(halves[0])
    status = "truncated" if truncated else "done"
    return tuple(
        Translation(text=untagged(h), rich=h if block.rich and runs_intact(h) else None, status=status)
        for h, block in zip(halves, (first, second))
    )


def blocks_to_translate(doc, lang, pages=None, force=False, block_ids=None, include_figures=False):
    """Text inside images and figures only with `include_figures`: it rarely fits its box once
    translated, so the user has to ask for it."""
    wanted = set(pages) if pages is not None else {p.index for p in doc.pages}
    return [
        (p.index, b)
        for p in doc.pages
        if p.index in wanted
        for b in p.blocks
        if b.translatable
        and (block_ids is None or b.id in block_ids)
        and (include_figures or not b.in_figure)
        and (force or lang not in b.translations or b.translations[lang].status == "error")
    ]


def estimate(doc, lang, bodhan, pages=None, force=False, block_ids=None, include_figures=False):
    """What translating would cost: calls, characters, and how many calls are already cached.
    `figure_blocks`: how many sections inside images and figures are (or would be) included."""
    todo = blocks_to_translate(doc, lang, pages, force, block_ids, include_figures)
    figures = sum(b.in_figure for _, b in blocks_to_translate(doc, lang, pages, force, block_ids, True))
    sent = [u for _, b in todo for u in units_of_block(b, lang)]
    cached = sum(1 for u in sent if bodhan.translation_cached(u, lang))
    chars = sum(len(u) for u in sent)
    return {
        "blocks": len(todo),
        "figure_blocks": figures,
        "calls": len(sent),
        "cached_calls": cached,
        "chars": chars,
        # Output is roughly as long as the input; Indic scripts run ~1 token per 2-3 chars.
        "est_output_tokens": round(sum(len(u) for u in sent if not bodhan.translation_cached(u, lang)) / 2.5),
    }


async def translate_document(
    store, doc_id, lang, bodhan, job, pages=None, force=False, block_ids=None, include_figures=False, openrouter=None
):
    """Translate the requested pages/blocks, saving after each page. Progress adds up on `job`,
    so one job can run several languages; the caller marks it done. With `openrouter`, short headings are
    revised after Bodhan (`refine_headings`)."""
    doc = store.load(doc_id)
    todo = blocks_to_translate(doc, lang, pages, force, block_ids, include_figures)
    job.total += len(todo)
    by_page = {}
    for page_index, block in todo:
        by_page.setdefault(page_index, []).append(block)

    by_id = {b.id: b for _, b in todo}
    pairs = [
        (b, by_id[b.continues])
        for _, b in todo
        if b.continues in by_id and joinable(b) and joinable(by_id[b.continues]) and not by_id[b.continues].continues
    ]
    preset = {}
    for (a, b), (ta, tb) in zip(pairs, await asyncio.gather(*(translate_pair(a, b, lang, bodhan) for a, b in pairs))):
        preset[a.id], preset[b.id] = ta, tb

    async def run(block):
        """The block's translation (from a joined pair, or its own), counted on the job."""
        t = preset.get(block.id) or await translate_block(block, lang, bodhan)
        job.done += 1
        if t.status == "error":
            job.failed += 1
        return block.id, t

    for page_index, blocks in by_page.items():
        results = dict(await asyncio.gather(*(run(b) for b in blocks)))
        if openrouter is not None:
            await refine_headings(doc.pages[page_index], results, lang, openrouter)
        async with store.locks[doc_id]:  # merge into the latest copy: edits may have happened meanwhile
            fresh = store.load(doc_id)
            for b in fresh.pages[page_index].blocks:
                if b.id in results:
                    previous = b.translations.get(lang)
                    new = results[b.id]
                    if previous and previous.edits and not force:
                        continue  # never overwrite a reviewer's edit
                    b.translations[lang] = new
            store.save(fresh)
