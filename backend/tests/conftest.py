import io

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import create_app as create_backend
from backend.core.config import Settings
from mock_server.app import ROOT
from mock_server.app import Settings as MockSettings
from mock_server.app import create_app as create_mock

RECORDED = ROOT / "fixtures" / "recorded"
INPUTS = ROOT / "fixtures" / "inputs"
KEYS = {"indic-ocr": "ocr-key", "indic-translate": "translate-key", "indic-transliterate": "translit-key"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_app(tmp_path):
    env = tmp_path / "mock.env"
    env.write_text(
        f"BODHAN_OCR={KEYS['indic-ocr']}\nBODHAN_TRANSLATE={KEYS['indic-translate']}\n"
        f"BODHAN_TRANSLITERATE={KEYS['indic-transliterate']}\n"
    )
    return create_mock(MockSettings(replay_dirs=[RECORDED], env_file=env))


@pytest.fixture
def api(tmp_path, mock_app):
    """The backend, talking to the mock in-process, with its own data dir."""
    settings = Settings(
        bodhan_base_url="http://mock",
        openrouter_base_url="http://mock/api/v1",
        openrouter_model="google/gemini-2.5-flash-lite",
        bodhan_keys=KEYS,
        openrouter_key="or-key",
        data_dir=tmp_path / "data",
    )
    app = create_backend(settings, transport=httpx.ASGITransport(app=mock_app), backoff_s=0)
    with TestClient(app) as client:
        yield client


def fail_next(mock_app, *errors):
    mock_app.state.state.queued_errors.extend(errors)


def png(width=600, height=800):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, "PNG")
    return buf.getvalue()


def upload(api, name):
    r = api.post("/api/documents", files={"file": (name, (INPUTS / name).read_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()
