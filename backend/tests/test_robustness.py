"""Adversarial inputs: uploads that aren't usable PDFs, odd file names, and bad requests get a clear 4xx, never a
crash; readable edge cases (a blank page, an unsupported language, a permissions-only PDF) still open."""

import io

import pymupdf


def pdf_bytes(text=None, **save):
    doc = pymupdf.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 100), text, fontsize=11)
    out = io.BytesIO()
    doc.save(out, **save)
    return out.getvalue()


def upload(api, data, name="test.pdf"):
    return api.post("/api/documents", files={"file": (name, data, "application/pdf")})


def test_unusable_uploads_are_refused_clearly(api):
    english = pdf_bytes("A sentence about rural health care in the district.")
    refused = {
        b"hello, not a pdf": "not a PDF",
        b"": "not a PDF",
        b"%PDF-1.7\n": "damaged",
        english[:300]: "damaged",  # truncated
        b"%PDF-1.4\n" + bytes(range(256)) * 40: "damaged",
        pdf_bytes("Secret.", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o"): "password",
    }
    for data, reason in refused.items():
        r = upload(api, data)
        assert r.status_code == 400 and reason in r.json()["detail"]
    assert api.get("/api/documents").json() == []  # nothing half-made was left behind


def test_readable_edge_cases_still_open(api):
    locked = pdf_bytes("Permissions only, readable text.", encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o")
    assert upload(api, locked).json()["source_lang"] == "en"
    blank = upload(api, pdf_bytes()).json()
    assert blank["page_count"] == 1 and blank["source_lang"] is None
    french = upload(api, pdf_bytes("Ceci est un document en français sur la santé rurale et les médecins.")).json()
    assert french["source_lang"] is None and french["unsupported_lang"]  # the studio says it can't translate it
    named = upload(api, pdf_bytes("A normal English sentence about the weather."), "../../etc/passwd.pdf").json()
    assert named["filename"] == "passwd.pdf"  # a name, never a path


def test_bad_requests_get_clear_errors(api):
    assert api.get("/api/documents/zzzzzzzzzzzz").status_code == 404
    assert api.get("/api/documents/..%2F..").status_code == 404
    assert api.post("/api/translate-text", json={"text": "hello", "langs": ["xx"]}).status_code == 400
    assert api.post("/api/translate-text", json={"text": "  ", "langs": ["hi"]}).status_code == 400
    assert api.post("/api/translate-text", json={"text": "a" * 30000, "langs": ["hi"]}).status_code == 413
    doc = upload(api, pdf_bytes("A sentence about rural health care in the district.")).json()
    r = api.post(f"/api/documents/{doc['id']}/translate", json={"langs": ["en"]})
    assert r.status_code == 400 and "already in" in r.json()["detail"]  # into its own language
