"""Persistent response cache: the same request is never paid for twice.

Files live at <root>/<host>/<model>/<sha256>.json in the same record format that
scripts/smoke_test.py writes, so the mock server can replay real cached responses.
Responses are namespaced by host, so mock output can never leak into a real run.
Each document's entries are listed in <root>/_documents/<doc_id>.txt, so they can go with it.
"""

import hashlib
import json
from contextvars import ContextVar
from pathlib import Path

# The document the current request or job works on: the cache files it reads or writes are listed under it. Set by
# the API layer; a job started from a request inherits it (asyncio copies the context into new tasks).
cached_for: ContextVar[str | None] = ContextVar("cached_for", default=None)


class Cache:
    """Request cache on disk: one JSON file per request under <host>/<model>/<sha>.json, so re-runs are free."""

    def __init__(self, root):
        self.root = Path(root)

    @staticmethod
    def key(path, body):
        """The SHA-256 of the request path and body, with keys sorted so equal requests share a file."""
        canonical = json.dumps([path, body], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _file(self, host, model, key):
        return self.root / host / (model or "_").replace("/", "__") / f"{key}.json"

    def _index(self, doc_id):
        return self.root / "_documents" / f"{doc_id}.txt"

    def _note(self, path):
        """List `path` under the current document, if any."""
        if doc_id := cached_for.get():
            index = self._index(doc_id)
            index.parent.mkdir(parents=True, exist_ok=True)
            with index.open("a") as f:
                f.write(f"{path.relative_to(self.root)}\n")

    def get(self, host, model, key):
        """The cached response body, or None."""
        path = self._file(host, model, key)
        try:
            body = json.loads(path.read_text())["response"]["body"]
        except FileNotFoundError:
            return None
        self._note(path)
        return body

    def put(self, host, model, key, request, response):
        """Store a request and its response, writing a temporary file first so a crash never leaves half a file."""
        path = self._file(host, model, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"request": request, "response": response}, ensure_ascii=False, indent=1))
        tmp.replace(path)
        self._note(path)

    def forget(self, doc_id):
        """Delete the cached answers a document used, so it's translated afresh if uploaded again; returns how many.
        An answer another document also used goes too (that document keeps its translations, in its doc.json)."""
        index = self._index(doc_id)
        try:
            paths = set(index.read_text().split())
        except FileNotFoundError:
            return 0
        for rel in paths:
            (self.root / rel).unlink(missing_ok=True)
        index.unlink()
        return len(paths)
