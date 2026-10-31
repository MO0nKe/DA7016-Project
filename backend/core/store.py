"""Documents on disk: data/documents/<id>/{source.pdf, doc.json, pages/*.png}."""

import asyncio
import json
import shutil
from collections import defaultdict
from pathlib import Path

from .models import Annotation, Document


class DocumentStore:
    """Documents on disk: one folder per document holding doc.json, its rasters, fonts and annotations."""

    def __init__(self, root):
        self.root = Path(root)
        self.locks = defaultdict(asyncio.Lock)  # hold while read-modify-writing one document

    def dir(self, doc_id):
        """The document's folder; a KeyError for an id that isn't alphanumeric, so it can't name a path."""
        if not doc_id.isalnum():
            raise KeyError(doc_id)
        return self.root / doc_id

    def exists(self, doc_id):
        """Whether the document has been saved."""
        return (self.dir(doc_id) / "doc.json").exists()

    def load(self, doc_id):
        """The saved document, or a KeyError."""
        try:
            return Document.model_validate_json((self.dir(doc_id) / "doc.json").read_text())
        except FileNotFoundError:
            raise KeyError(doc_id) from None

    def save(self, doc):
        """Write the document's doc.json, through a temporary file so a crash never leaves half a file."""
        path = self.dir(doc.id) / "doc.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc.model_dump(), ensure_ascii=False, indent=1))
        tmp.replace(path)

    def annotations(self, doc_id):
        """The document's annotations, or [] when it has none."""
        path = self.dir(doc_id) / "annotations.json"
        if not path.exists():
            return []
        return [Annotation.model_validate(a) for a in json.loads(path.read_text())]

    def save_annotations(self, doc_id, items):
        """Replace the document's annotations with `items`."""
        path = self.dir(doc_id) / "annotations.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps([a.model_dump() for a in items], ensure_ascii=False, indent=1))
        tmp.replace(path)

    def list(self):
        """Every saved document, newest first."""
        if not self.root.exists():
            return []
        docs = [self.load(d.name) for d in self.root.iterdir() if (d / "doc.json").exists()]
        return sorted(docs, key=lambda d: d.created, reverse=True)

    def delete(self, doc_id):
        """Delete the document's folder and everything in it."""
        shutil.rmtree(self.dir(doc_id), ignore_errors=True)
