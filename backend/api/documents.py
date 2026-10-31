"""Documents: upload (ingest, then the structure review in the background), list, get, delete, their files (source
PDF, page images, embedded fonts, formula crops), the outline, OCR of scanned pages, and an on-request structure
review."""

import asyncio
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..clients import ApiError, cached_for
from ..core.models import Document, DocumentSummary
from ..pipeline.ingest import UnreadablePDF, ingest_pdf, ocr_page
from ..pipeline.outline import outline
from ..pipeline.structure import link_next_pages, review_page
from .deps import Services, ServicesDep
from .schemas import PagesRequest

router = APIRouter(prefix="/api/documents", tags=["documents"])

STRUCTURE_PARALLEL = 4  # pages reviewed at once on upload (one OpenRouter call each, about 10 s)


@router.post("", response_model=DocumentSummary)
async def upload(file: UploadFile, svc: ServicesDep):
    """Ingest a PDF (free; an already-uploaded file returns its document) and start the structure review of its
    text-layer pages in the background."""
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "not a PDF")
    name = PurePosixPath((file.filename or "").replace("\\", "/")).name or "document.pdf"  # a name, never a path
    try:
        doc = ingest_pdf(data, name, svc.store)
    except UnreadablePDF as exc:
        raise HTTPException(400, str(exc)) from exc
    cached_for.set(doc.id)  # the structure review's answers are this document's
    pages = [p.index for p in doc.pages if p.source == "text_layer" and p.blocks and p.review is None]
    if pages and not svc.jobs.running_for(doc.id):
        svc.jobs.start("structure", doc.id, [], lambda job: _review_structure_job(svc, doc.id, pages, job))
    return DocumentSummary.of(doc)


async def _review_structure_job(svc: Services, doc_id: str, pages: list[int], job):
    """The vision structure review of a new upload's text-layer pages, a few at a time. Each page is reviewed on a
    copy and swapped in under the lock, so the slow model call doesn't hold the document."""
    job.total = len(pages)
    gate = asyncio.Semaphore(STRUCTURE_PARALLEL)

    async def one(i):
        """Review page `i`, counting it done or failed on the job."""
        async with gate:
            copy = svc.document(doc_id)
            try:
                await review_page(copy, i, svc.store, svc.openrouter)
            except ApiError:
                job.failed += 1
            else:
                async with svc.store.locks[doc_id]:
                    fresh = svc.document(doc_id)
                    fresh.pages[i].blocks, fresh.pages[i].review = copy.pages[i].blocks, copy.pages[i].review
                    svc.store.save(fresh)
            job.done += 1

    await asyncio.gather(*(one(i) for i in pages))
    async with svc.store.locks[doc_id]:
        fresh = svc.document(doc_id)
        link_next_pages(fresh)
        svc.store.save(fresh)


@router.get("", response_model=list[DocumentSummary])
def list_documents(svc: ServicesDep):
    """Every stored document, as library summaries."""
    return [DocumentSummary.of(d) for d in svc.store.list()]


@router.get("/{doc_id}", response_model=Document)
def get_document(doc_id: str, svc: ServicesDep):
    """The full document model: pages, blocks and their translations."""
    return svc.document(doc_id)


@router.delete("/{doc_id}")
def delete_document(doc_id: str, svc: ServicesDep):
    """Delete the document, its files, its place in the library and the cached API answers it used."""
    svc.document(doc_id)
    svc.store.delete(doc_id)
    svc.library.forget(doc_id)
    svc.bodhan.cache.forget(doc_id)  # the same cache serves both clients
    return {"deleted": doc_id}


@router.get("/{doc_id}/source.pdf")
def source_pdf(doc_id: str, svc: ServicesDep):
    """The uploaded PDF as it was."""
    svc.document(doc_id)
    return FileResponse(svc.store.dir(doc_id) / "source.pdf", media_type="application/pdf")


@router.get("/{doc_id}/outline")
def document_outline(doc_id: str, svc: ServicesDep):
    """Sections and chapters for the side panel."""
    return outline(svc.document(doc_id), svc.store.dir(doc_id) / "source.pdf")


@router.get("/{doc_id}/pages/{index}/{kind}.png")
def page_image(doc_id: str, index: int, kind: str, svc: ServicesDep):
    """The page raster (`original`) or the same page with its text removed (`background`)."""
    doc = svc.document(doc_id)
    if not 0 <= index < len(doc.pages) or kind not in ("original", "background"):
        raise HTTPException(404)
    page = doc.pages[index]
    return FileResponse(
        svc.store.dir(doc_id) / (page.image if kind == "original" else page.background), media_type="image/png"
    )


@router.get("/{doc_id}/fonts/{filename}")
def document_font(doc_id: str, filename: str, svc: ServicesDep):
    """An embedded font from the PDF, reused so re-rendered text looks like the original."""
    doc = svc.document(doc_id)
    rel = f"fonts/{filename}"
    if rel not in doc.fonts.values():
        raise HTTPException(404, f"no font {filename}")
    return FileResponse(svc.store.dir(doc_id) / rel, media_type="font/ttf" if rel.endswith(".ttf") else "font/otf")


@router.get("/{doc_id}/maths/{filename}")
def maths_crop(doc_id: str, filename: str, svc: ServicesDep):
    """A crop of an inline formula from the original page, drawn in place of its text."""
    doc = svc.document(doc_id)
    rel = f"maths/{filename}"
    if not any(m.image == rel for p in doc.pages for b in p.blocks for m in b.maths):
        raise HTTPException(404, f"no formula {filename}")
    return FileResponse(svc.store.dir(doc_id) / rel, media_type="image/png")


@router.post("/{doc_id}/ocr", response_model=Document)
async def run_ocr(doc_id: str, req: PagesRequest, svc: ServicesDep):
    """OCR the given pages with Bodhan (one call per page; cached afterwards)."""
    async with svc.store.locks[doc_id]:
        doc = svc.document(doc_id)
        for i in req.pages:
            if not 0 <= i < len(doc.pages):
                raise HTTPException(400, f"no page {i}")
            try:
                await ocr_page(doc, i, svc.store, svc.bodhan)
            except ApiError as exc:
                raise HTTPException(502, f"OCR failed on page {i}: {exc}") from exc
            svc.store.save(doc)
        return doc


@router.post("/{doc_id}/structure", response_model=Document)
async def review_structure(doc_id: str, req: PagesRequest, svc: ServicesDep):
    """Check how the given text-layer pages were split into blocks with a vision model (OpenRouter, one call per
    page; cached) and apply its fixes. Changed blocks lose their translations."""
    async with svc.store.locks[doc_id]:
        doc = svc.document(doc_id)
        for i in req.pages:
            if not 0 <= i < len(doc.pages):
                raise HTTPException(400, f"no page {i}")
            try:
                await review_page(doc, i, svc.store, svc.openrouter)
            except ApiError as exc:
                raise HTTPException(502, f"structure review failed on page {i}: {exc}") from exc
        link_next_pages(doc)
        svc.store.save(doc)
        return doc
