"""Local stand-in for the Bodhan and OpenRouter APIs, so development spends no credits.

Run:
    uv run uvicorn mock_server.app:app --port 9000
Point the app at it:
    BODHAN_BASE_URL=http://localhost:9000
    OPENROUTER_BASE_URL=http://localhost:9000/api/v1

Where responses come from (the `x-mock-source` header says which):
    replay     a real recording whose request matches (fixtures/, or real responses cached in data/live/cache/)
    synthetic  deterministic fake text in the target script / a fake OCR layout
    forward    OpenRouter requests sent on to a real ":free" model (only with MOCK_LLM=forward)
    injected   a failure you asked for

Settings (env vars):
    MOCK_REPLAY_DIRS    colon-separated recording dirs (default: fixtures/recorded, fixtures/synthetic,
                        and the backend's cache of real responses under data/live/cache/)
    MOCK_LATENCY_MS     delay added to every request (default 0)
    MOCK_ERROR_RATE     fraction of requests that fail at random with 429/500 (default 0)
    MOCK_LLM            "echo" (default) or "forward"
    MOCK_FORWARD_MODEL  OpenRouter model for forward mode; must end in ":free"

Injecting failures:
    - put "[[mock:429]]" in the input text (also 401, 403, 500, 502, truncate)
    - POST /_mock/fail {"errors": ["429", "truncate"]} fails the next requests, in order
    - POST /_mock/reset clears queued failures and rate-limit counters

The mock is stricter than the live API in one place: transliterate without `target_language`
is a 400 here, whereas live it silently does the wrong thing.
"""

import asyncio
import copy
import hashlib
import io
import json
import os
import random
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from dotenv import dotenv_values
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from PIL import Image

from . import synthetic
from .languages import REFUSED_LANGS, TRANSLATE_LANGS, TRANSLITERATE_LANGS
from .replay import ReplayStore, decode_image, image_url, request_key

ROOT = Path(__file__).resolve().parent.parent
BODHAN_MODELS = ("indic-ocr", "indic-translate", "indic-transliterate")
KEY_ENV_MODEL = {
    "BODHAN_OCR": "indic-ocr",
    "BODHAN_TRANSLATE": "indic-translate",
    "BODHAN_TRANSLITERATE": "indic-transliterate",
}
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Live limits seen on 2026-10-20; the window length isn't published, 60s is a guess.
RATE_LIMIT, RATE_WINDOW_S, MAX_PARALLEL = 120, 60, 10

MAGIC = re.compile(r"\[\[mock:(\w+)\]\]")
INJECTABLE = {"401", "403", "429", "500", "502", "truncate"}


@dataclass
class Settings:
    """The mock's settings: where recordings live, injected latency and errors, and how to answer OpenRouter."""

    replay_dirs: list[Path]
    latency_ms: int = 0
    error_rate: float = 0.0
    llm_mode: str = "echo"
    forward_model: str = "google/gemma-4-31b-it:free"
    env_file: Path = ROOT / ".env"

    @classmethod
    def from_env(cls):
        """Settings from the MOCK_* environment variables."""
        dirs = os.environ.get(
            "MOCK_REPLAY_DIRS",
            "fixtures/recorded:fixtures/synthetic:data/live/cache/api.bodhan.ai:data/live/cache/openrouter.ai",
        )
        return cls(
            replay_dirs=[ROOT / d for d in dirs.split(":") if d],
            latency_ms=int(os.environ.get("MOCK_LATENCY_MS", "0")),
            error_rate=float(os.environ.get("MOCK_ERROR_RATE", "0")),
            llm_mode=os.environ.get("MOCK_LLM", "echo"),
            forward_model=os.environ.get("MOCK_FORWARD_MODEL", cls.forward_model),
        )


@dataclass
class State:
    """Mutable mock state: failures queued for the next requests, and recent calls per key for rate limiting."""

    queued_errors: deque = field(default_factory=deque)
    calls: dict = field(default_factory=dict)  # api key -> deque of request timestamps


