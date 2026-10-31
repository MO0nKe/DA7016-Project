"""Clients against the mock server, wired in-process (no network, no credits)."""

import json

import httpx
import pytest

from backend.clients import ApiError, BodhanClient, Cache, Ledger, OpenRouterClient
from backend.core.config import Settings as BackendSettings
from backend.core.config import load_settings
from mock_server.app import ROOT, create_app
from mock_server.app import Settings as MockSettings

from .conftest import KEYS, RECORDED, fail_next, png

pytestmark = pytest.mark.anyio


@pytest.fixture
def cache(tmp_path):
    return Cache(tmp_path / "cache")


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "usage.jsonl")


@pytest.fixture
async def bodhan(mock_app, cache, ledger):
    async with BodhanClient(
        "http://mock", KEYS, cache, ledger, transport=httpx.ASGITransport(app=mock_app), backoff_s=0
    ) as client:
        yield client


@pytest.fixture
async def openrouter(mock_app, cache, ledger):
    async with OpenRouterClient(
        "http://mock/api/v1",
        "or-key",
        "google/gemini-2.5-flash-lite",
        cache,
        ledger,
        transport=httpx.ASGITransport(app=mock_app),
        backoff_s=0,
    ) as client:
        yield client


# ------------------------------------------------------------ translate / transliterate


async def test_translate_then_cache_hit(bodhan, ledger):
    first = await bodhan.translate("The library opens at nine.", "ta")
    second = await bodhan.translate("The library opens at nine.", "ta")
    assert any("஀" <= ch <= "௿" for ch in first.text)
    assert (first.cached, second.cached) == (False, True)
    assert second.text == first.text
    assert [e["cached"] for e in ledger.entries()] == [False, True]


async def test_recorded_translation_is_replayed(bodhan):
    rec = json.loads((RECORDED / "translate.json").read_text())
    result = await bodhan.translate(rec["request"]["body"]["messages"][0]["content"], "hi")
    assert result.text == rec["response"]["body"]["choices"][0]["message"]["content"]


async def test_blank_text_makes_no_call(bodhan, ledger):
    result = await bodhan.translate("   \n", "hi")
    assert result.text == "   \n"
    assert ledger.entries() == []


async def test_truncation_is_reported(bodhan, mock_app):
    fail_next(mock_app, "truncate")
    result = await bodhan.translate("A sentence long enough to be cut in half by the mock.", "hi")
    assert result.truncated


async def test_transliterate_to_roman(bodhan):
    result = await bodhan.transliterate("नया पुस्तकालय", "hi")
    assert result.text.isascii()


# ------------------------------------------------------------ retries and errors


async def test_429_is_retried(bodhan, mock_app, ledger):
    fail_next(mock_app, "429")
    result = await bodhan.translate("Retry me.", "hi")
    assert result.text
    assert [e["status"] for e in ledger.entries()] == [429, 200]


async def test_gives_up_after_max_retries(bodhan, mock_app, ledger):
    fail_next(mock_app, "500", "500", "500")
    with pytest.raises(ApiError) as exc:
        await bodhan.translate("Never works.", "hi")
    assert exc.value.status == 500
    assert len(ledger.entries()) == 3


async def test_failed_calls_are_not_cached(bodhan, mock_app, cache):
    fail_next(mock_app, "403")
    with pytest.raises(ApiError):
        await bodhan.translate("Denied.", "hi")
    assert not list(cache.root.rglob("*.json"))


async def test_wrong_key_for_model_is_a_403(mock_app, cache, ledger):
    keys = {**KEYS, "indic-ocr": KEYS["indic-translate"]}
    async with BodhanClient(
        "http://mock", keys, cache, ledger, transport=httpx.ASGITransport(app=mock_app), backoff_s=0
    ) as client:
        with pytest.raises(ApiError) as exc:
            await client.ocr(png())
    assert exc.value.status == 403
    assert exc.value.kind == "key_model_access_denied"


async def test_unsupported_language_is_not_retried(bodhan, ledger):
    with pytest.raises(ApiError) as exc:
        await bodhan.translate("Hello", "bho")
    assert exc.value.status == 400
    assert len(ledger.entries()) == 1


# ------------------------------------------------------------ OCR


async def test_ocr_replays_recorded_page(bodhan):
    page = (ROOT / "fixtures/inputs/sample_page.png").read_bytes()
    result = await bodhan.ocr(page)
    assert result.blocks[1]["label"] == "Section-title"
    assert "Translation Studio" in result.markdown


async def test_ocr_synthetic_page_and_cache_record_omits_image(bodhan, cache):
    result = await bodhan.ocr(png())
    assert any(b["label"] == "Table" for b in result.blocks)
    [record] = [json.loads(p.read_text()) for p in cache.root.rglob("*.json")]
    url = record["request"]["body"]["messages"][0]["content"][0]["image_url"]["url"]
    assert url.startswith("<sha256:")


