"""The library: the folder tree and which folder each document is in."""

from fastapi import APIRouter, HTTPException

from ..core.library import Folder, Library, LibraryError
from .deps import ServicesDep
from .schemas import FolderUpdate, Placement

router = APIRouter(prefix="/api", tags=["library"])


@router.get("/library", response_model=Library)
def get_library(svc: ServicesDep):
    """The folder tree and which folder each document is in."""
    return svc.library.load()


@router.post("/folders", response_model=Folder)
def add_folder(folder: Folder, svc: ServicesDep):
    """Create a folder and return it with its id."""
    try:
        return svc.library.add_folder(folder)
    except LibraryError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/folders/{folder_id}", response_model=Folder)
def update_folder(folder_id: str, req: FolderUpdate, svc: ServicesDep):
    """Rename a folder and/or move it under another (`move`: set `parent`, None = top level)."""
    try:
        return svc.library.update_folder(folder_id, req.name, req.parent if req.move else ...)
    except KeyError:
        raise HTTPException(404, f"no folder {folder_id}") from None
    except (LibraryError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: str, svc: ServicesDep):
    """Its documents and subfolders move up to its parent."""
    try:
        svc.library.delete_folder(folder_id)
    except KeyError:
        raise HTTPException(404, f"no folder {folder_id}") from None
    return {"deleted": folder_id}


@router.put("/documents/{doc_id}/folder")
def move_document(doc_id: str, req: Placement, svc: ServicesDep):
    """Move the document into a folder, or to the top level when `folder_id` is null."""
    svc.document(doc_id)
    try:
        svc.library.place(doc_id, req.folder_id)
    except LibraryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"doc_id": doc_id, "folder_id": req.folder_id}
