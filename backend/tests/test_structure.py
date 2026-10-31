import json
import tempfile
from pathlib import Path

import pymupdf
import pytest

from backend.clients.openrouter import ChatResult
from backend.core.models import Block, Translation
from backend.core.store import DocumentStore
from backend.pipeline.ingest import ingest_pdf
from backend.pipeline.render import wrap_html
from backend.pipeline.structure import apply, link_next_pages, page_lines, parse, review_page
from backend.pipeline.translate.run import translate_pair

from .conftest import ROOT
from .test_translate import FakeBodhan


def ingested(name):
    store = DocumentStore(Path(tempfile.mkdtemp()))
    doc = ingest_pdf((ROOT / "documents" / name).read_bytes(), name, store)
    return doc, store


def number_of(page, needle):
    blocks = sorted(page.blocks, key=lambda b: b.order)
    return next(n for n, b in enumerate(blocks, 1) if needle in b.text)


def test_parse_keeps_only_checked_fixes():
    fixes = parse(
        'Sure: {"lines": [2, 99], "split": [{"block": 1, "starts": ["As far", ""]}], "merge": [[3]], '
        '"label": {"4": "Section-title", "5": "Banner"}, "continues": [[1, 2], [1]], "next_page": [3]}',
        5,
    )
    assert fixes == {
        "lines": [2],
        "split": [{"block": 1, "starts": ["As far"]}],
        "merge": [],
        "label": {4: "Section-title"},
        "continues": [[1, 2]],
        "next_page": [3],
    }
    assert parse("no json here", 5)["lines"] == []


def test_split_at_missed_paragraph_breaks():
    doc, store = ingested("en_book_darwin-origin-of-species-ch1.pdf")
    page = doc.pages[1]
    n = number_of(page, "As far as I am able")
    with pymupdf.open(store.dir(doc.id) / "source.pdf") as pdf:
        lines = page_lines(pdf[1])
    done = apply(
        page,
        parse(
            json.dumps({"split": [{"block": n, "starts": ["As far as I am able", "Indefinite variability"]}]}),
            len(page.blocks),
        ),
        lines,
    )
    parts = [b for b in page.blocks if b.id.startswith(done["split"][0] + "s")]
    assert (
        len(parts) == 3 and parts[1].text.startswith("As far as I am able") and parts[2].text.startswith("Indefinite")
    )
    assert parts[0].text.startswith(
        "domesticated animals are still capable of rapid improvement"
    )  # hyphenated line kept
    assert [b.order for b in page.blocks] == list(range(len(page.blocks)))


def test_form_lines_become_one_block_each():
    doc, store = ingested("en_form_irs-1040-2025.pdf")
    page = doc.pages[0]
    n = number_of(page, "Total amount from Form(s) W-2")
    with pymupdf.open(store.dir(doc.id) / "source.pdf") as pdf:
        lines = page_lines(pdf[0])
    before = len(page.blocks)
    apply(page, parse(json.dumps({"lines": [n]}), before), lines)
    pieces = [b for b in page.blocks if "s" in b.id.split("-b")[1]]
    assert len(pieces) >= 10 and pieces[0].text.startswith("Total amount from Form(s) W-2")
    assert all(p.bbox[3] - p.bbox[1] < 15 for p in pieces)  # one line each


