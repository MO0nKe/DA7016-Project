from backend.core.models import Block
from backend.pipeline.edit import build_messages
from backend.pipeline.glossary import Term, occurs

from .conftest import upload
from .test_render import translate


def test_whole_word_match():
    assert occurs("rice", "Rice and wheat") and not occurs("rice", "the price of wheat")


def test_glossary_flags_sections_missing_a_pinned_term(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    translate(api, doc_id, "hi")
    term = api.post("/api/glossary", json={"source": "attendance", "lang": "hi", "target": "उपस्थिति"}).json()
    found = api.get(f"/api/documents/{doc_id}/glossary-check", params={"lang": "hi"}).json()
    assert found and all(m["missing"][0]["target"] == "उपस्थिति" for m in found)  # mock text never has it
    assert any("Attendance" in m["text"] for m in found)
    # Re-pinning the same term replaces it; deleting empties the list.
    api.post("/api/glossary", json={"source": "Attendance", "lang": "hi", "target": "हाज़िरी"})
    terms = api.get("/api/glossary").json()
    assert [t["target"] for t in terms] == ["हाज़िरी"]
    assert api.delete(f"/api/glossary/{terms[0]['id']}").status_code == 200
    assert api.delete(f"/api/glossary/{term['id']}").status_code == 404
    assert api.post("/api/glossary", json={"source": "", "lang": "hi", "target": "x"}).status_code == 422


def test_prompt_edit_is_told_the_pinned_terms():
    block = Block(
        id="b",
        order=0,
        label="Paragraph",
        type="Text",
        bbox=[0, 0, 1, 1],
        source="text_layer",
        text="Attendance was high.",
    )
    system = build_messages(block, "hi", "...", "x", [Term(source="Attendance", lang="hi", target="उपस्थिति")])[0]
    assert '"Attendance" → "उपस्थिति"' in system["content"]
