"""Translation: estimates, translating a document (a background job) and following its progress, and translating
or romanising a selected snippet (shown, not stored)."""

import asyncio

from fastapi import APIRouter, HTTPException

from ..clients import ApiError
from ..core.jobs import Job
from ..pipeline.translate import estimate, translate_document, translate_text
from .deps import ServicesDep, check_lang, parse_list, parse_pages
from .schemas import RomaniseRequest, TextRequest, TranslateRequest

router = APIRouter(prefix="/api", tags=["translation"])

# The live context allows 14,894 prompt tokens; Indic text runs ~2-3 chars per token.
MAX_SNIPPET_CHARS = 20_000


@router.get("/documents/{doc_id}/estimate")
def translation_estimate(
    doc_id: str,
    langs: str,
    svc: ServicesDep,
    pages: str | None = None,
    blocks: str | None = None,
    force: bool = False,
    include_figures: bool = False,
):
    """Cost of translating before doing it, per language and in total; `minutes` is the wait at the live rate limit
    (null on the mock)."""
    codes = parse_list(langs) or []
    for lang in codes:
        check_lang(lang)
    doc = svc.document(doc_id)
    rows = {
        lang: estimate(doc, lang, svc.bodhan, parse_pages(pages), force, parse_list(blocks), include_figures)
        for lang in codes
    }
    calls = sum(r["calls"] - r["cached_calls"] for r in rows.values())
    per_minute = svc.settings.bodhan_per_minute
    return {
        "languages": rows,
        "blocks": sum(r["blocks"] for r in rows.values()),
        "figure_blocks": max((r["figure_blocks"] for r in rows.values()), default=0),
        "calls": sum(r["calls"] for r in rows.values()),
        "uncached_calls": calls,
        "est_output_tokens": sum(r["est_output_tokens"] for r in rows.values()),
        "minutes": round(calls / per_minute, 1) if per_minute else None,
    }


@router.post("/documents/{doc_id}/translate", response_model=Job)
async def translate(doc_id: str, req: TranslateRequest, svc: ServicesDep):
    """Start translating (one language after another); poll the returned job. Waits for a running structure review
    first, so the reviewed blocks are the ones translated."""
    if not req.langs:
        raise HTTPException(400, "choose at least one language")
    for lang in req.langs:
        check_lang(lang)
    if (own := svc.document(doc_id).source_lang) in req.langs:
        raise HTTPException(400, f"the document is already in {own}")
    if running := [j for j in svc.jobs.running_for(doc_id) if j.kind != "structure"]:
        raise HTTPException(409, f"job {running[0].id} is already running for this document")

    async def work(job):
        """Translate the document into each requested language in turn."""
        if svc.jobs.running_for(doc_id, "structure"):  # translate the reviewed blocks, not the ones it replaces
            job.phase = "layout"
            await svc.jobs.wait(doc_id, "structure")
            job.phase = None
        for lang in req.langs:  # one language at a time, so the first finishes first
            await translate_document(
                svc.store,
                doc_id,
                lang,
                svc.bodhan,
                job,
                req.pages,
                req.force,
                req.block_ids,
                req.include_figures,
                svc.openrouter,
            )

    return svc.jobs.start("translate", doc_id, req.langs, work)


@router.delete("/documents/{doc_id}/translations/{lang}")
async def remove_translation(doc_id: str, lang: str, svc: ServicesDep):
    """Remove a language from the document: every section's translation into it, edits included."""
    check_lang(lang)
    if any(lang in j.langs for j in svc.jobs.running_for(doc_id, "translate")):
        raise HTTPException(409, "it is being translated into this language")
    async with svc.store.locks[doc_id]:
        doc = svc.document(doc_id)
        removed = sum(b.translations.pop(lang, None) is not None for p in doc.pages for b in p.blocks)
        svc.store.save(doc)
    return {"removed": removed}


@router.get("/documents/{doc_id}/job", response_model=Job | None)
def document_job(doc_id: str, svc: ServicesDep):
    """The document's running job, if any (so a reopened document shows its progress); a translation first."""
    svc.document(doc_id)
    running = sorted(svc.jobs.running_for(doc_id), key=lambda j: j.kind == "structure")
    return running[0] if running else None


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str, svc: ServicesDep):
    """A job's status and progress (done and failed of total); poll until it is no longer running."""
    if job_id not in svc.jobs.jobs:
        raise HTTPException(404, f"no job {job_id}")
    return svc.jobs.jobs[job_id]


@router.post("/translate-text")
async def translate_snippet(req: TextRequest, svc: ServicesDep):
    """Translate highlighted text into each language; shown to the user, not stored in the document."""
    if not req.text.strip():
        raise HTTPException(400, "nothing selected")
    if len(req.text) > MAX_SNIPPET_CHARS:
        raise HTTPException(
            413,
            f"selection is {len(req.text):,} characters; select less than "
            f"{MAX_SNIPPET_CHARS:,} (Bodhan's context limit)",
        )
    for lang in req.langs:
        check_lang(lang)

    async def one(lang):
        """The snippet in `lang`, or the error Bodhan gave."""
        cached = svc.bodhan.translation_cached(req.text, lang)
        try:
            text, truncated = await translate_text(req.text, lang, svc.bodhan)
            return {"lang": lang, "text": text, "truncated": truncated, "cached": cached, "error": None}
        except ApiError as exc:
            return {"lang": lang, "text": "", "truncated": False, "cached": False, "error": str(exc)}

    return await asyncio.gather(*(one(lang) for lang in req.langs))


@router.post("/transliterate-text")
async def transliterate_snippet(req: RomaniseRequest, svc: ServicesDep):
    """Translated text in Latin script (Bodhan transliterate); not stored, repeats come from cache."""
    check_lang(req.lang)
    if req.lang == "en":
        raise HTTPException(400, "English is already in Latin script")
    if not req.text.strip():
        raise HTTPException(400, "nothing to romanise")
    if len(req.text) > MAX_SNIPPET_CHARS:
        raise HTTPException(413, f"select less than {MAX_SNIPPET_CHARS:,} characters")
    try:
        text, truncated = await translate_text(req.text, req.lang, svc.bodhan, svc.bodhan.transliterate)
    except ApiError as exc:
        raise HTTPException(502, f"Bodhan: {exc}") from exc
    return {"text": text, "truncated": truncated}