@pytest.mark.anyio
async def test_review_page_and_continuations():
    doc, store = ingested("en_paper_llama-two-column.pdf")
    page = doc.pages[0]
    a, b = number_of(page, "cheaper to train a large model"), number_of(page, "performance, a smaller one")

    class Reviewer:
        async def chat(self, messages, model=None, max_tokens=None, temperature=None):
            assert messages[0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
            return ChatResult(
                text=json.dumps({"continues": [[a, b]], "next_page": [b]}),
                finish_reason="stop",
                usage={"cost": 0.02},
            )

    first = sorted(page.blocks, key=lambda x: x.order)
    first[a - 1].translations["hi"] = Translation(text="पुराना")
    done = await review_page(doc, 0, store, Reviewer())
    assert first[a - 1].translations == {}  # translated again, with its continuation
    assert done["continues"] == [[first[a - 1].id, first[b - 1].id]] and page.review["cost_usd"] == 0.02
    link_next_pages(doc)
    assert first[b - 1].continues == next(
        c.id for c in sorted(doc.pages[1].blocks, key=lambda c: c.order) if c.label in ("Paragraph", "List")
    )


@pytest.mark.anyio
async def test_a_split_sentence_is_translated_whole():
    def block(i, text):
        return Block(id=i, order=0, label="Paragraph", type="Text", bbox=[0, 0, 1, 1], source="text_layer", text=text)

    fake = FakeBodhan()
    head, tail = await translate_pair(
        block("a", "Curiosity's landing site was fol-"), block("b", "lowed by thirty others."), "hi", fake
    )
    assert fake.sent == ["Curiosity's landing site was followed by thirty others."]
    assert (head.text, tail.text) == ("CURIOSITY'S LANDING SITE WAS FOLLOWED", "BY THIRTY OTHERS.")  # cut in proportion


def test_upload_reviews_structure_before_the_first_translation(api):
    from .conftest import upload
    from .test_translate import wait_for

    summary = upload(api, "sample_en.pdf")
    [review] = [j for j in api.app.state.services.jobs.jobs.values() if j.doc_id == summary["id"]]
    assert review.kind == "structure" and review.total in (0, 2)  # the mock answers at once: it may be done
    job = api.post(f"/api/documents/{summary['id']}/translate", json={"langs": ["hi"]}).json()  # not refused
    assert wait_for(api, job["id"])["status"] == "done" and review.status == "done" and review.done == 2
    doc = api.get(f"/api/documents/{summary['id']}").json()
    assert all(p["review"] is not None for p in doc["pages"])  # the mock's reply has no fixes, but each page was asked
    assert (
        upload(api, "sample_en.pdf")["id"] == summary["id"]
        and api.get(f"/api/documents/{summary['id']}/job").json() is None
    )


@pytest.mark.anyio
async def test_a_translation_waits_for_the_running_review():
    import asyncio

    from backend.core.jobs import JobManager

    jobs, order = JobManager(), []

    async def review(job):
        await asyncio.sleep(0.05)
        order.append("review")

    jobs.start("structure", "d", [], review)
    await jobs.wait("d", "structure")
    order.append("translate")
    assert order == ["review", "translate"] and jobs.running_for("d") == []


@pytest.mark.anyio
async def test_a_split_sentence_keeps_its_styled_runs():
    from .test_translate import TagKeepingBodhan

    a = Block(
        id="a",
        order=0,
        label="Paragraph",
        type="Text",
        bbox=[0, 0, 1, 1],
        source="text_layer",
        text="the objective of Hoffmann et al. is to reach a certain level of",
        rich='the objective of <span style="color:#000080">Hoffmann et al.</span> is to reach a certain level of',
    )
    b = Block(
        id="b",
        order=1,
        label="Paragraph",
        type="Text",
        bbox=[0, 2, 1, 3],
        source="text_layer",
        text="performance, a smaller one trained longer.",
    )
    head, tail = await translate_pair(a, b, "hi", TagKeepingBodhan())
    assert (
        head.rich
        == 'THE OBJECTIVE OF <span style="color:#000080">HOFFMANN ET AL.</span> IS TO REACH A CERTAIN LEVEL OF'
    )
    assert tail.text == "PERFORMANCE, A SMALLER ONE TRAINED LONGER." and tail.rich is None


def test_merges_only_join_blocks_directly_above_one_another():
    from backend.core.models import Style
    from backend.pipeline.structure import stacked

    def block(y0, y1):
        return Block(
            id=f"b{y0}",
            order=0,
            label="Paragraph",
            type="Text",
            bbox=[50, y0, 300, y1],
            source="text_layer",
            text="x",
            style=Style(font_size=10),
        )

    assert stacked([block(100, 124), block(127, 140)])  # a line split off a paragraph
    assert not stacked([block(100, 124), block(160, 200)])  # an equation between them


def test_a_merged_paragraph_keeps_wrapping_around_its_photo():
    doc, store = ingested("hi_wikipedia_mahatma-gandhi.pdf")
    page = doc.pages[1]  # "कम आयु में विवाह": four short lines beside a photo, then full width, split at ingest
    beside, below = number_of(page, "मई १८८३"), number_of(page, "अपने माता पिता")
    with pymupdf.open(store.dir(doc.id) / "source.pdf") as pdf:
        lines = page_lines(pdf[1])
    room = sorted(page.blocks, key=lambda b: b.order)[below - 1].room
    done = apply(page, parse(json.dumps({"merge": [[beside, below]]}), len(page.blocks)), lines)
    merged = next(b for b in page.blocks if b.id == done["merge"][0][0] + "s0")
    floats = wrap_html(merged, merged.bbox, page)  # the photo is one of the page's obstacles
    assert "ds-wrap-right" in floats and "ds-wrap-left" not in floats
    assert merged.room == room
