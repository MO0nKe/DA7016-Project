import base64
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mock_server.app import ROOT, Settings, create_app

RECORDED = ROOT / "fixtures" / "recorded"
AUTH = {"Authorization": "Bearer test-key"}


@pytest.fixture
def client(tmp_path):
    env = tmp_path / ".env"
    env.write_text("BODHAN_OCR=ocr-key\nBODHAN_TRANSLATE=translate-key\nBODHAN_TRANSLITERATE=translit-key\n")
    return TestClient(create_app(Settings(replay_dirs=[RECORDED], env_file=env)))


def recording(name):
    return json.loads((RECORDED / f"{name}.json").read_text())


def shape(obj):
    """Key structure of a JSON value, ignoring the values themselves."""
    if isinstance(obj, dict):
        return {k: shape(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [shape(obj[0])] if obj else []
    return None


def translate(client, text, lang="hi", **extra):
    body = {
        "model": "indic-translate",
        "messages": [{"role": "user", "content": text}],
        "target_language": lang,
        **extra,
    }
    return client.post("/v1/chat/completions", json=body, headers=AUTH)


def png_data_uri(width=800, height=1000, fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, fmt)
    return f"data:image/{fmt.lower()};base64,{base64.b64encode(buf.getvalue()).decode()}"


def ocr(client, url, **extra):
    body = {
        "model": "indic-ocr",
        "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}]}],
        **extra,
    }
    return client.post("/v1/chat/completions", json=body, headers=AUTH)


# ------------------------------------------------------------ replay


@pytest.mark.parametrize("name", ["translate", "transliterate", "ocr"])
def test_recorded_bodhan_request_is_replayed(client, name):
    rec = recording(name)
    body = rec["request"]["body"]
    if name == "ocr":
        page = (ROOT / "fixtures/inputs/sample_page.png").read_bytes()
        body["messages"][0]["content"][0]["image_url"]["url"] = (
            "data:image/png;base64," + base64.b64encode(page).decode()
        )
    r = client.post("/v1/chat/completions", json=body, headers=AUTH)
    assert r.status_code == 200
    assert r.headers["x-mock-source"] == "replay"
    assert r.json() == rec["response"]["body"]


def test_recorded_openrouter_request_is_replayed(client):
    rec = recording("openrouter")
    r = client.post("/api/v1/chat/completions", json=rec["request"]["body"], headers=AUTH)
    assert r.headers["x-mock-source"] == "replay"
    assert r.json() == rec["response"]["body"]


# ------------------------------------------------------------ synthetic responses match live shapes


def test_synthetic_translate_has_live_shape(client):
    r = translate(client, "A sentence nobody recorded.")
    assert r.headers["x-mock-source"] == "synthetic"
    assert shape(r.json()) == shape(recording("translate")["response"]["body"])
    assert r.headers["x-ratelimit-api_key-limit-requests"] == "120"


def test_synthetic_transliterate_has_live_shape(client):
    body = {
        "model": "indic-transliterate",
        "messages": [{"role": "user", "content": "नया वाक्य"}],
        "target_language": "hi",
        "script": "roman",
    }
    r = client.post("/v1/chat/completions", json=body, headers=AUTH)
    assert r.headers["x-mock-source"] == "synthetic"
    assert shape(r.json()) == shape(recording("transliterate")["response"]["body"])
    assert r.json()["choices"][0]["message"]["content"].isascii()


def test_synthetic_ocr_has_live_shape(client):
    r = ocr(client, png_data_uri())
    assert r.headers["x-mock-source"] == "synthetic"
    assert shape(r.json()) == shape(recording("ocr")["response"]["body"])
    blocks = r.json()["blocks"]
    assert all(0 <= b["bbox_xyxy"][0] < b["bbox_xyxy"][2] <= 800 for b in blocks)
    assert all(0 <= b["bbox_xyxy"][1] < b["bbox_xyxy"][3] <= 1000 for b in blocks)
    assert any(b["label"] == "Table" and b["text"].startswith("<table>") for b in blocks)


def test_synthetic_openrouter_has_live_shape(client):
    body = {"model": "some/model", "messages": [{"role": "user", "content": "Make this formal."}]}
    r = client.post("/api/v1/chat/completions", json=body, headers=AUTH)
    assert r.headers["x-mock-source"] == "synthetic"
    expected = shape(recording("openrouter")["response"]["body"])
    actual = shape(r.json())
    # Live usage carries extra cost breakdowns the app doesn't need.
    expected["usage"] = {k: None for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cost", "is_byok")}
    assert actual == expected


# ------------------------------------------------------------ synthetic text


def test_translation_uses_target_script_and_keeps_structure(client):
    text = "Total: 42 items.\n<table><tr><td>Rice</td></tr></table>"
    out = translate(client, text, lang="ta").json()["choices"][0]["message"]["content"]
    assert "42" in out and "\n" in out
    assert "<table><tr><td>" in out and "</td></tr></table>" in out
    assert any("஀" <= ch <= "௿" for ch in out)  # Tamil block
    assert "Rice" not in out


def test_translation_keeps_formula_placeholders(client):
    out = translate(client, "the state ⟦1⟧ of ⟦2⟧s grows.", lang="hi").json()["choices"][0]["message"]["content"]
    assert out.count("⟦1⟧") == 1 and out.count("⟦2⟧") == 1


def test_translation_is_deterministic_and_longer(client):
    text = "The meeting has been postponed to next week."
    first = translate(client, text + " x").json()["choices"][0]["message"]["content"]
    second = translate(client, text + " x").json()["choices"][0]["message"]["content"]
    assert first == second
    assert len(first) > len(text)
    assert first.endswith("।") or "।" in first  # Hindi full stop


# ------------------------------------------------------------ validation and auth


def test_missing_key_is_401(client):
    r = client.post("/v1/chat/completions", json={"model": "indic-translate"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "401"


def test_key_scoped_to_another_model_is_403(client):
    body = {"model": "indic-ocr", "messages": []}
    r = client.post("/v1/chat/completions", json=body, headers={"Authorization": "Bearer translate-key"})
    assert r.status_code == 403
    assert r.json()["error"]["type"] == "key_model_access_denied"


def test_models_lists_only_the_keys_model(client):
    r = client.get("/v1/models", headers={"Authorization": "Bearer translit-key"})
    assert [m["id"] for m in r.json()["data"]] == ["indic-transliterate"]


def test_refused_language_is_400(client):
    r = translate(client, "Hello", lang="bho")
    assert r.status_code == 400
    assert "not supported" in r.json()["error"]["message"]


def test_transliterate_requires_target_language(client):
    body = {"model": "indic-transliterate", "messages": [{"role": "user", "content": "नमस्ते"}], "language": "hi"}
    r = client.post("/v1/chat/completions", json=body, headers=AUTH)
    assert r.status_code == 400


def test_system_turn_is_rejected(client):
    body = {
        "model": "indic-translate",
        "target_language": "hi",
        "messages": [{"role": "system", "content": "Be formal"}, {"role": "user", "content": "Hi"}],
    }
    r = client.post("/v1/chat/completions", json=body, headers=AUTH)
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "invalid_prompt"


def test_undecodable_or_gif_image_is_502(client):
    assert ocr(client, "data:image/png;base64,not-base64!!").status_code == 502
    assert ocr(client, png_data_uri(fmt="GIF")).status_code == 502


# ------------------------------------------------------------ failure injection


def test_magic_marker_injects_429(client):
    r = translate(client, "Hello [[mock:429]]")
    assert r.status_code == 429
    assert r.headers["x-mock-source"] == "injected"


def test_queued_truncate_sets_finish_reason_length(client):
    client.post("/_mock/fail", json={"errors": ["truncate"]})
    r = translate(client, "A fairly long sentence that will be cut in half.")
    assert r.json()["choices"][0]["finish_reason"] == "length"
    assert translate(client, "Next one is fine.").json()["choices"][0]["finish_reason"] == "stop"


def test_truncate_on_ocr_is_502_like_live(client):
    client.post("/_mock/fail", json={"errors": ["truncate"]})
    assert ocr(client, png_data_uri()).status_code == 502


def test_truncate_does_not_corrupt_replay(client):
    body = recording("translate")["request"]["body"]
    client.post("/_mock/fail", json={"errors": ["truncate"]})
    client.post("/v1/chat/completions", json=body, headers=AUTH)
    r = client.post("/v1/chat/completions", json=body, headers=AUTH)
    assert r.json() == recording("translate")["response"]["body"]


def test_rate_limit_after_120_requests(client):
    for _ in range(120):
        assert translate(client, "Hi").status_code == 200
    r = translate(client, "Hi")
    assert r.status_code == 429
    assert r.headers["x-ratelimit-api_key-remaining-requests"] == "0"
    client.post("/_mock/reset")
    assert translate(client, "Hi").status_code == 200


def test_forward_mode_refuses_paid_models():
    with pytest.raises(ValueError):
        create_app(Settings(replay_dirs=[], llm_mode="forward", forward_model="openai/gpt-5-nano"))
