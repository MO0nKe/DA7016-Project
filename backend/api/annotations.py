"""A reader's notes on a document: highlights, comments and text boxes, each on the original or a language view.

Annotation files may still hold "slips" from a removed feature (translations pinned over the page): they stay on
disk, are never listed, and can't be created again.
"""

import time
import uuid

from fastapi import APIRouter, HTTPException

from ..core.languages import LANGUAGES
from ..core.models import Annotation
from .deps import ServicesDep

router = APIRouter(prefix="/api/documents/{doc_id}/annotations", tags=["annotations"])

SLIPS_REMOVED = "translation slips were removed; translations show in the Translation view"


@router.get("", response_model=list[Annotation])
def list_annotations(doc_id: str, svc: ServicesDep):
    """The document's highlights and comments (old translation slips left out)."""
    svc.document(doc_id)
    return [a for a in svc.store.annotations(doc_id) if a.kind != "slip"]


@router.post("", response_model=Annotation)
async def add_annotation(doc_id: str, a: Annotation, svc: ServicesDep):
    """Save a highlight or comment on a page and return it with its new id and creation time."""
    doc = svc.document(doc_id)
    if not 0 <= a.page < len(doc.pages) or not a.rects or any(len(r) != 4 for r in a.rects):
        raise HTTPException(400, "annotation needs a valid page and boxes of 4 numbers")
    if a.kind == "slip":
        raise HTTPException(400, SLIPS_REMOVED)
    if a.lang and a.lang not in LANGUAGES:
        raise HTTPException(400, f"unknown language {a.lang}")
    async with svc.store.locks[f"{doc_id}:annotations"]:
        items = svc.store.annotations(doc_id)
        a.id, a.created = uuid.uuid4().hex[:10], time.strftime("%Y-%m-%dT%H:%M:%S%z")
        svc.store.save_annotations(doc_id, [*items, a])
    return a


@router.put("/{ann_id}", response_model=Annotation)
async def update_annotation(doc_id: str, ann_id: str, a: Annotation, svc: ServicesDep):
    """Replace an annotation's content; its id, creation time, page and view stay."""
    svc.document(doc_id)
    if a.kind == "slip":
        raise HTTPException(400, SLIPS_REMOVED)
    async with svc.store.locks[f"{doc_id}:annotations"]:
        items = svc.store.annotations(doc_id)
        old = next((x for x in items if x.id == ann_id), None)
        if old is None:
            raise HTTPException(404, f"no annotation {ann_id}")
        new = a.model_copy(update={"id": ann_id, "created": old.created, "page": old.page, "lang": old.lang})
        svc.store.save_annotations(doc_id, [new if x.id == ann_id else x for x in items])
    return new


@router.delete("/{ann_id}")
async def delete_annotation(doc_id: str, ann_id: str, svc: ServicesDep):
    """Delete one annotation."""
    svc.document(doc_id)
    async with svc.store.locks[f"{doc_id}:annotations"]:
        items = svc.store.annotations(doc_id)
        if not any(x.id == ann_id for x in items):
            raise HTTPException(404, f"no annotation {ann_id}")
        svc.store.save_annotations(doc_id, [x for x in items if x.id != ann_id])
    return {"deleted": ann_id}
