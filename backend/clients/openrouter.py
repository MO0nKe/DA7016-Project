"""OpenRouter chat completions, for reviewer prompt-edits and other general LLM work."""

from dataclasses import dataclass, field

from .base import JsonApiClient


@dataclass
class ChatResult:
    """A chat model's answer, why it stopped, and its usage."""

    text: str
    finish_reason: str
    usage: dict = field(default_factory=dict)
    cached: bool = False

    @property
    def cost_usd(self):
        """What OpenRouter charged for the call (0 when cached or unreported)."""
        return self.usage.get("cost", 0) or 0


class OpenRouterClient(JsonApiClient):
    """Client for OpenRouter's chat completions, used for prompt edits, headings and the structure review."""

    service = "openrouter"
    retryable = frozenset({429, 500, 502, 503, 504})  # 502 here is a flaky upstream provider

    def __init__(self, base_url, key, default_model, cache, ledger, **kwargs):
        super().__init__(base_url, cache, ledger, **kwargs)
        self.key, self.default_model = key, default_model

    async def chat(self, messages, model=None, max_tokens=None, temperature=None, use_cache=True):
        """`use_cache=False` forces a fresh answer, e.g. when the user asks to regenerate."""
        body = {"model": model or self.default_model, "messages": messages}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        payload, cached = await self.post("/chat/completions", body, self.key, use_cache=use_cache)
        choice = payload["choices"][0]
        return ChatResult(
            text=choice["message"].get("content") or "",
            finish_reason=choice.get("finish_reason", ""),
            usage=payload.get("usage", {}),
            cached=cached,
        )
