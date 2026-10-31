"""Persistent response cache: the same request is never paid for twice.

Files live at <root>/<host>/<model>/<sha256>.json in the same record format that
scripts/smoke_test.py writes, so the mock server can replay real cached responses.
Responses are namespaced by host, so mock output can never leak into a real run.
"""

import hashlib
import json
from pathlib import Path


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

    def get(self, host, model, key):
        """The cached response body, or None."""
        try:
            return json.loads(self._file(host, model, key).read_text())["response"]["body"]
        except FileNotFoundError:
            return None

    def put(self, host, model, key, request, response):
        """Store a request and its response, writing a temporary file first so a crash never leaves half a file."""
        path = self._file(host, model, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"request": request, "response": response}, ensure_ascii=False, indent=1))
        tmp.replace(path)