def tokens(text):
    """A rough token count (about three characters per token)."""
    return max(1, len(text) // 3)


# ---------------------------------------------------------------- response builders


def bodhan_error(status, message, type_, param=None):
    """An error response shaped like Bodhan's."""
    return JSONResponse(
        {"error": {"message": message, "type": type_, "param": param, "code": str(status)}}, status_code=status
    )


def openrouter_error(status, message):
    """An error response shaped like OpenRouter's."""
    return JSONResponse({"error": {"message": message, "code": status}}, status_code=status)


def bodhan_completion(model, content, prompt_tokens, finish_reason="stop", blocks=None):
    """A chat completion body shaped like Bodhan's for `model` (with OCR `blocks` when given), usage included."""
    choice = {"finish_reason": finish_reason, "index": 0, "message": {"content": content, "role": "assistant"}}
    body = {"created": int(time.time()), "model": model, "object": "chat.completion"}
    if model == "indic-ocr":
        choice["message"]["provider_specific_fields"] = {"refusal": None}
        choice["provider_specific_fields"] = {}
        body = {"id": f"indic-ocr-{uuid.uuid4().hex}", **body, "choices": [choice]}
    else:
        choice["message"]["provider_specific_fields"] = {"reasoning": None, "refusal": None}
        choice["provider_specific_fields"] = {"token_ids": None, "stop_reason": None, "routed_experts": None}
        body = {
            "id": f"{time.strftime('%Y%m%d')}_{uuid.uuid4()}",
            **body,
            "system_fingerprint": "mock",
            "choices": [choice],
        }
    completion_tokens = tokens(content)
    body["usage"] = {
        "completion_tokens": completion_tokens,
        "prompt_tokens": prompt_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if blocks is not None:
        body["blocks"] = blocks
    return body


def openrouter_completion(model, content, prompt_tokens, finish_reason="stop"):
    """A chat completion body shaped like OpenRouter's, usage and zero cost included."""
    completion_tokens = tokens(content)
    return {
        "id": f"gen-{int(time.time())}-mock{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "provider": "Mock",
        "system_fingerprint": None,
        "service_tier": "default",
        "choices": [
            {
                "index": 0,
                "logprobs": None,
                "finish_reason": finish_reason,
                "native_finish_reason": finish_reason.upper(),
                "message": {"role": "assistant", "content": content, "refusal": None, "reasoning": None},
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost": 0,
            "is_byok": False,
        },
    }


def truncate(body):
    """Cut a completion in half and mark it as stopped by the token budget."""
    choice = body["choices"][0]
    content = choice["message"]["content"]
    choice["message"]["content"] = content[: max(1, len(content) // 2)]
    choice["finish_reason"] = "length"
    return body


# ---------------------------------------------------------------- request helpers


def user_text(body):
    """All plain-text message content, for spotting [[mock:...]] markers."""
    parts = []
    for msg in body.get("messages") or []:
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str):
            parts.append(content)
    return "\n".join(parts)


def single_user_message(body):
    """The text of the one user turn Bodhan's text models accept, or None."""
    messages = body.get("messages")
    if (
        isinstance(messages, list)
        and len(messages) == 1
        and isinstance(messages[0], dict)
        and messages[0].get("role") == "user"
        and isinstance(messages[0].get("content"), str)
    ):
        return messages[0]["content"]
    return None


def bearer(request):
    """The request's bearer token, or ""."""
    auth = request.headers.get("authorization", "")
    return auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""


# ---------------------------------------------------------------- app


def create_app(settings=None):
    """The mock app: Bodhan's routes under /v1, OpenRouter's under /api/v1, and /_mock controls for injecting
    failures."""
    settings = settings or Settings.from_env()
    if settings.llm_mode == "forward" and not settings.forward_model.endswith(":free"):
        raise ValueError("MOCK_FORWARD_MODEL must be a ':free' model so the mock never spends credits")
    env = dotenv_values(settings.env_file) if settings.env_file.exists() else {}
    scoped_keys = {env[k]: model for k, model in KEY_ENV_MODEL.items() if env.get(k)}
    replay = ReplayStore(settings.replay_dirs, ROOT)
    state = State()
    rng = random.Random(0)

    app = FastAPI(title="Bodhan + OpenRouter mock")
    app.state.settings, app.state.state, app.state.replay = settings, state, replay

    def pick_failure(text):
        """The failure to inject for this request, if any."""
        if state.queued_errors:
            return state.queued_errors.popleft()
        if m := MAGIC.search(text):
            return m.group(1)
        if settings.error_rate and rng.random() < settings.error_rate:
            return rng.choice(["429", "500"])
        return None

    def rate_limit(key):
        """Record a call; return (allowed, headers)."""
        now = time.monotonic()
        calls = state.calls.setdefault(key, deque())
        while calls and now - calls[0] > RATE_WINDOW_S:
            calls.popleft()
        allowed = len(calls) < RATE_LIMIT
        if allowed:
            calls.append(now)
        return allowed, {
            "x-ratelimit-api_key-limit-requests": str(RATE_LIMIT),
            "x-ratelimit-api_key-remaining-requests": str(RATE_LIMIT - len(calls)),
            "x-ratelimit-api_key-limit-max_parallel_requests": str(MAX_PARALLEL),
            "x-ratelimit-api_key-remaining-max_parallel_requests": str(MAX_PARALLEL - 1),
        }

    def respond(resp, source, headers=None):
        """`resp` tagged with where its answer came from (x-mock-source) and any extra headers."""
        resp.headers["x-mock-source"] = source
        for k, v in (headers or {}).items():
            resp.headers[k] = v
        return resp

    def injected_bodhan_error(failure, model):
        """The Bodhan error response for an injected failure, as live Bodhan words it."""
        if failure == "401":
            return bodhan_error(
                401, "Authentication Error, Invalid proxy server token passed. (mock)", "token_not_found_in_db", "key"
            )
        if failure == "403":
            return bodhan_error(
                403,
                f"key not allowed to access model. Tried to access {model} (mock)",
                "key_model_access_denied",
                "model",
            )
        if failure == "429":
            return bodhan_error(429, "Rate limit exceeded (mock)", "rate_limit_exceeded_error")
        if failure == "502" or (failure == "truncate" and model == "indic-ocr"):
            return JSONResponse(
                {"detail": "A block exceeded max_tokens; raise max_tokens and retry (mock)"}, status_code=502
            )
        return bodhan_error(500, "Upstream failure (mock)", "internal_error")

    @app.middleware("http")
    async def latency(request, call_next):
        """Delay every request by the configured latency."""
        if settings.latency_ms:
            await asyncio.sleep(settings.latency_ms / 1000)
        return await call_next(request)

    # ------------------------------------------------------------ Bodhan

    @app.get("/v1/models")
    async def models(request: Request):
        """The Bodhan models the key may use (a model-scoped key sees only its own)."""
        key = bearer(request)
        if not key:
            return bodhan_error(401, "Authentication Error, No api key passed in.", "auth_error", "None")
        ids = [scoped_keys[key]] if key in scoped_keys else list(BODHAN_MODELS)
        return {
            "data": [{"id": i, "object": "model", "created": 1677610602, "owned_by": "openai"} for i in ids],
            "object": "list",
        }

    @app.post("/v1/chat/completions")
    async def bodhan_chat(request: Request):
        """Bodhan's chat completions: checks the key, model and rate limit like live Bodhan, then answers OCR,
        translation or transliteration from a recording or synthetically."""
        key = bearer(request)
        if not key:
            return respond(
                bodhan_error(401, "Authentication Error, No api key passed in.", "auth_error", "None"), "injected"
            )
        try:
            body = await request.json()
        except ValueError:
            return bodhan_error(400, "Request body is not valid JSON", "invalid_request_error")
        model = body.get("model")
        if model not in BODHAN_MODELS:
            return bodhan_error(
                400, f"Unknown model {model!r}; expected one of {list(BODHAN_MODELS)}", "invalid_request_error", "model"
            )
        if key in scoped_keys and scoped_keys[key] != model:
            return respond(
                bodhan_error(
                    403,
                    f"key not allowed to access model. This key can only access models=['{scoped_keys[key]}']. "
                    f"Tried to access {model}",
                    "key_model_access_denied",
                    "model",
                ),
                "injected",
            )

        allowed, limit_headers = rate_limit(key)
        if not allowed:
            return respond(
                bodhan_error(429, "Rate limit exceeded (mock)", "rate_limit_exceeded_error"), "injected", limit_headers
            )

        failure = pick_failure(user_text(body))
        if failure in INJECTABLE - {"truncate"} or (failure == "truncate" and model == "indic-ocr"):
            return respond(injected_bodhan_error(failure, model), "injected", limit_headers)

        if model == "indic-ocr":
            resp, source = ocr(body)
        else:
            resp, source = text_model(model, body)
        if failure == "truncate" and isinstance(resp, dict):
            resp, source = truncate(resp), "injected"
        if isinstance(resp, dict):
            resp = JSONResponse(resp)
        return respond(resp, source, limit_headers)

    def replayed(body):
        """The recorded response for `body` (a copy), or None."""
        hit = replay.get(request_key(body, ROOT))
        if hit is None:
            return None
        if hit["status"] == 200:
            return copy.deepcopy(hit["body"])  # truncate() must not modify the stored recording
        return JSONResponse(hit["body"], status_code=hit["status"])

    def text_model(model, body):
        """(response, source) for a translate or transliterate request: the live API's validation errors, a recording,
        or fake text in the target script."""
        text = single_user_message(body)
        if text is None:
            return bodhan_error(
                400,
                "Exactly one user message with string content is required; "
                "system turns and multiple turns are rejected",
                "invalid_prompt",
            ), "synthetic"
        lang = body.get("target_language")
        valid = TRANSLATE_LANGS if model == "indic-translate" else TRANSLITERATE_LANGS
        if lang in REFUSED_LANGS:
            return bodhan_error(
                400,
                f"{lang!r} ({REFUSED_LANGS[lang]}) is not supported: the model was not trained on it.",
                "invalid_request_error",
            ), "synthetic"
        if lang not in valid:
            return bodhan_error(
                400,
                f"target_language {lang!r} is missing or not supported (mock)",
                "invalid_request_error",
                "target_language",
            ), "synthetic"
        script = body.get("script", "native" if model == "indic-translate" else "roman")
        if model == "indic-transliterate" and script not in ("roman", "native"):
            return bodhan_error(
                400, f"script {script!r} is not valid for transliteration", "invalid_request_error", "script"
            ), "synthetic"

        if (hit := replayed(body)) is not None:
            return hit, "replay"
        clean = MAGIC.sub("", text)
        if model == "indic-translate":
            out = synthetic.pseudo_text(clean, "en" if script == "roman" else lang)
        else:
            out = synthetic.pseudo_text(clean, "en" if script == "roman" else lang, ratio=1.0)
        return bodhan_completion(model, out, tokens(text) + 15), "synthetic"

    def ocr(body):
        """(response, source) for an OCR request: a recording, or a fake layout for the page image."""
        image = decode_image(image_url(body) or "", ROOT)
        if not image:
            return JSONResponse({"detail": "The image could not be decoded (mock)"}, status_code=502), "synthetic"
        try:
            with Image.open(io.BytesIO(image)) as img:
                fmt, (width, height) = img.format, img.size
        except Exception:
            return JSONResponse({"detail": "The image could not be decoded (mock)"}, status_code=502), "synthetic"
        if fmt not in ("PNG", "JPEG"):
            return JSONResponse(
                {"detail": f"Only PNG and JPEG are supported, got {fmt} (mock)"}, status_code=502
            ), "synthetic"

        if (hit := replayed(body)) is not None:
            return hit, "replay"
        sha = hashlib.sha256(image).hexdigest()
        blocks = synthetic.ocr_blocks(sha, width, height, body.get("table_format", "html"))
        content = "\n\n".join(b["text"] for b in blocks if b["text"])
        return bodhan_completion("indic-ocr", content, 850, blocks=blocks), "synthetic"

    # ------------------------------------------------------------ OpenRouter

    @app.post("/api/v1/chat/completions")
    async def openrouter_chat(request: Request):
        """OpenRouter's chat completions: a recording, a free model's answer (forward mode) or an echo of the last
        line."""
        if not bearer(request):
            return respond(openrouter_error(401, "No auth credentials found"), "injected")
        try:
            body = await request.json()
        except ValueError:
            return openrouter_error(400, "Request body is not valid JSON")
        model = body.get("model", "")
        failure = pick_failure(user_text(body))
        if failure in INJECTABLE - {"truncate"}:
            status = int(failure)
            return respond(openrouter_error(status, "Provider returned error (mock)"), "injected")

        if (hit := replayed(body)) is not None:
            resp, source = hit, "replay"
        elif settings.llm_mode == "forward":
            resp, source = await forward(body), "forward"
        else:
            last = user_text(body).splitlines()[-1:] or [""]
            content = f"[mock {model}] {MAGIC.sub('', last[0])}".strip()
            if max_tokens := body.get("max_tokens"):
                content = content[: max_tokens * 4]
            if "You revise one section" in str(body.get("messages", [{}])[0].get("content", "")):
                content = json.dumps({"translation": content, "style": {}}, ensure_ascii=False)  # an edit is JSON
            resp, source = openrouter_completion(model, content, tokens(user_text(body))), "synthetic"

        if failure == "truncate" and isinstance(resp, dict):
            resp, source = truncate(resp), "injected"
        if isinstance(resp, dict):
            resp = JSONResponse(resp)
        return respond(resp, source)

    async def forward(body):
        """The request answered by a real free OpenRouter model."""
        key = env.get("OPENROUTER")
        if not key:
            return openrouter_error(500, "MOCK_LLM=forward needs OPENROUTER in .env")
        payload = {**body, "model": settings.forward_model}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(OPENROUTER_URL, json=payload, headers={"Authorization": f"Bearer {key}"})
        return JSONResponse(r.json(), status_code=r.status_code)

    # ------------------------------------------------------------ control

    @app.post("/_mock/fail")
    async def queue_failures(request: Request):
        """Queue failures ("429", "truncate"…) for the next requests, in order."""
        errors = (await request.json()).get("errors", [])
        bad = [e for e in errors if e not in INJECTABLE]
        if bad:
            return JSONResponse({"error": f"unknown failures {bad}; use {sorted(INJECTABLE)}"}, status_code=400)
        state.queued_errors.extend(errors)
        return {"queued": list(state.queued_errors)}

    @app.post("/_mock/reset")
    async def reset():
        """Clear queued failures and rate-limit counters."""
        state.queued_errors.clear()
        state.calls.clear()
        return {"ok": True}

    @app.get("/_mock/state")
    async def mock_state():
        """The mock's settings, queued failures and number of recordings."""
        return {
            "queued_errors": list(state.queued_errors),
            "replay_records": len(replay.records),
            "llm_mode": settings.llm_mode,
            "latency_ms": settings.latency_ms,
            "error_rate": settings.error_rate,
        }

    return app


app = create_app()
