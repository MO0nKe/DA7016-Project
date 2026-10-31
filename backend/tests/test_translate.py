import re
import time

import pytest

from backend.clients import TextResult
from backend.clients.openrouter import ChatResult
from backend.core.models import Block, Document, Edit, Maths, Page, Translation
from backend.pipeline.markup import attach_markers, protect, restore, runs_intact, strip_markers
from backend.pipeline.translate import translate_text
from backend.pipeline.translate.headings import refine_headings
from backend.pipeline.translate.run import blocks_to_translate, translate_block
from backend.pipeline.translate.units import already_in, english_case, sentences, units, units_of_block

from .conftest import upload


class FakeBodhan:
    """Upper-cases text; reports truncation for anything longer than `limit` chars."""

    def __init__(self, limit=10_000):
        self.limit, self.sent = limit, []

    async def translate(self, text, lang, script=None):
        self.sent.append(text)
        return TextResult(text=text.upper(), truncated=len(text) > self.limit)


def test_sentences_keep_markers_with_their_sentence():
    assert sentences("One is here.¹ Two is there. Three") == ["One is here.¹", "Two is there.", "Three"]
    assert sentences("एक वाक्य। दूसरा वाक्य।") == ["एक वाक्य।", "दूसरा वाक्य।"]


def test_units_strip_markers_and_skip_numbers():
    assert units("All good.²") == ["All good."]
    assert units("First claim.¹ Second claim.") == [
        "First claim. Second claim."
    ]  # one call; the marker comes back after its sentence
    assert units("+6.2%") == []
    assert units("7c") == units("b6 e3") == units("A") == []  # hex bytes and lone letters are codes, not words
    assert units("Bed") == ["Bed"] and units("கை") == ["கை"]  # a vowel sign counts towards a word


@pytest.mark.anyio
async def test_markers_survive_translation():
    fake = FakeBodhan()
    assert await translate_text("learning materials.¹", "hi", fake) == ("LEARNING MATERIALS.¹", False)
    assert fake.sent == ["learning materials."]
    out, _ = await translate_text("First claim.¹ Second claim.", "hi", fake)
    assert out == "FIRST CLAIM.¹ SECOND CLAIM."


@pytest.mark.anyio
async def test_truncated_result_is_retried_by_sentence():
    fake = FakeBodhan(limit=20)
    out, truncated = await translate_text("A short one. Another short one.", "hi", fake)
    assert (out, truncated) == ("A SHORT ONE. ANOTHER SHORT ONE.", False)
    assert fake.sent == ["A short one. Another short one.", "A short one.", "Another short one."]


@pytest.mark.anyio
async def test_html_table_translates_text_nodes_only():
    block = Block(
        id="b",
        order=0,
        label="Table",
        type="Table",
        bbox=[0, 0, 1, 1],
        source="ocr",
        html="<table><tr><th>Item &amp; kind</th><td>40</td></tr></table>",
    )
    t = await translate_block(block, "hi", FakeBodhan())
    assert t.html == "<table><tr><th>ITEM &amp; KIND</th><td>40</td></tr></table>"
    assert units_of_block(block) == ["Item & kind"]


