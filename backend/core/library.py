"""Folders for organising documents: one library.json with the folder tree and each document's folder.

Documents stay where they are on disk; a folder is only a label. Deleting a folder moves its
documents and subfolders up to its parent, so no document is ever lost.
"""

import json
import uuid
from pathlib import Path

from pydantic import BaseModel, Field


class Folder(BaseModel):
    """A library folder; `parent` is None at the top level."""

    id: str = ""
    name: str = Field(min_length=1, max_length=100)
    parent: str | None = None


class Library(BaseModel):
    """The folder tree and which folder each document is in (unplaced documents sit at the top level)."""

    folders: list[Folder] = Field(default_factory=list)
    placement: dict[str, str] = Field(default_factory=dict)  # document id -> folder id


class LibraryError(Exception):
    """A library change that would break the tree: an unknown folder, or a folder moved inside itself."""


class LibraryStore:
    """The library (folders and placements), kept in one JSON file."""

    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        """The saved library, or an empty one."""
        return Library.model_validate_json(self.path.read_text()) if self.path.exists() else Library()

    def _save(self, lib):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(lib.model_dump(), ensure_ascii=False, indent=1))

    def _check_parent(self, lib, folder_id, parent):
        ids = {f.id for f in lib.folders}
        if parent is not None and parent not in ids:
            raise LibraryError(f"no folder {parent}")
        seen = parent  # walking up from the new parent must never reach the folder itself
        while seen is not None:
            if seen == folder_id:
                raise LibraryError("a folder can't be moved inside itself")
            seen = next(f.parent for f in lib.folders if f.id == seen)

    def add_folder(self, folder):
        """Save a new folder under its parent and return it with its new id."""
        lib = self.load()
        self._check_parent(lib, None, folder.parent)
        folder.id = uuid.uuid4().hex[:10]
        lib.folders.append(folder)
        self._save(lib)
        return folder

    def update_folder(self, folder_id, name=None, parent=...):  # parent=... means "unchanged"
        """Rename or move a folder and return it; a KeyError for an unknown folder."""
        lib = self.load()
        folder = next((f for f in lib.folders if f.id == folder_id), None)
        if folder is None:
            raise KeyError(folder_id)
        if name is not None:
            folder.name = Folder(name=name).name
        if parent is not ...:
            self._check_parent(lib, folder_id, parent)
            folder.parent = parent
        self._save(lib)
        return folder

    def delete_folder(self, folder_id):
        """Delete a folder; its subfolders and documents move up to its parent."""
        lib = self.load()
        folder = next((f for f in lib.folders if f.id == folder_id), None)
        if folder is None:
            raise KeyError(folder_id)
        for f in lib.folders:
            if f.parent == folder_id:
                f.parent = folder.parent
        for doc_id, fid in list(lib.placement.items()):
            if fid == folder_id:
                if folder.parent:
                    lib.placement[doc_id] = folder.parent
                else:
                    del lib.placement[doc_id]
        lib.folders.remove(folder)
        self._save(lib)

    def place(self, doc_id, folder_id):
        """Put a document in a folder, or at the top level when `folder_id` is None."""
        lib = self.load()
        if folder_id is None:
            lib.placement.pop(doc_id, None)
        else:
            if folder_id not in {f.id for f in lib.folders}:
                raise LibraryError(f"no folder {folder_id}")
            lib.placement[doc_id] = folder_id
        self._save(lib)

    def forget(self, doc_id):
        """Drop a deleted document's placement."""
        lib = self.load()
        if lib.placement.pop(doc_id, None):
            self._save(lib)
