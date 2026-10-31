"""Serve real recorded responses back when the same request comes in again.

A record is the JSON written by scripts/smoke_test.py:
    {"request": {"body": ...}, "response": {"status", "headers", "body"}}
An OCR record's image may be a reference "<base64 of path/to/page.png>" (relative to the repo root)
or "<sha256:HEX>" (written by the backend's response cache).
"""

import base64
import hashlib
import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

IMAGE_REF = re.compile(r"^<base64 of (.+)>$")
SHA_REF = re.compile(r"^<sha256:([0-9a-f]{64})>$")
DATA_URI = re.compile(r"^data:image/[\w.+-]+;base64,(.*)$", re.S)


def image_url(body):
    """The image URL of an OCR request, or None if the request isn't shaped like one."""
    try:
        return body["messages"][0]["content"][0]["image_url"]["url"]
    except (KeyError, IndexError, TypeError):
        return None


def decode_image(url, root):
    """Raw image bytes from a data URI or a recorded file reference; None if undecodable."""
    if m := IMAGE_REF.match(url):
        return (root / m.group(1)).read_bytes()
    if m := DATA_URI.match(url):
        try:
            return base64.b64decode(m.group(1), validate=True)
        except ValueError:
            return None
    return None


def request_key(body, root):
    """What makes two requests 'the same' for replay purposes."""
    model = body.get("model")
    if model == "indic-ocr":
        url = image_url(body) or ""
        if m := SHA_REF.match(url):
            digest = m.group(1)
        else:
            image = decode_image(url, root)
            digest = hashlib.sha256(image).hexdigest() if image else None
        return json.dumps([model, digest, body.get("table_format", "html")])
    if model in ("indic-translate", "indic-transliterate"):
        default_script = "native" if model == "indic-translate" else "roman"
        return json.dumps(
            [model, body.get("messages"), body.get("target_language"), body.get("script", default_script)],
            ensure_ascii=False,
        )
    return json.dumps([model, body.get("messages")], ensure_ascii=False, sort_keys=True)


class ReplayStore:
    """Recorded responses from the replay directories, keyed by their request."""

    def __init__(self, dirs, root):
        self.records = {}
        for d in dirs:
            for path in sorted(Path(d).rglob("*.json")):
                try:
                    record = json.loads(path.read_text())
                    key = request_key(record["request"]["body"], root)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    log.warning("skipping replay file %s: %r", path, exc)
                    continue
                self.records[key] = record["response"]
        log.info("loaded %d replay records", len(self.records))

    def get(self, key):
        """The recorded response for a request key, or None."""
        return self.records.get(key)