async def test_ocr_502_retries_with_more_tokens(bodhan, mock_app, ledger):
    fail_next(mock_app, "502")
    result = await bodhan.ocr(png())
    assert result.blocks
    assert [e["status"] for e in ledger.entries()] == [502, 200]


async def test_ocr_rejects_other_formats(bodhan):
    with pytest.raises(ValueError):
        await bodhan.ocr(b"GIF89a...")


# ------------------------------------------------------------ OpenRouter


async def test_openrouter_chat_and_regenerate(openrouter, ledger):
    messages = [{"role": "user", "content": "Make this formal: see you"}]
    first = await openrouter.chat(messages)
    again = await openrouter.chat(messages)
    fresh = await openrouter.chat(messages, use_cache=False)
    assert "Make this formal" in first.text
    assert (first.cached, again.cached, fresh.cached) == (False, True, False)
    assert [e["cached"] for e in ledger.entries()] == [False, True, False]


async def test_openrouter_error_includes_provider_reason(openrouter, mock_app):
    fail_next(mock_app, "401")
    with pytest.raises(ApiError) as exc:
        await openrouter.chat([{"role": "user", "content": "hi"}])
    assert exc.value.status == 401


# ------------------------------------------------------------ cache and ledger


async def test_cache_is_separate_per_host(mock_app, cache, ledger):
    transport = httpx.ASGITransport(app=mock_app)
    async with (
        BodhanClient("http://mock", KEYS, cache, ledger, transport=transport) as a,
        BodhanClient("http://other-host", KEYS, cache, ledger, transport=transport) as b,
    ):
        await a.translate("Same text.", "hi")
        result = await b.translate("Same text.", "hi")
    assert not result.cached


async def test_cached_real_response_is_replayed_by_mock(bodhan, cache, tmp_path):
    """The mock can serve what the cache saved: point it at the cache dir and ask again."""
    image = png(700, 900)
    original = await bodhan.ocr(image)
    replaying_mock = create_app(MockSettings(replay_dirs=[cache.root / "mock"], env_file=tmp_path / "none.env"))
    async with BodhanClient(
        "http://mock",
        KEYS,
        Cache(tmp_path / "fresh-cache"),
        Ledger(tmp_path / "l.jsonl"),
        transport=httpx.ASGITransport(app=replaying_mock),
    ) as client:
        again = await client.ocr(image)
    assert again.blocks == original.blocks


async def test_ledger_summary(bodhan, openrouter, ledger):
    await bodhan.translate("One.", "hi")
    await bodhan.translate("One.", "hi")
    await openrouter.chat([{"role": "user", "content": "hi"}])
    rows = {row["model"]: row for row in ledger.summary()}
    assert rows["indic-translate"]["calls"] == 1
    assert rows["indic-translate"]["cache_hits"] == 1
    assert rows["indic-translate"]["completion_tokens"] > 0
    assert rows["google/gemini-2.5-flash-lite"]["calls"] == 1


# ------------------------------------------------------------ settings


def test_settings_default_to_mock(tmp_path, monkeypatch):
    for var in ("BODHAN_BASE_URL", "OPENROUTER_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    env = tmp_path / ".env"
    env.write_text("BODHAN_TRANSLATE=abc\n")
    settings = load_settings(env)
    assert isinstance(settings, BackendSettings)
    assert settings.bodhan_base_url.startswith("http://localhost")
    assert not settings.spends_credits
    assert settings.bodhan_keys["indic-translate"] == "abc"
    # Against the mock, a missing key gets a stand-in (it accepts any), so trying the app needs no .env.
    assert settings.bodhan_keys["indic-ocr"] and settings.openrouter_key


def test_real_url_is_flagged(tmp_path, monkeypatch):
    for var in ("BODHAN_TRANSLATE", "OPENROUTER", "OPENROUTER_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BODHAN_BASE_URL", "https://api.bodhan.ai")
    settings = load_settings(tmp_path / "missing.env")
    assert settings.spends_credits
    assert settings.bodhan_keys["indic-translate"] == "" and settings.openrouter_key  # no stand-in for the real API


async def test_per_minute_pacing_and_429_pause(mock_app, cache, ledger, monkeypatch):
    from backend.clients import base

    monkeypatch.setattr(base, "WINDOW_S", 0.3)
    async with BodhanClient(
        "http://mock", KEYS, cache, ledger, transport=httpx.ASGITransport(app=mock_app), per_minute=2
    ) as client:
        import time

        start = time.monotonic()
        for text in ("One.", "Two.", "Three."):
            await client.translate(text, "hi")
        assert time.monotonic() - start >= 0.3  # the third call waited for the window
        fail_next(mock_app, "429")
        start = time.monotonic()
        assert (await client.translate("Four.", "hi")).text
        assert time.monotonic() - start >= 0.3  # after a 429 the whole window is waited out