def wait_for(api, job_id):
    for _ in range(200):
        job = api.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_translate_document_end_to_end(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    before = api.get(f"/api/documents/{doc_id}/estimate", params={"langs": "ta"}).json()
    assert before["calls"] > 20 and before["languages"]["ta"]["cached_calls"] == 0 and before["minutes"] is None

    started = api.post(f"/api/documents/{doc_id}/translate", json={"langs": ["ta"]}).json()
    running = api.get(f"/api/documents/{doc_id}/job").json()  # a reopened document finds its translation
    assert running is None or running["id"] == started["id"]
    job = wait_for(api, started["id"])
    assert job["status"] == "done" and job["failed"] == 0 and job["done"] == job["total"] == before["blocks"]
    assert api.get(f"/api/documents/{doc_id}/job").json() is None

    doc = api.get(f"/api/documents/{doc_id}").json()
    blocks = {b["text"]: b for p in doc["pages"] for b in p["blocks"]}
    title = blocks["District Education Survey 2025"]["translations"]["ta"]["text"]
    assert any("஀" <= ch <= "௿" for ch in title) and "2025" in title
    intro = next(b for t, b in blocks.items() if t.startswith("This report"))
    assert intro["translations"]["ta"]["text"].endswith("¹")
    table = next(b for b in blocks.values() if b["label"] == "Table")
    cells = table["translations"]["ta"]["cells"]
    assert len(cells) == len(table["cells"]) and cells[5] == "48"
    assert blocks["1"]["translations"] == {}  # page number left alone
    assert api.get("/api/documents").json()[0]["languages"] == ["ta"]

    after = api.get(f"/api/documents/{doc_id}/estimate", params={"langs": "ta", "force": True}).json()
    assert after["uncached_calls"] == 0 and after["est_output_tokens"] == 0


def test_retranslation_keeps_reviewer_edits(api):
    app = api.app
    doc_id = upload(api, "sample_en.pdf")["id"]
    wait_for(api, api.post(f"/api/documents/{doc_id}/translate", json={"langs": ["hi"], "pages": [0]}).json()["id"])
    store = app.state.services.store
    doc = store.load(doc_id)
    block = doc.pages[0].blocks[1]
    block.translations["hi"].text = "EDITED"
    block.translations["hi"].edits.append(Edit(instruction="x", before="a", after="EDITED", model="m", ts="t"))
    block.translations["hi"].status = "error"  # would normally be re-translated
    store.save(doc)
    wait_for(api, api.post(f"/api/documents/{doc_id}/translate", json={"langs": ["hi"], "pages": [0]}).json()["id"])
    assert store.load(doc_id).pages[0].blocks[1].translations["hi"].text == "EDITED"
    assert all("hi" not in b.translations for b in store.load(doc_id).pages[1].blocks)


def test_bad_language_and_errors(api, mock_app):
    doc_id = upload(api, "sample_hi.pdf")["id"]
    assert api.post(f"/api/documents/{doc_id}/translate", json={"langs": ["bho"]}).status_code == 400
    assert api.get("/api/jobs/nope").status_code == 404
    mock_app.state.state.queued_errors.extend(["403"])
    job = wait_for(api, api.post(f"/api/documents/{doc_id}/translate", json={"langs": ["en"]}).json()["id"])
    assert job["status"] == "done" and job["failed"] == 1
    failed = [
        b
        for b in api.get(f"/api/documents/{doc_id}").json()["pages"][0]["blocks"]
        if b["translations"].get("en", {}).get("status") == "error"
    ]
    assert len(failed) == 1 and "403" in failed[0]["translations"]["en"]["error"]


def test_selected_blocks_into_several_languages(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    picked = ["p0-b1", "p0-b3"]
    est = api.get(f"/api/documents/{doc_id}/estimate", params={"langs": "hi,ta", "blocks": ",".join(picked)}).json()
    assert est["blocks"] == 4 and set(est["languages"]) == {"hi", "ta"}
    job = wait_for(
        api,
        api.post(f"/api/documents/{doc_id}/translate", json={"langs": ["hi", "ta"], "block_ids": picked}).json()["id"],
    )
    assert job["status"] == "done" and job["total"] == job["done"] == 4 and job["langs"] == ["hi", "ta"]
    blocks = [b for p in api.get(f"/api/documents/{doc_id}").json()["pages"] for b in p["blocks"]]
    assert {b["id"] for b in blocks if b["translations"]} == set(picked)
    assert all(set(b["translations"]) == {"hi", "ta"} for b in blocks if b["id"] in picked)
    assert api.post(f"/api/documents/{doc_id}/translate", json={"langs": []}).status_code == 400


def test_remove_a_language(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    picked = ["p0-b1", "p0-b3"]
    body = {"langs": ["hi", "ta"], "block_ids": picked}
    wait_for(api, api.post(f"/api/documents/{doc_id}/translate", json=body).json()["id"])
    assert api.delete(f"/api/documents/{doc_id}/translations/hi").json() == {"removed": 2}
    blocks = [b for p in api.get(f"/api/documents/{doc_id}").json()["pages"] for b in p["blocks"]]
    assert all(set(b["translations"]) == {"ta"} for b in blocks if b["id"] in picked)
    assert api.get("/api/documents").json()[0]["languages"] == ["ta"]
    assert api.delete(f"/api/documents/{doc_id}/translations/bho").status_code == 400


def test_deleting_a_document_forgets_its_cached_answers(api):
    cache = api.app.state.services.bodhan.cache
    doc_id, other = upload(api, "sample_en.pdf")["id"], upload(api, "sample_hi.pdf")["id"]
    for d, lang in ((doc_id, "ta"), (other, "bn")):
        wait_for(api, api.post(f"/api/documents/{d}/translate", json={"langs": [lang]}).json()["id"])
    listed = lambda d: {cache.root / rel for rel in cache._index(d).read_text().split()}  # noqa: E731
    mine, theirs = listed(doc_id), listed(other)
    assert mine and theirs and all(p.exists() for p in mine | theirs)  # the structure review's and Bodhan's answers
    api.delete(f"/api/documents/{doc_id}")
    assert not any(p.exists() for p in mine) and not cache._index(doc_id).exists()
    assert all(p.exists() for p in theirs - mine)  # another document's answers stay


def test_translate_highlighted_text(api):
    r = api.post("/api/translate-text", json={"text": "The library opens at nine.", "langs": ["hi", "ta"]})
    assert r.status_code == 200
    by_lang = {x["lang"]: x for x in r.json()}
    assert any("\u0b80" <= ch <= "\u0bff" for ch in by_lang["ta"]["text"]) and not by_lang["hi"]["cached"]
    again = api.post("/api/translate-text", json={"text": "The library opens at nine.", "langs": ["hi"]}).json()
    assert again[0]["cached"] and again[0]["text"] == by_lang["hi"]["text"]
    assert api.post("/api/translate-text", json={"text": "  ", "langs": ["hi"]}).status_code == 400
    assert api.post("/api/translate-text", json={"text": "a" * 20_001, "langs": ["hi"]}).status_code == 413
    assert api.post("/api/translate-text", json={"text": "hi", "langs": ["bho"]}).status_code == 400


def test_romanise_translated_text(api):
    r = api.post("/api/transliterate-text", json={"text": "नमस्ते दुनिया", "lang": "hi"}).json()
    assert r["text"] and not any("\u0900" <= ch <= "\u097f" for ch in r["text"])  # no Devanagari left
    assert api.post("/api/transliterate-text", json={"text": "hello", "lang": "en"}).status_code == 400
    assert api.post("/api/transliterate-text", json={"text": " ", "lang": "hi"}).status_code == 400


def test_text_in_figures_only_when_asked():
    blocks = [
        Block(id="a", order=0, label="Paragraph", type="Text", bbox=[0, 0, 1, 1], text="Body", source="text_layer"),
        Block(
            id="b",
            order=1,
            label="Paragraph",
            type="Text",
            bbox=[0, 0, 1, 1],
            text="Label",
            source="text_layer",
            in_figure=True,
        ),
    ]
    doc = Document(
        id="x",
        filename="x.pdf",
        created="",
        pages=[
            Page(
                index=0,
                width=1,
                height=1,
                source="text_layer",
                dpi=150,
                image="",
                background="",
                text_quality=1.0,
                blocks=blocks,
            )
        ],
    )
    assert [b.id for _, b in blocks_to_translate(doc, "hi")] == ["a"]
    assert [b.id for _, b in blocks_to_translate(doc, "hi", include_figures=True)] == ["a", "b"]


def maths_block(text, *formulas):
    return Block(
        id="m",
        order=0,
        label="Paragraph",
        type="Text",
        bbox=[0, 0, 100, 20],
        text=text,
        source="text_layer",
        maths=[Maths(text=f, bbox=[0, 0, 5, 5], descent=1, image=f"maths/{n}.png") for n, f in enumerate(formulas)],
    )


def test_formulas_become_placeholders_and_come_back():
    block = maths_block("the model d maps 𝑥(𝑡) to 𝑦 with d layers", "d", "𝑥(𝑡)", "𝑦")
    sent, formulas = protect(block.text, block.maths)
    assert sent == "the model ⟦1⟧ maps ⟦2⟧ to ⟦3⟧ with ⟦4⟧ layers"  # "d" not matched inside "model"
    assert restore("⟦2⟧ ⟦1⟧ ⟦3⟧ ⟦ 4 ⟧", formulas) == "𝑥(𝑡) d 𝑦 d"  # order may change; spacing inside is tolerated
    assert restore("⟦1⟧ ⟦2⟧ ⟦3⟧", formulas) is None and restore("⟦1⟧ ⟦1⟧ ⟦2⟧ ⟦3⟧ ⟦4⟧", formulas) is None
    assert restore("⟦১⟧ ⟦২⟧ ⟦৩⟧ ⟦৪⟧", formulas) == "d 𝑥(𝑡) 𝑦 d"  # Bengali writes the numbers in its own digits


class LosesPlaceholders(FakeBodhan):
    async def translate(self, text, lang, script=None):
        self.sent.append(text)
        return TextResult(text=text.replace("⟦1⟧", "").upper(), truncated=False)


@pytest.mark.anyio
async def test_lost_placeholder_falls_back_to_the_words_between_formulas():
    block = maths_block("the state ℎ(𝑡) grows.", "ℎ(𝑡)")
    fake = FakeBodhan()
    assert (await translate_block(block, "hi", fake)).text == "THE STATE ℎ(𝑡) GROWS."
    assert fake.sent == ["the state ⟦1⟧ grows."]
    lossy = LosesPlaceholders()
    assert (await translate_block(block, "hi", lossy)).text == "THE STATE ℎ(𝑡) GROWS."
    assert lossy.sent == ["the state ⟦1⟧ grows.", "the state", "grows."]


@pytest.mark.anyio
async def test_citation_markers_come_back_after_their_sentence():
    block = maths_block("Changes in precipitation,[¹] but slowly. Heavy rains.[²][³] Then ℎ(𝑡) grows.", "ℎ(𝑡)")
    fake = FakeBodhan()
    assert (
        await translate_block(block, "hi", fake)
    ).text == "CHANGES IN PRECIPITATION, BUT SLOWLY.[¹] HEAVY RAINS.[²][³] THEN ℎ(𝑡) GROWS."
    assert fake.sent == ["Changes in precipitation, but slowly. Heavy rains. Then ⟦1⟧ grows."]  # markers never sent


@pytest.mark.anyio
async def test_markers_in_table_cells_keep_their_numbers():
    assert await translate_text("Porbandar[¹][²]", "hi", FakeBodhan()) == ("PORBANDAR[¹][²]", False)


class TagKeepingBodhan(FakeBodhan):
    """Upper-cases the words and keeps the tags, as live Bodhan mostly does."""

    async def translate(self, text, lang, script=None):
        self.sent.append(text)
        return TextResult(
            text=re.sub(r"(^|>)([^<]*)", lambda m: m.group(1) + m.group(2).upper(), text), truncated=False
        )


@pytest.mark.anyio
async def test_styled_runs_travel_as_tags():
    block = Block(
        id="b",
        order=0,
        label="Paragraph",
        type="Text",
        bbox=[0, 0, 1, 1],
        source="text_layer",
        text="A monsoon is a wind.",
        rich='A <b>monsoon</b> is a <span style="color:#236192">wind</span>.',
    )
    t = await translate_block(block, "hi", TagKeepingBodhan())
    assert (
        t.rich == 'A <b>MONSOON</b> IS A <span style="color:#236192">WIND</span>.' and t.text == "A MONSOON IS A WIND."
    )
    t = await translate_block(block, "hi", FakeBodhan())  # tags mangled (<B>): the words stay, the runs go
    assert t.rich is None and t.text == "A MONSOON IS A WIND."
    assert (
        runs_intact("<i>a <b>b</b></i>")
        and not runs_intact("<b>a</i>")
        and not runs_intact("<b>a")
        and not runs_intact("a</>")
    )


@pytest.mark.anyio
async def test_text_already_in_the_target_language_is_kept():
    quote = "I shall finish this letter with a description of the two wonderful mausoleums of Agra."
    assert already_in(quote, "en") and not already_in(quote, "hi")
    assert not already_in(
        "El monzón es un viento que cambia con las estaciones y que trae las lluvias de la "
        "temporada a la región, pero no es el único de los vientos del año.",
        "en",
    )
    assert already_in("ताजमहल भारत के आगरा शहर में स्थित है और यह एक मकबरा है।", "hi")
    fake = FakeBodhan()
    assert await translate_text(quote, "en", fake) == (quote, False) and fake.sent == []
    assert units(quote, "en") == [] and units(quote, "hi") == [quote]


@pytest.mark.anyio
async def test_english_from_a_caseless_script_is_tidied():
    assert english_case("the Taj Mahal", heading=True) == "Taj Mahal"
    assert english_case("The introduction", heading=True) == "Introduction"
    assert english_case("the great hall of the people", heading=True) == "The great hall of the people"  # not short
    assert english_case("located in Uttar Pradesh, India") == "Located in Uttar Pradesh, India"
    assert english_case("<b>monsoon</b> rains") == "<b>Monsoon</b> rains"
    assert english_case("http://whc.unesco.org") == "http://whc.unesco.org"
    assert english_case("iPhone sales") == "iPhone sales" and english_case("km²") == "km²"

    class Lower(FakeBodhan):
        async def translate(self, text, lang, script=None):
            return TextResult(text="the garden", truncated=False)

    heading = Block(
        id="b", order=0, label="Section-title", type="Text", bbox=[0, 0, 1, 1], source="text_layer", text="বাগান"
    )
    assert (await translate_block(heading, "en", Lower())).text == "Garden"
    assert (await translate_block(heading, "hi", Lower())).text == "the garden"  # only English is tidied
    english = Block(
        id="e",
        order=0,
        label="Section-title",
        type="Text",
        bbox=[0, 0, 1, 1],
        source="text_layer",
        text="the origin of species, by means of natural selection",
    )
    assert (await translate_block(english, "en", Lower())).text == english.text  # already English: untouched


@pytest.mark.anyio
async def test_short_headings_are_revised_with_the_section_they_introduce():
    class Reviewer:
        default_model = "fake"

        def __init__(self, reply):
            self.reply, self.asked = reply, []

        async def chat(self, messages, model=None, use_cache=True):
            self.asked.append(messages[-1]["content"])
            return ChatResult(text=self.reply, finish_reason="stop")

    def page_of(heading_t):
        heading = Block(
            id="h", order=0, label="Section-title", type="Text", bbox=[0, 0, 1, 1], source="text_layer", text="প্রভাব"
        )
        body = Block(
            id="p",
            order=1,
            label="Paragraph",
            type="Text",
            bbox=[0, 2, 1, 3],
            source="text_layer",
            text="তাজমহল তৈরি হয়েছে বিভিন্ন ঐতিহ্যবাহী নকশার উপর",
        )
        page = Page(
            index=0,
            width=600,
            height=800,
            source="text_layer",
            dpi=150,
            image="a.png",
            background="b.png",
            text_quality=1.0,
            blocks=[heading, body],
        )
        return page, {"h": heading_t, "p": Translation(text="The Taj Mahal was built on many traditional designs")}

    page, results = page_of(Translation(text="Effect of"))
    reviewer = Reviewer("Influence")
    await refine_headings(page, results, "en", reviewer)
    t = results["h"]
    assert t.text == "Influence" and t.status == "edited" and t.edits[0].before == "Effect of"
    assert "তাজমহল তৈরি" in reviewer.asked[0] and len(reviewer.asked) == 1  # the paragraph is left alone
    page, results = page_of(Translation(text="Effect of"))
    await refine_headings(
        page, results, "en", Reviewer("Sure! Here is the heading you asked for, translated: Influence")
    )
    assert results["h"].text == "Effect of" and results["h"].status == "done" and not results["h"].edits
    page, results = page_of(Translation(text="Albert Gu∗¹"))
    await refine_headings(page, results, "en", Reviewer("Albert Gu"))  # a footnote marker lost: undone
    assert results["h"].text == "Albert Gu∗¹" and not results["h"].edits


def test_powers_stay_where_they_are():
    text = "In GF(2⁸), the polynomial x⁶+x⁵+x+1 covers 5 km² of the field.¹ See [²][³]"
    plain, marks = strip_markers(text)
    assert plain == "In GF(2⁸), the polynomial x⁶+x⁵+x+1 covers 5 km² of the field. See "
    assert [m for _, m in marks] == ["¹", "[²][³]"]
    assert strip_markers("Gandhi¹ was born.")[0] == "Gandhi was born."  # a word's footnote still moves
    assert strip_markers("the polynomial ⟦1⟧⁶+⟦2⟧⁵+⟦3⟧+1.")[1] == []  # powers of formulas sent as placeholders
    assert strip_markers("by the polynomial <i>x</i>⁶+ <i>x</i>⁵.")[1] == []  # and of styled runs
    assert strip_markers("element as −<i>x</i> ⁴+ <i>x</i> ², and")[1] == []  # set apart from its variable (FIPS)
    assert strip_markers("found in textbooks ¹ such as")[1] == [(0, "¹")]  # a gap after a word: still a footnote
    plain, marks = strip_markers("²https://github.com/facebookresearch/xformers")  # a footnote's own number
    assert attach_markers(plain, marks) == "²https://github.com/facebookresearch/xformers"
