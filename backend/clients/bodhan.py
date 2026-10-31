"""Bodhan models, all through /v1/chat/completions (the documented /translate and
/transliterate routes 404 live). Each model has its own API key."""

import base64
import hashlib
from dataclasses import dataclass, field

from .base import ApiError, JsonApiClient

CHAT_PATH = "/v1/chat/completions"
OCR_DEFAULT_MAX_TOKENS = 2048
OCR_RETRY_MAX_TOKENS = 4096


@dataclass
class TextResult:
    """A text model's answer, and whether it hit the token budget."""

    text: str
    truncated: bool  # output hit the token budget; reads fluently but stops early
    usage: dict = field(default_factory=dict)
    cached: bool = False


@dataclass
class OcrResult:
    """One page's OCR: its Markdown and its layout blocks in reading order."""

    markdown: str
    blocks: list  # [{order, label, type, bbox_xyxy, conf, text}] in reading order
    usage: dict = field(default_factory=dict)
    cached: bool = False


def _image_mime(image):
    if image.startswith(b"\x89PNG"):
        return "image/png"
    if image.startswith(b"\xff\xd8"):
        return "image/jpeg"
    raise ValueError("indic-ocr accepts PNG or JPEG only")


class BodhanClient(JsonApiClient):
    """Client for Bodhan's OCR, translation and transliteration models, each with its own API key."""

    service = "bodhan"

    def __init__(self, base_url, keys, cache, ledger, **kwargs):
        super().__init__(base_url, cache, ledger, **kwargs)
        self.keys = keys  # model id -> key

    def _key(self, model):
        if not self.keys.get(model):
            raise ApiError(self.service, 0, f"no API key configured for {model}")
        return self.keys[model]

    @staticmethod
    def _text_body(model, text, extra):
        return {"model": model, "messages": [{"role": "user", "content": text}], **extra}

    def translation_cached(self, text, target_language, script=None):
        """Would translate() be answered from the cache (i.e. free)?"""
        extra = {"target_language": target_language, **({"script": script} if script else {})}
        body = self._text_body("indic-translate", text, extra)
        return self.cache.get(self.host, "indic-translate", self.cache.key(CHAT_PATH, body)) is not None

    async def _text_model(self, model, text, extra):
        if not text.strip():
            return TextResult(text=text, truncated=False)  # don't pay for whitespace
        body = self._text_body(model, text, extra)
        payload, cached = await self.post(CHAT_PATH, body, self._key(model))
        choice = payload["choices"][0]
        return TextResult(
            text=choice["message"]["content"],
            truncated=choice.get("finish_reason") == "length",
            usage=payload.get("usage", {}),
            cached=cached,
        )

    async def translate(self, text, target_language, script=None):
        """Translate into `target_language`; the source language is inferred."""
        extra = {"target_language": target_language}
        if script:
            extra["script"] = script
        return await self._text_model("indic-translate", text, extra)

    async def transliterate(self, text, target_language, script="roman"):
        """Rewrite `text` (written in `target_language`) into another script, without translating.

        Live wants `target_language`, not the documented `language`; unknown fields are ignored silently.
        """
        return await self._text_model(
            "indic-transliterate", text, {"target_language": target_language, "script": script}
        )

    async def ocr(self, image, table_format="html", max_tokens=None):
        """Layout + text of one page image (PNG/JPEG bytes)."""
        url = f"data:{_image_mime(image)};base64,{base64.b64encode(image).decode()}"
        sha_ref = f"<sha256:{hashlib.sha256(image).hexdigest()}>"

        def body(image_url, tokens):
            """The OCR request body for `image_url`, with a token budget when `tokens` is set."""
            b = {
                "model": "indic-ocr",
                "table_format": table_format,
                "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": image_url}}]}],
            }
            if tokens:
                b["max_tokens"] = tokens
            return b

        try:
            payload, cached = await self.post(
                CHAT_PATH, body(url, max_tokens), self._key("indic-ocr"), record_body=body(sha_ref, max_tokens)
            )
        except ApiError as exc:
            # 502 means a block (usually a big table) overflowed max_tokens: retry once with more room.
            if exc.status != 502 or (max_tokens or OCR_DEFAULT_MAX_TOKENS) >= OCR_RETRY_MAX_TOKENS:
                raise
            return await self.ocr(image, table_format, OCR_RETRY_MAX_TOKENS)
        return OcrResult(
            markdown=payload["choices"][0]["message"]["content"],
            blocks=payload.get("blocks", []),
            usage=payload.get("usage", {}),
            cached=cached,
        )
