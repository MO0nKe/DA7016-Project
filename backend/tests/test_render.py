import time

import pymupdf
import pytest

from backend.core.models import Block, Cell, Maths, Page, Style, Translation
from backend.pipeline.render import (
    cell_boxes,
    cell_css,
    clean_table_html,
    layout_box,
    render_block,
    rich_html,
    text_html,
    wrap_html,
)

from .conftest import INPUTS, upload


def translate(api, doc_id, lang):
    job = api.post(f"/api/documents/{doc_id}/translate", json={"langs": [lang]}).json()
    for _ in range(200):
        if api.get(f"/api/jobs/{job['id']}").json()["status"] != "running":
            return
        time.sleep(0.02)


def test_page_fragment_marks_translated_and_untranslated_blocks(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    before = api.get(f"/api/documents/{doc_id}/pages/0/render", params={"lang": "hi"}).text
    assert 'data-status="untranslated"' in before and 'data-status="translated"' not in before
    # Nothing in Hindi yet: the page is the original, its sections invisible text over their own pixels.
    assert "original.png" in before and "background.png" not in before and before.count("ds-drawn") > 5
    translate(api, doc_id, "hi")
    after = api.get(f"/api/documents/{doc_id}/pages/0/render", params={"lang": "hi"}).text
    assert 'data-status="translated"' in after and 'lang="hi"' in after
    assert "--patch:url('/api/documents/" in after and "background.png') calc(" in after  # each covers its own patch
    assert after.count('class="ds-cell') == 20  # table cells placed one by one


def test_block_fragment_and_preview(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    block = api.get(f"/api/documents/{doc_id}/blocks/p0-b1/render").text
    assert block.startswith('<div class="ds-block') and "District Education Survey 2025" in block
    assert api.get(f"/api/documents/{doc_id}/blocks/nope/render").status_code == 404
    preview = api.get(f"/api/documents/{doc_id}/preview").text
    assert preview.count('class="ds-page"') == 2 and "dsFit" in preview
    assert api.get("/api/static/fit.js").status_code == 200


def test_rtl_translation_sets_direction(api):
    doc_id = upload(api, "sample_hi.pdf")["id"]
    translate(api, doc_id, "ur")
    assert 'dir="rtl"' in api.get(f"/api/documents/{doc_id}/pages/0/render", params={"lang": "ur"}).text


def test_table_html_is_sanitised():
    raw = '<table onclick="x()"><tr><td colspan="2" style="a">A<script>bad()</script></td></tr></table>'
    assert clean_table_html(raw) == '<table><tr><td colspan="2">Abad()</td></tr></table>'


@pytest.mark.slow
@pytest.mark.anyio
async def test_rendered_page_keeps_the_layout(tmp_path):
    """Re-render the source text over the text-free background (as the Translation view does) and print
    it: it should read back as the same text in the same places as the original."""
    from backend.core.store import DocumentStore
    from backend.pipeline.export import export_pdf
    from backend.pipeline.ingest import ingest_pdf

    store = DocumentStore(tmp_path)
    source = (INPUTS / "sample_en.pdf").read_bytes()
    path, _ = await export_pdf(ingest_pdf(source, "sample_en.pdf", store), None, store)
    out = pymupdf.open(path)
    assert out.page_count == 2
    words = {w[4] for w in out[0].get_text("words")}
    assert {"District", "Northfield", "Attendance", "Figure"} <= words
    title_orig = pymupdf.open(stream=source, filetype="pdf")[0].search_for("Key findings")[0]
    title_new = out[0].search_for("Key findings")[0]
    assert abs(title_orig.y0 - title_new.y0) < 4 and abs(title_orig.x0 - title_new.x0) < 4


def test_embedded_fonts_are_reused(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    doc = api.get(f"/api/documents/{doc_id}").json()
    assert doc["fonts"], "Chrome-made PDFs embed TrueType subsets that map their own text"
    name, rel = next(iter(doc["fonts"].items()))
    font = api.get(f"/api/documents/{doc_id}/{rel}")
    assert font.status_code == 200 and len(font.content) > 1000
    assert api.get(f"/api/documents/{doc_id}/fonts/nope.ttf").status_code == 404
    page = api.get(f"/api/documents/{doc_id}/pages/0/render").text
    assert "@font-face" in page and "font-family:'pdf-" in page and "var(--ds-" in page
    translate(api, doc_id, "hi")  # translated text gets the Noto stack (render.css), not the subset font
    translated = api.get(f"/api/documents/{doc_id}/pages/0/render", params={"lang": "hi"}).text
    assert not any("font-family:'pdf-" in div for div in translated.split("<div") if 'data-status="translated"' in div)


def test_inline_formulas_are_drawn_from_their_crops(api):
    block = Block(
        id="b",
        order=0,
        label="Paragraph",
        type="Text",
        bbox=[0, 0, 200, 20],
        text="maps 𝑥(𝑡) to 𝑦",
        source="text_layer",
        style=Style(font_size=10),
        maths=[Maths(text="𝑥(𝑡)", bbox=[30, 0, 50, 12], descent=3, image="maths/p0-b0-0.png")],
        translations={"hi": Translation(text="𝑥(𝑡) को मैप करता है")},
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
        blocks=[block],
    )
    html = render_block(block, page, "hi", asset=lambda rel: f"/api/documents/d/{rel}")
    assert '<img class="ds-maths" src="/api/documents/d/maths/p0-b0-0.png" alt="𝑥(𝑡)"' in html
    assert "width:2.000em;height:1.200em;vertical-align:-0.300em" in html and "को मैप करता है" in html
    assert api.get("/api/documents/nope/maths/p0-b0-0.png").status_code == 404


def test_untranslated_table_cells_keep_the_original_font():
    cells = [
        Cell(row=0, col=0, bbox=[0, 0, 50, 10], text="Gold certificates"),
        Cell(row=0, col=1, bbox=[50, 0, 90, 10], text="11,037"),
    ]
    block = Block(
        id="t",
        order=0,
        label="Table",
        type="Table",
        bbox=[0, 0, 90, 10],
        text="",
        cells=cells,
        source="text_layer",
        style=Style(font_size=8, family="sans"),
        translations={"hi": Translation(cells=["स्वर्ण प्रमाण पत्र", "11,037"])},
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
        blocks=[block],
    )
    word, number = render_block(block, page, "hi").split('<div class="ds-cell')[1:]
    assert "font-family" not in word and "font-family:var(--ds-sans-stack)" in number


def test_a_translation_that_says_the_same_keeps_the_original_pixels():
    block = Block(
        id="h",
        order=0,
        label="Page-header",
        type="Text",
        bbox=[0, 0, 90, 10],
        text="FIPS 197",
        source="text_layer",
        style=Style(font_size=8),
        translations={"ml": Translation(text="FIPS 197")},
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
        blocks=[block],
    )
    over_original = render_block(block, page, "ml", crop="bg.png")
    assert 'data-status="untranslated"' in over_original and "ds-drawn" in over_original
    assert 'data-status="translated"' in render_block(block, page, "ml")  # an export draws it on the text-free page
    block.translations["ml"] = Translation(text="FIPS 197", status="edited")
    assert 'data-status="translated"' in render_block(block, page, "ml", crop="bg.png")  # someone chose this text


def test_infobox_cells_grow_into_their_row_and_column():
    cells = [
        Cell(row=0, col=0, bbox=[310, 410, 330, 420], text="Birth", header=True),
        Cell(row=0, col=1, bbox=[400, 410, 460, 432], text="2 October 1869"),
        Cell(row=1, col=0, bbox=[310, 445, 328, 455], text="Death", header=True),
        Cell(row=1, col=1, bbox=[400, 445, 470, 455], text="30 January 1948"),
    ]
    block = Block(
        id="t",
        order=0,
        label="Table",
        type="Table",
        bbox=[310, 410, 545, 470],
        text="",
        cells=cells,
        source="text_layer",
        style=Style(font_size=8),
    )
    assert cell_boxes(block) == [[310, 410, 398, 444], [400, 410, 543, 444], [310, 445, 398, 469], [400, 445, 543, 469]]
    page = Page(
        index=0,
        width=600,
        height=800,
        source="text_layer",
        dpi=150,
        image="a.png",
        background="b.png",
        text_quality=1.0,
        blocks=[block],
    )
    html = render_block(block, page, None)
    assert html.count("ds-top") == 4 and 'data-group="t:c0"' in html and 'data-group="t:c1"' in html


def test_citation_markers_are_one_raised_run():
    assert (
        text_html("Porbandar[¹][²] & 5 km²")
        == 'Porbandar<sup class="ds-ref">[1][2]</sup> &amp; 5 km<sup class="ds-ref">2</sup>'
    )
    assert 'style="color:#3366cc"' in text_html("rains.[³]", "#3366cc")


def test_cells_and_runs_keep_their_own_style():
    block = Block(
        id="t",
        order=0,
        label="Table",
        type="Table",
        bbox=[0, 0, 90, 10],
        text="",
        source="text_layer",
        style=Style(font_size=8, bold=True),
    )
    assets = Cell(row=0, col=0, bbox=[0, 0, 50, 10], text="ASSETS", style=Style(bold=True, color="#236192"))
    coin = Cell(row=1, col=0, bbox=[0, 0, 50, 10], text="Coin", style=Style())
    assert cell_css(assets, block) == ";font-weight:700;font-style:normal;color:#236192"
    assert cell_css(coin, block) == ";font-weight:400;font-style:normal"  # not bold, though the table mostly is
    assert rich_html("<b>Gold</b> <script>x</script>[¹]", block, None) == '<b>Gold</b> x<sup class="ds-ref">[1]</sup>'


def test_cells_stop_at_a_row_that_overlaps_them_a_little():
    cells = [
        Cell(row=0, col=0, bbox=[61, 570, 347, 581], text="Consolidated variable interest entities formed"),
        Cell(row=1, col=0, bbox=[70, 579.8, 307, 590.7], text="Total Reserve Bank capital"),
        Cell(row=2, col=0, bbox=[84, 590.2, 153, 601.2], text="Total liabilities and capital"),
    ]
    block = Block(
        id="t",
        order=0,
        label="Table",
        type="Table",
        bbox=[61, 570, 557, 601.2],
        text="",
        cells=cells,
        source="text_layer",
        style=Style(font_size=8),
    )
    assert [box[3] for box in cell_boxes(block)] == [581, 590.7, 601.2]  # not grown past the next row's top


def test_a_centred_cell_alone_in_its_row_spans_the_table():
    cells = [
        Cell(row=0, col=0, bbox=[361, 453, 393, 466], text="Location"),
        Cell(row=0, col=2, bbox=[437, 453, 490, 467], text="Agra, India"),
        Cell(row=1, col=0, bbox=[392, 628, 517, 641], text="UNESCO World Heritage Site"),
        Cell(row=2, col=0, bbox=[370, 651, 380, 664], text="Type"),
    ]  # alone, but not centred: keeps its indent
    block = Block(
        id="t",
        order=0,
        label="Table",
        type="Table",
        bbox=[361, 453, 546, 680],
        text="",
        cells=cells,
        source="text_layer",
        style=Style(font_size=10.5),
    )
    boxes = cell_boxes(block)
    assert boxes[2][0] == 361 and boxes[2][2] == 544 and boxes[3][0] == 370
    page = Page(
        index=0,
        width=600,
        height=800,
        source="text_layer",
        dpi=150,
        image="a.png",
        background="b.png",
        text_quality=1.0,
        blocks=[block],
    )
    assert render_block(block, page, None).count("text-align:center") == 1


def test_renderer_assets_are_revalidated(api):
    assert api.get("/api/static/render.css").headers["cache-control"] == "no-cache"


def test_text_keeps_clear_of_pictures():
    def block(bbox, label="Paragraph", size=10):
        return Block(id="b", order=0, label=label, type="Text", bbox=bbox, text="x", source="text_layer",
                     style=Style(font_size=size))  # fmt: skip

    def page(blocks, obstacles):
        return Page(index=0, width=600, height=800, source="text_layer", dpi=150, image="a.png", background="b.png",
                    text_quality=1.0, blocks=blocks, obstacles=obstacles)  # fmt: skip

    # A one-line heading widens to the right margin, but stops at a picture on its line (NIST slides p2).
    heading = block([60, 100, 200, 112], "Section-title")
    assert layout_box(heading, page([heading], []), 60)[0][2] == 538
    assert layout_box(heading, page([heading], [[400, 90, 550, 300]]), 60)[0][2] == 398
    assert layout_box(heading, page([heading], [[0, 0, 600, 130]]), 60)[0][2] == 538  # a banner it sits on
    # An indented list item near the middle isn't a centred line.
    item = block([117, 397, 518, 416], "List", 16)
    assert layout_box(item, page([item, block([52, 25, 587, 74])], []), 52)[1] is None
    # A centred title wider than the body's margins keeps its whole box (Mamba: the English showed at both ends).
    title = block([76, 108, 558, 129], "Title", 17)
    body = block([72, 300, 540, 400])
    assert layout_box(title, page([title, body], []), 72) == ([76, 108, 558, 129], "center")
    # A paragraph wraps around a photo on its left and one on its right, each from where it starts.
    para = block([42, 559, 359, 764])
    floats = wrap_html(para, para.bbox, page([para], [[44.5, 559.6, 135.1, 678.6], [300, 700, 380, 760]]))
    assert floats.count("ds-wrap-left") == 1 and "width:96.10pt;height:122.60pt" in floats  # from the top: no spacer
    assert floats.count("ds-wrap-right") == 2 and "width:0;height:138.00pt" in floats  # empty above, then the photo
    assert wrap_html(para, para.bbox, page([para], [[0, 500, 600, 800]])) == ""  # a panel it sits on
