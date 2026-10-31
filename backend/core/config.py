"""Settings from the environment and .env (real environment variables win).

Base URLs default to the local mock server, so nothing spends credits unless you point
BODHAN_BASE_URL / OPENROUTER_BASE_URL at the real APIs on purpose.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]  # the repo root (backend/core/config.py)

MOCK_BODHAN_URL = "http://localhost:9000"
MOCK_OPENROUTER_URL = "http://localhost:9000/api/v1"
REAL_BODHAN_URL = "https://api.bodhan.ai"
REAL_OPENROUTER_URL = "https://openrouter.ai/api/v1"


def is_local(url):
    """Whether `url` points at this machine (the mock server)."""
    return urlsplit(url).hostname in ("localhost", "127.0.0.1", "::1")


@dataclass(frozen=True)
class Settings:
    """Where the APIs and data live, and the keys to use them."""

    bodhan_base_url: str
    openrouter_base_url: str
    openrouter_model: str
    bodhan_keys: dict  # model id -> key; each Bodhan key only works for one model
    openrouter_key: str
    data_dir: Path
    bodhan_per_minute: int | None = None  # pace live Bodhan calls; None = unthrottled (mock)

    @property
    def spends_credits(self):
        """Whether either API is a real one, so calls cost money."""
        return not (is_local(self.bodhan_base_url) and is_local(self.openrouter_base_url))


def load_settings(env_file=ROOT / ".env"):
    """Settings from the environment and `.env`. Both base URLs default to the mock, and mock and live keep separate
    data directories."""
    values = {**dotenv_values(env_file), **os.environ}
    bodhan_url = values.get("BODHAN_BASE_URL", MOCK_BODHAN_URL)
    openrouter_url = values.get("OPENROUTER_BASE_URL", MOCK_OPENROUTER_URL)
    # Mock and live runs keep separate documents, so mock translations never pass for real ones.
    live = not (is_local(bodhan_url) and is_local(openrouter_url))
    return Settings(
        bodhan_base_url=bodhan_url,
        openrouter_base_url=openrouter_url,
        openrouter_model=values.get("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite"),
        bodhan_keys={
            "indic-ocr": values.get("BODHAN_OCR", ""),
            "indic-translate": values.get("BODHAN_TRANSLATE", ""),
            "indic-transliterate": values.get("BODHAN_TRANSLITERATE", ""),
        },
        openrouter_key=values.get("OPENROUTER", ""),
        data_dir=ROOT / values.get("DATA_DIR", "data/live" if live else "data/mock"),
        # Live indic-translate allowed 15 requests, then 429s, when measured on 2026-10-24.
        bodhan_per_minute=None if is_local(bodhan_url) else int(values.get("BODHAN_PER_MINUTE", "15")),
    )
