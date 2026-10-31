"""Shared HTTP plumbing: cache lookup, bounded parallelism, retries, ledger entries."""

import asyncio
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

import httpx

KEEP_HEADERS = ("x-request-id", "content-type")
KEEP_HEADER_PREFIXES = ("x-ratelimit-",)
WINDOW_S = 60  # per_minute pacing window


class ApiError(Exception):
    """A failed API call: the service, HTTP status (0 for network or setup errors), message and the provider's error
    kind."""

    def __init__(self, service, status, message, kind=None, request_id=None):
        super().__init__(f"{service} {status} {kind or ''}: {message}".replace("  ", " "))
        self.service, self.status, self.message, self.kind, self.request_id = service, status, message, kind, request_id


def parse_error(service, status, payload):
    """Bodhan: {"error": {"message", "type"}} or {"detail"}; OpenRouter: {"error": {"message", "code"}}."""
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        message = err.get("message", "")
        raw = (err.get("metadata") or {}).get("raw")  # OpenRouter puts the provider's reason here
        return ApiError(
            service,
            status,
            f"{message} ({raw})" if raw else message,
            kind=err.get("type") or str(err.get("code", "")),
            request_id=err.get("request_id"),
        )
    if isinstance(payload, dict) and "detail" in payload:
        return ApiError(service, status, str(payload["detail"]))
    return ApiError(service, status, str(payload)[:500])


class JsonApiClient:
    """Async JSON POST client with a request cache, a usage ledger, retries with backoff, bounded parallelism and
    optional per-minute pacing."""

    service = "api"
    retryable = frozenset({429, 500, 503, 504})

    def __init__(
        self,
        base_url,
        cache,
        ledger,
        *,
        transport=None,
        max_retries=2,
        backoff_s=1.0,
        max_parallel=4,
        timeout_s=120,
        per_minute=None,
    ):
        self.host = (urlsplit(base_url).netloc or "local").replace(":", "_")
        self.cache, self.ledger = cache, ledger
        self.max_retries, self.backoff_s = max_retries, backoff_s
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/") + "/", transport=transport, timeout=timeout_s)
        self._slots = asyncio.Semaphore(max_parallel)  # live limit is 10 parallel per key
        self.per_minute = per_minute
        self._starts = defaultdict(deque)  # model -> recent request start times
        self._turns = defaultdict(asyncio.Lock)

    async def _wait_turn(self, model):
        """At most `per_minute` requests per model in any rolling window (Bodhan throttles per model,
        and failed retries still count, so pacing beats retrying into the limit)."""
        if not self.per_minute:
            return
        starts = self._starts[model]
        async with self._turns[model]:
            while True:
                now = time.monotonic()
                while starts and now - starts[0] >= WINDOW_S:
                    starts.popleft()
                if len(starts) < self.per_minute:
                    starts.append(now)
                    return
                await asyncio.sleep(WINDOW_S - (now - starts[0]) + 0.1)

    async def aclose(self):
        """Close the HTTP connection pool."""
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    async def post(self, path, body, key, *, record_body=None, use_cache=True):
        """POST JSON and return (response body, came_from_cache).

        `record_body` is what gets written to the cache file in place of `body`
        (e.g. with a large inline image replaced by its hash).
        """
        model = body.get("model")
        cache_key = self.cache.key(path, body)
        if use_cache and (hit := self.cache.get(self.host, model, cache_key)) is not None:
            self.ledger.record(
                service=self.service, model=model, host=self.host, status=200, cached=True, usage=hit.get("usage")
            )
            return hit, True

        for attempt in range(self.max_retries + 1):
            await self._wait_turn(model)
            started = time.monotonic()
            try:
                async with self._slots:
                    resp = await self._http.post(
                        path.lstrip("/"), json=body, headers={"Authorization": f"Bearer {key}"}
                    )
            except httpx.TransportError as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_s * 2**attempt)
                    continue
                raise ApiError(self.service, 0, f"network error: {exc!r}") from exc
            elapsed = round(time.monotonic() - started, 3)
            try:
                payload = resp.json()
            except ValueError:
                payload = {"_raw_text": resp.text}
            self.ledger.record(
                service=self.service,
                model=model,
                host=self.host,
                status=resp.status_code,
                cached=False,
                usage=payload.get("usage"),
                elapsed_s=elapsed,
                request_id=resp.headers.get("x-request-id") or payload.get("id"),
            )
            if resp.is_success:
                headers = {
                    k: v for k, v in resp.headers.items() if k in KEEP_HEADERS or k.startswith(KEEP_HEADER_PREFIXES)
                }
                self.cache.put(
                    self.host,
                    model,
                    cache_key,
                    request={"url": str(resp.url), "body": record_body or body},
                    response={"status": resp.status_code, "headers": headers, "body": payload},
                )
                return payload, False
            if resp.status_code in self.retryable and attempt < self.max_retries:
                if resp.status_code == 429 and self.per_minute:
                    # Our count is off (e.g. another process used the key): treat the window as full.
                    starts = self._starts[model]
                    starts.clear()
                    starts.extend([time.monotonic()] * self.per_minute)
                else:
                    # A 429 means the rate-limit window is full: wait much longer than for a 5xx blip.
                    factor = 5 if resp.status_code == 429 else 1
                    await asyncio.sleep(self.backoff_s * factor * 2**attempt)
                continue
            raise parse_error(self.service, resp.status_code, payload)
