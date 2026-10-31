"""API clients. Use `make_clients(settings)` so both share one cache and one ledger."""

from .base import ApiError
from .bodhan import BodhanClient, OcrResult, TextResult
from .cache import Cache, cached_for
from .ledger import Ledger
from .openrouter import ChatResult, OpenRouterClient


def make_clients(settings, **kwargs):
    """(BodhanClient, OpenRouterClient) for `settings`, sharing one request cache and usage ledger."""
    cache = Cache(settings.data_dir / "cache")
    ledger = Ledger(settings.data_dir / "usage.jsonl")
    bodhan = BodhanClient(
        settings.bodhan_base_url, settings.bodhan_keys, cache, ledger, per_minute=settings.bodhan_per_minute, **kwargs
    )
    openrouter = OpenRouterClient(
        settings.openrouter_base_url, settings.openrouter_key, settings.openrouter_model, cache, ledger, **kwargs
    )
    return bodhan, openrouter


__all__ = [
    "ApiError",
    "BodhanClient",
    "Cache",
    "cached_for",
    "ChatResult",
    "Ledger",
    "OcrResult",
    "OpenRouterClient",
    "TextResult",
    "make_clients",
]
