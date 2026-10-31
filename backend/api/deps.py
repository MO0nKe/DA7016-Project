"""What every route needs: the app's shared services, and lookups that turn ids into objects or a 404."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from ..clients import BodhanClient, OpenRouterClient, cached_for
from ..core.config import Settings
from ..core.jobs import JobManager
from ..core.languages import LANGUAGES
from ..core.library import LibraryStore
from ..core.models import Block, Document, Page
from ..core.store import DocumentStore
from ..pipeline.glossary import Glossary


@dataclass
class Services:
    """The app's long-lived objects, created once by `create_app` and shared by every request."""

    settings: Settings
    store: DocumentStore
    library: LibraryStore
    glossary: Glossary
    jobs: JobManager
    bodhan: BodhanClient
    openrouter: OpenRouterClient

    def document(self, doc_id: str) -> Document:
        """The stored document, or a 404."""
        try:
            return self.store.load(doc_id)
        except KeyError:
            raise HTTPException(404, f"no document {doc_id}") from None


async def services(request: Request) -> Services:
    """The shared `Services`, for injection into route handlers. A request about a document marks the API answers
    cached while serving it (and by any job it starts) as that document's. Async, so the mark reaches the handler."""
    if doc_id := request.path_params.get("doc_id"):
        cached_for.set(doc_id)
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(services)]


def page_of(doc: Document, index: int) -> Page:
    """The document's page at `index`, or a 404."""
    if not 0 <= index < len(doc.pages):
        raise HTTPException(404, f"no page {index}")
    return doc.pages[index]


def find_block(doc: Document, block_id: str) -> tuple[Page, Block]:
    """(the page holding the block, the block), or a 404."""
    for page in doc.pages:
        for block in page.blocks:
            if block.id == block_id:
                return page, block
    raise HTTPException(404, f"no block {block_id}")


def check_lang(lang: str) -> None:
    """Reject (400) a language code Bodhan doesn't support."""
    if lang not in LANGUAGES:
        raise HTTPException(400, f"unsupported language {lang!r}")


def parse_list(value: str | None) -> list[str] | None:
    """ "a,b" from a query string as ["a", "b"]; None when absent."""
    return [v for v in value.split(",") if v.strip()] if value else None


def parse_pages(pages: str | None) -> list[int] | None:
    """ "0,2" from a query string as [0, 2]; None when absent."""
    return [int(p) for p in pages.split(",") if p.strip()] if pages else None


# URLs the rendered HTML points at (served by the documents and rendering routers).


def background_url(doc_id: str, page: Page) -> str:
    """The page with its text removed, which translations are drawn over."""
    return f"/api/documents/{doc_id}/pages/{page.index}/background.png"


def original_url(doc_id: str, page: Page) -> str:
    """The page as the original PDF draws it."""
    return f"/api/documents/{doc_id}/pages/{page.index}/original.png"


def asset_url(doc_id: str):
    """URL of a file in the document's folder (fonts, formula crops), by its path there."""
    return lambda rel: f"/api/documents/{doc_id}/{rel}"


def font_urls(doc: Document) -> dict[str, str]:
    """The document's reusable embedded fonts: PDF font name -> URL."""
    return {name: f"/api/documents/{doc.id}/{rel}" for name, rel in doc.fonts.items()}
