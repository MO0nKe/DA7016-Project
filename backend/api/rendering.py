"""Rendering: a page or one block as an HTML fragment for the studio, and the whole document as one printable page.
The fragments need /api/static/render.css and fit.js on the host page (mounted by `create_app`)."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..pipeline.render import render_block, render_document, render_page
from .deps import ServicesDep, asset_url, background_url, find_block, font_urls, original_url, page_of

router = APIRouter(prefix="/api/documents", tags=["rendering"])


@router.get("/{doc_id}/pages/{index}/render", response_class=HTMLResponse)
def render_page_fragment(doc_id: str, index: int, svc: ServicesDep, lang: str | None = None):
    """One page: the original raster with the sections translated into `lang` drawn over it."""
    doc = svc.document(doc_id)
    page = page_of(doc, index)
    return render_page(
        page,
        lang,
        background_url(doc_id, page),
        font_urls(doc),
        asset=asset_url(doc_id),
        image_url=original_url(doc_id, page),
    )


@router.get("/{doc_id}/blocks/{block_id}/render", response_class=HTMLResponse)
def render_block_fragment(doc_id: str, block_id: str, svc: ServicesDep, lang: str | None = None):
    """Just one block, so an edit re-renders only that section."""
    doc = svc.document(doc_id)
    page, block = find_block(doc, block_id)
    return render_block(
        block, page, lang, fonts=doc.fonts, asset=asset_url(doc_id), crop=background_url(doc_id, page) if lang else None
    )


@router.get("/{doc_id}/preview", response_class=HTMLResponse)
def preview(doc_id: str, svc: ServicesDep, lang: str | None = None):
    """The whole document as one printable HTML page."""
    doc = svc.document(doc_id)
    return render_document(doc, lang, lambda p: background_url(doc_id, p), font_url=asset_url(doc_id))
