import pymupdf
from PIL import Image, ImageDraw

from backend.core.models import Block, Style
from backend.pipeline.ingest.blocks import raw_blocks, text_box
from backend.pipeline.ingest.maths import is_maths, maths_runs
from backend.pipeline.ingest.raster import room_below, underlines
from backend.pipeline.ingest.regions import drawn_areas, region_label, split_by_regions
from backend.pipeline.ingest.style import rich_text
from backend.pipeline.ingest.tables import grid_blocks
from backend.pipeline.ingest.text import collapse_repeated_marks, join_lines, text_quality, visual_lines

from .conftest import INPUTS, ROOT, png, upload


def blocks_by_label(doc, page=0):
    out = {}
    for b in doc["pages"][page]["blocks"]:
        out.setdefault(b["label"], []).append(b)
    return out


def test_english_sample_structure(api):
    summary = upload(api, "sample_en.pdf")
    assert summary["page_count"] == 2 and summary["pending_ocr"] == [] and summary["source_lang"] == "en"
    doc = api.get(f"/api/documents/{summary['id']}").json()
    p0, p1 = blocks_by_label(doc, 0), blocks_by_label(doc, 1)
    assert p0["Title"][0]["text"] == "District Education Survey 2025"
    assert [b["text"] for b in p0["Section-title"]] == ["1. Key findings", "2. Attendance across the year"]
    assert p0["Header"][0]["text"].startswith("District Education Survey 2025")
    assert p0["Page-number"][0]["translatable"] is False
    assert p0["Footnote"][0]["text"].startswith("1 The survey")
    assert p0["Image-caption"][0]["text"].startswith("Figure 1")
    assert len(p1["List"]) == 3
    table = p0["Table"][0]
    assert len(table["cells"]) == 20 and table["cells"][4]["text"] == "Northfield"
    # The paragraph Chrome split around the superscript is one block again, with the marker kept.
    intro = next(b for b in p0["Paragraph"] if b["text"].startswith("This report"))
    assert intro["text"].endswith("materials.¹")
    # The callout's yellow fill is sampled for covering scanned text.
    note = next(b for b in p0["Paragraph"] if b["text"].startswith("Note for"))
    assert note["style"]["background"].startswith("#fe")


def test_hindi_sample_is_clean(api):
    doc = api.get(f"/api/documents/{upload(api, 'sample_hi.pdf')['id']}").json()
    labels = blocks_by_label(doc)
    assert labels["Title"][0]["text"] == "ग्रामीण स्वास्थ्य सेवाएँ"
    assert labels["Header"][0]["text"].startswith("ज़िला")
    assert doc["pages"][0]["text_quality"] == 1.0
    assert doc["source_lang"] == "hi"  # detected from the script, so Hindi is greyed out as a target


def test_upload_is_deduplicated_and_listed(api):
    a, b = upload(api, "sample_en.pdf"), upload(api, "sample_en.pdf")
    assert a["id"] == b["id"]
    assert [d["id"] for d in api.get("/api/documents").json()] == [a["id"]]


def test_page_images_and_source(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    original = api.get(f"/api/documents/{doc_id}/pages/0/original.png")
    background = api.get(f"/api/documents/{doc_id}/pages/0/background.png")
    assert original.headers["content-type"] == "image/png"
    assert original.content != background.content
    assert api.get(f"/api/documents/{doc_id}/source.pdf").content.startswith(b"%PDF")
    assert api.get(f"/api/documents/{doc_id}/pages/9/original.png").status_code == 404


def test_scanned_page_waits_for_ocr_then_ocr_fills_it(api, tmp_path):
    # A "scan": one page that is only an image.
    src = pymupdf.open(INPUTS / "sample_en.pdf")
    pix = src[0].get_pixmap(dpi=100)
    scan = pymupdf.open()
    page = scan.new_page(width=src[0].rect.width, height=src[0].rect.height)
    page.insert_image(page.rect, pixmap=pix)
    path = tmp_path / "scan.pdf"
    scan.save(path)
    r = api.post("/api/documents", files={"file": ("scan.pdf", path.read_bytes(), "application/pdf")})
    summary = r.json()
    assert summary["pending_ocr"] == [0]
    doc = api.post(f"/api/documents/{summary['id']}/ocr", json={"pages": [0]}).json()
    page = doc["pages"][0]
    assert page["source"] == "ocr" and page["blocks"]
    assert page["background"] == page["image"]
    table = next(b for b in page["blocks"] if b["label"] == "Table")
    assert table["html"].startswith("<table>") and "Rice" in table["text"]
    assert all(0 <= b["bbox"][2] <= page["width"] + 1 for b in page["blocks"])


def test_rejects_non_pdf(api):
    r = api.post("/api/documents", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 400


def test_text_quality_and_mark_cleanup():
    assert text_quality("A perfectly normal sentence with enough characters.") == 1.0
    assert text_quality(" broken private use glyphs everywhere ") < 0.97
    assert text_quality("ि" + "क ि" * 20) < 0.97
    assert collapse_repeated_marks("ग्राामीण") == "ग्रामीण"


def test_outline_from_headings_and_from_bookmarks(api, tmp_path):
    doc_id = upload(api, "sample_en.pdf")["id"]
    items = api.get(f"/api/documents/{doc_id}/outline").json()
    assert [(i["level"], i["title"], i["page"]) for i in items[:3]] == [
        (1, "District Education Survey 2025", 0),
        (2, "1. Key findings", 0),
        (2, "2. Attendance across the year", 0),
    ]
    assert items[-1]["page"] == 1 and items[0]["block_id"] == "p0-b1"

    pdf = pymupdf.open(INPUTS / "sample_en.pdf")
    pdf.set_toc([[1, "Findings", 1], [2, "Materials", 2]])
    path = tmp_path / "bookmarked.pdf"
    pdf.save(path)
    r = api.post("/api/documents", files={"file": ("b.pdf", path.read_bytes(), "application/pdf")})
    items = api.get(f"/api/documents/{r.json()['id']}/outline").json()
    assert [(i["level"], i["title"], i["page"], i["block_id"]) for i in items] == [
        (1, "Findings", 0, None),
        (2, "Materials", 1, None),
    ]


def test_font_family_from_name():
    from backend.pipeline.ingest.style import family_of

    cases = {
        "NimbusRomNo9L-Regu": "serif",
        "TimesNewRomanPSMT": "serif",
        "LinLibertineT": "serif",
        "HelveticaNeueLTStd-Roman": "sans",
        "FranklinGothicLTPro-BkCm": "sans",
        "NotoSansDevanagari-Bold": "sans",
        "Noto-Serif": "serif",
        "ABCDEF+Calibri-Bold": "sans",
        "Roboto-Mono": "mono",
        "NimbusMonL-Regu": "mono",
        "CMR10": "serif",
    }
    assert {f: family_of(f) for f in cases} == cases


def test_rotated_and_maths_text_stay_in_background():
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 100), "Plain prose stays editable.", fontsize=11)
    page.insert_text((30, 500), "arXiv:0000.00000v1", fontsize=11, rotate=90)
    blocks, keep = raw_blocks(page)
    assert [b["text"] for b in blocks] == ["Plain prose stays editable."] and len(keep) == 1
    line = lambda *spans: {"spans": [{"font": f, "text": t} for f, t in spans]}  # noqa: E731
    assert is_maths([line(("ABCDEF+CMMI10", "x"), ("CMR10", "="), ("CMMI10", "y")), line(("CMR10", "(1)"))])
    assert is_maths([line(("LibertineMathMI", "Ah"), ("LinLibertineT", "+"))])
    assert not is_maths([line(("LinLibertineT", "where the pair "), ("LibertineMathMI", "fA"))])
    assert not is_maths([line(("Symbol", "•"), ("Calibri", "a list item"))])


def test_text_box_fits_one_line_box_per_baseline():
    lines = [{"spans": [{"size": 10, "origin": (72, 100)}]}, {"spans": [{"size": 10, "origin": (72, 112)}]}]
    # A glyph box far shorter than the type (as Libertine reports) still gets two 12 pt line boxes.
    x0, y0, x1, y1 = text_box([72, 96, 300, 113], lines, 10, 1.2)
    assert (x0, x1) == (72, 300) and round(y1 - y0, 2) == 24 and round(y0, 2) == 100 - 6 - 3.4


def test_outline_skips_front_matter_and_nests_numbered_sections(tmp_path):
    from backend.core.models import Block, Document, Page, Style
    from backend.pipeline.outline import outline

    def heading(n, text, label="Section-title", font="Bold"):
        return Block(
            id=f"b{n}",
            order=n,
            label=label,
            type="SectionHeader",
            bbox=[0, n * 20, 100, n * 20 + 12],
            text=text,
            style=Style(font=font),
            source="text_layer",
        )

    blocks = [
        heading(0, "A Paper", "Title", "Big"),
        heading(1, "Ann Author, Bo Author, Cy Author"),
        heading(2, "Abstract"),
        heading(3, "1 Introduction"),
        heading(4, "Figure Title", font="Sans"),
        heading(5, "Status of This Memo"),
        heading(6, "5.1.2 ShiftRows"),
    ]
    doc = Document(
        id="x",
        filename="x.pdf",
        created="",
        pages=[
            Page(
                index=0,
                width=600,
                height=800,
                source="text_layer",
                dpi=150,
                image="",
                background="",
                text_quality=1.0,
                blocks=blocks,
            )
        ],
    )
    path = tmp_path / "x.pdf"
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.save(path)  # no bookmarks: the outline comes from the heading blocks
    assert [(i["level"], i["title"]) for i in outline(doc, path)] == [
        (1, "A Paper"),
        (2, "Abstract"),
        (2, "1 Introduction"),
        (2, "Status of This Memo"),
        (4, "5.1.2 ShiftRows"),
    ]


def test_type1_and_unmapped_truetype_fonts_are_reused(tmp_path):
    from pathlib import Path

    from backend.pipeline.ingest.fonts import extract_fonts
    from backend.pipeline.ingest.webfonts import drawn_glyphs

    docs = Path(__file__).resolve().parents[2] / "documents"
    fonts = extract_fonts(pymupdf.open(docs / "en_paper_mamba-equations.pdf"), tmp_path)  # LaTeX Type1
    libertine = pymupdf.Font(fontfile=str(tmp_path / fonts["LinLibertineT"]))
    assert fonts["LinLibertineT"].endswith(".otf") and all(libertine.has_glyph(ord(c)) for c in "Mamba,1")
    fonts = extract_fonts(pymupdf.open(docs / "en_financial_federal-reserve-2023.pdf"), tmp_path)  # no cmap
    assert "FranklinGothicLTPro-BkCm" in fonts
    # A glyph traced for two characters is a ligature: neither letter may be mapped to it.
    assert drawn_glyphs([(102, 7), (105, 7), (102, 3), (97, 4)]) == {102: 3, 97: 4}


def test_text_inside_a_drawn_figure_is_marked(tmp_path):
    from pathlib import Path

    from backend.core.store import DocumentStore
    from backend.pipeline.ingest import ingest_pdf

    docs = Path(__file__).resolve().parents[2] / "documents"
    doc = ingest_pdf((docs / "en_paper_mamba-equations.pdf").read_bytes(), "m.pdf", DocumentStore(tmp_path))
    figure = {b.text for b in doc.pages[1].blocks if b.in_figure}
    assert {"Project", "Selection Mechanism", "GPU HBM"} <= figure
    assert not any(b.text.startswith(("Figure 1", "Discretization")) for b in doc.pages[1].blocks if b.in_figure)


def test_text_over_a_full_page_picture_is_not_a_scan(tmp_path):
    """Slides draw real text over a full-page picture: that text is removed from the background like any
    other. A scan's text is part of its picture (at most an invisible OCR layer): the background keeps it."""
    from backend.core.store import DocumentStore
    from backend.pipeline.ingest import ingest_pdf
    from backend.pipeline.ingest.raster import scan_like

    def page_with(render_mode):
        pdf = pymupdf.open()
        page = pdf.new_page()
        picture = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 80), False)
        picture.set_rect(picture.irect, (20, 40, 120))
        page.insert_image(page.rect, pixmap=picture)
        page.insert_text(
            (72, 100), "A slide title over the picture", fontsize=24, render_mode=render_mode, color=(1, 1, 1)
        )
        return pdf

    slide, scan = page_with(0), page_with(3)
    assert not scan_like(slide[0]) and scan_like(scan[0])
    store = DocumentStore(tmp_path)
    doc = ingest_pdf(slide.tobytes(), "slide.pdf", store)
    page = doc.pages[0]
    assert page.background != page.image and page.blocks  # a text-free background to draw over


def test_reading_order_reads_columns_then_sidebar():
    from backend.pipeline.ingest.blocks import reading_order

    box = lambda n, *bbox: {"n": n, "bbox": list(bbox)}  # noqa: E731
    # Two columns under a title whose paragraph gaps line up, then a full-width note.
    paper = [
        box("title", 50, 10, 550, 30),
        box("L1", 50, 40, 290, 100),
        box("R1", 310, 40, 550, 100),
        box("L2", 50, 110, 290, 200),
        box("R2", 310, 110, 550, 200),
        box("note", 50, 210, 550, 240),
    ]
    assert [b["n"] for b in reading_order(paper)] == ["title", "L1", "L2", "R1", "R2", "note"]
    # A Wikipedia infobox stored first in the PDF comes after the article beside it.
    wiki = [
        box("infobox", 360, 140, 518, 780),
        box("title", 42, 88, 113, 114),
        box("lead", 42, 128, 346, 160),
        box("heading", 42, 410, 100, 429),
        box("section", 42, 440, 346, 500),
    ]
    assert [b["n"] for b in reading_order(wiki)] == ["title", "lead", "heading", "section", "infobox"]


def test_text_cleanup():
    from backend.pipeline.ingest.blocks import inside_line
    from backend.pipeline.ingest.ocr import ocr_text
    from backend.pipeline.ingest.text import join_lines, span_text

    line = lambda text: {"spans": [{"text": text, "flags": 0}]}  # noqa: E731
    assert join_lines([line("rapid improve-"), line("ment of income . . . . . . 9")]) == "rapid improvement of income 9"
    assert join_lines([line("Amount from line 11a .")]) == "Amount from line 11a"  # a form's lone leader dot
    assert (
        ocr_text("SPEEDS $$^1$$ at angle $\\theta$ and drag $C_D$ con-\nstant")
        == "SPEEDS ¹ at angle θ and drag CD constant"
    )
    # A broken Unicode map read the fi ligature as "f" (FIPS 197); "of" is no word in WordNet but stays.
    assert span_text({"text": "a fnite feld of coeffcients", "flags": 0}) == "a finite field of coefficients"
    assert span_text({"text": "0", "flags": 1, "font": "ABCDEF+CMSY10"}) == "′"  # TeX's prime, not a raised zero
    # The tall brackets of "GF(2⁸)" are pieces of their prose line, not a display line kept as pixels.
    prose = {"bbox": [77.0, 597.0, 537.6, 610.1]}
    assert inside_line({"bbox": [290.3, 585.2, 315.2, 605.0]}, prose)
    assert not inside_line({"bbox": [290.3, 612.0, 315.2, 640.0]}, prose)  # an equation under it


def piece(x0, y0, x1, y1, text, size=8):
    span = {
        "text": text,
        "size": size,
        "flags": 0,
        "font": "Helvetica",
        "color": 0,
        "bbox": (x0, y0, x1, y1),
        "origin": (x0, y1 - 2),
    }
    return {
        "kind": "text",
        "bbox": [x0, y0, x1, y1],
        "text": text,
        "style": Style(font_size=size),
        "list": False,
        "fixed": True,
        "lines": [{"spans": [span], "bbox": (x0, y0, x1, y1)}],
    }


def test_aligned_grid_becomes_a_table_and_a_form_does_not():
    from backend.pipeline.ingest.tables import grid_blocks

    statement = [
        piece(60, 70, 300, 80, "Statement of condition"),
        piece(450, 85, 470, 95, "2023"),
        piece(520, 85, 540, 95, "2022"),
    ]
    for y, label in ((100, "Gold certificates"), (110, "Coin"), (120, "Other loans")):
        statement += [
            piece(60, y, 140, y + 9, label),
            piece(445, y, 470, y + 9, "1,423"),
            piece(515, y, 540, y + 9, "1,209"),
        ]
    statement += [
        piece(60, 130, 200, 139, "Treasury securities (of which"),
        piece(70, 140, 120, 149, "respectively)"),
        piece(445, 140, 470, 149, "4,988"),
        piece(515, 140, 540, 149, "5,729"),
    ]
    title, table = grid_blocks(statement)
    assert title["text"] == "Statement of condition" and table["kind"] == "table"
    rows = {}
    for c in table["cells"]:
        rows.setdefault(c.row, {})[c.col] = c.text
    assert rows[0] == {1: "2023", 2: "2022"} and rows[1] == {0: "Gold certificates", 1: "1,423", 2: "1,209"}
    assert rows[4] == {0: "Treasury securities (of which respectively)", 1: "4,988", 2: "5,729"}
    # A form's wrapped label is joined; a numbered field below it stays apart.
    form = [
        piece(36, 300, 60, 308, "If more"),
        piece(36, 308, 70, 316, "than four"),
        piece(36, 316, 80, 324, "(2) Last name"),
    ]
    assert [p["text"] for p in grid_blocks(form)] == ["If more than four", "(2) Last name"]


def test_running_heads_and_form_tops():
    from backend.pipeline.ingest.labels import label_for

    def label(text, bbox, size=10, busy=()):
        b = {"kind": "text", "text": text, "bbox": bbox, "style": Style(font_size=size), "list": False}
        return label_for(b, 1, 800, 10, 20, set(), set(), busy=busy)

    assert label("6 VARIATION UNDER DOMESTICATION.", [33, 25, 239, 38]) == "Header"
    assert label("Davis, et al. Standards Track Page 1", [56, 724, 539, 735]) == "Footer"
    assert label("Mars Science Laboratory/Curiosity 2 NASA Facts", [46, 761, 566, 772]) == "Footer"
    assert label("Chapter 3 Methods", [46, 20, 300, 40]) != "Header"
    assert label("1040 U.S. Individual Income Tax Return", [43, 32, 284, 47], size=12, busy={"top"}) != "Header"
    assert label("2025", [298, 24, 350, 48], size=20, busy={"top"}) != "Page-number"


def test_display_equation_lines():
    from backend.pipeline.ingest.maths import maths_line

    line = lambda *spans: {"spans": [{"font": f, "text": t, "flags": fl} for f, t, fl in spans]}  # noqa: E731
    italic = 2
    assert maths_line(
        line(
            ("Times", "(", 0),
            ("Times-Italic", "x", italic),
            ("CMR10", "+", 0),
            ("Times-Italic", "x", italic),
            ("Times", "+ 1) =", 0),
            ("Times-Italic", "x", italic),
        )
    )
    assert not maths_line(line(("Times", "same finite field element as ", 0), ("Times-Italic", "x", italic)))


def test_labels_beside_values_become_a_table():
    from backend.pipeline.ingest.tables import label_value_tables

    def block(*lines):  # (x0, top, text) per line
        parts = [piece(x, y, x + 60, y + 10, text) for x, y, text in lines]
        return {
            **parts[0],
            "fixed": False,
            "lines": [p["lines"][0] for p in parts],
            "bbox": [min(x for x, _, _ in lines), lines[0][1], 500, lines[-1][1] + 10],
        }

    infobox = [
        block((309, 400, "जन्म"), (384, 400, "2 अक्टूबर 1869")),
        block((384, 415, "पोरबन्दर")),
        block((309, 435, "मौत"), (384, 435, "30 जनवरी 1948")),
        block((309, 455, "जाति"), (390, 455, "गुजराती")),
    ]
    [table] = label_value_tables(infobox)
    rows = {}
    for c in table["cells"]:
        rows.setdefault(c.row, []).append(c.text)
    assert rows == {0: ["जन्म", "2 अक्टूबर 1869 पोरबन्दर"], 1: ["मौत", "30 जनवरी 1948"], 2: ["जाति", "गुजराती"]}
    # Prose broken into fragments (an OCR text layer) has no common value edge.
    fragments = [
        block((50, 100, "equation"), (110, 100, "(2), which describes")),
        block((50, 115, "altitude,"), (160, 115, "the constants should")),
        block((50, 130, "for which"), (125, 130, "the deceleration is")),
    ]
    assert all(b["kind"] == "text" for b in label_value_tables(fragments))


def test_room_below_stops_at_blocks_and_drawings():
    def block(bbox):
        return Block(
            id="b", order=0, label="Paragraph", type="Text", bbox=bbox, source="text_layer", style=Style(font_size=10)
        )

    bg = Image.new("RGB", (600, 800), "white")  # 1 px per pt
    ImageDraw.Draw(bg).rectangle((50, 300, 250, 400), fill="black")  # a picture under the left column
    left, right, below_right = block([50, 100, 250, 200]), block([300, 100, 500, 200]), block([300, 260, 500, 280])
    blocks = [left, right, below_right]
    assert room_below(left, blocks, bg, 1, 800) == 95  # down to the picture at 300, less half a line
    assert room_below(right, blocks, bg, 1, 800) == 55  # down to the next block at 260
    assert room_below(below_right, blocks, bg, 1, 800) == 479  # down to the bottom margin (800 - 36)


def test_link_underlines_are_found_but_rules_and_maths_bars_are_not():
    pdf = pymupdf.open()
    page = pdf.new_page(width=400, height=300)
    page.insert_text((50, 100), "a linked word", fontsize=10)
    page.draw_rect(pymupdf.Rect(50, 101.5, 108, 102.2), fill=(0, 0, 1), color=None)  # its underline
    page.insert_text((50, 150), "a table cell", fontsize=10)
    page.draw_rect(pymupdf.Rect(40, 151.5, 200, 152.2), fill=(0, 0, 0), color=None)  # a rule wider than the text
    page.insert_text((50, 200), "x over y", fontsize=10)
    page.draw_rect(pymupdf.Rect(50, 201.5, 80, 202.2), fill=(0, 0, 0), color=None)  # a bar beside kept maths
    found = underlines(page, keep=[[48, 190, 90, 215]])
    assert [round(r.y0, 1) for r in found] == [101.5]
    page.insert_text((250, 100), "a form label", fontsize=10)
    page.draw_line((250, 102), (300, 102))  # a row border under the label, in two touching pieces
    page.draw_line((300, 102), (390, 102))
    assert [round(r.y0, 1) for r in underlines(page, keep=[[48, 190, 90, 215]])] == [101.5]


def test_inline_maths_runs():
    def span(text, x0, font="Times-Roman", size=10, y=100):
        return {
            "text": text,
            "font": font,
            "size": size,
            "flags": 0,
            "origin": (x0, y),
            "bbox": (x0, y - 0.8 * size, x0 + 5 * len(text), y + 0.2 * size),
        }

    line = {
        "spans": [
            span("the state ", 0),
            span("h", 50, "CMMI10"),
            span("(", 55),
            span("t", 60, "CMMI10"),
            span(")", 65),
            span(" ", 70),
            span("∈", 75, "CMSY10"),
            span("R", 80, "MSBM10"),
            span("N", 85, "CMMI7", 7, 96),
            span(" grows 10", 90),
            span("×", 135),
            span(" faster.", 140),
        ]
    }
    runs = maths_runs([line])
    assert [r[0] for r in runs] == ["h(t) ∈RN"]  # brackets, the space and the superscript join; a lone × doesn't
    text, box, descent = runs[0]
    assert box[0] == 50 and box[2] == 90 and descent == 2  # down to the bottom of the box, below the baseline


def test_a_stacked_fraction_is_one_formula_and_the_text_after_it_is_not_raised():
    """LLaMA p2: "a dimension of ⅔4d instead of 4d", TeX's 2 over 3 in CMR8. PyMuPDF flags everything after the
    lowered 3 as superscript."""

    def span(text, x0, x1, font, size, base, flags=0):
        return {"text": text, "font": font, "size": size, "flags": flags, "origin": (x0, base),
                "bbox": (x0, base - 0.75 * size, x1, base + 0.25 * size)}  # fmt: skip

    numerator = {"spans": [span("2", 72.1, 76.3, "CMR8", 8, 554.7)], "bbox": (72.1, 549.2, 76.3, 556.2)}
    text = {
        "spans": [
            span("3", 72.1, 76.3, "CMR8", 8, 562.8),
            span("4", 77.5, 82.9, "CMR10", 10.9, 559, 1),
            span("d", 82.9, 88.6, "CMMI10", 10.9, 559, 1),
            span(" instead of", 88.6, 134.1, "Times", 10.9, 559, 1),
            span(" 4", 134.1, 142.3, "CMR10", 10.9, 559, 1),
            span("d", 142.3, 147.9, "CMMI10", 10.9, 559, 1),
            span(" as in PaLM.", 147.9, 203.5, "Times", 10.9, 559, 1),
        ],
        "bbox": (72.1, 551.4, 203.5, 564.3),
    }
    lines = visual_lines([numerator, text])
    assert join_lines(lines) == "2⁄3 4d instead of 4d as in PaLM."
    assert [r[0] for r in maths_runs(lines)] == ["2⁄3 4d", "d"]
    assert maths_runs(lines)[0][1][1] == numerator["spans"][0]["bbox"][1]  # the crop starts at the numerator
    # A footnote's marker starts its line, so PyMuPDF doesn't flag it; it is small and raised all the same.
    marker = {
        "spans": [span("2", 318.8, 322, "Times", 6, 767.2), span("https://github.com", 322, 487, "Times", 9, 771)]
    }
    assert join_lines(visual_lines([{**marker, "bbox": (318.8, 763.2, 487.4, 773)}])) == "²https://github.com"
    # Two lines of small text, one under the other, aren't a fraction: no text baseline between them.
    small = {"spans": [span("12", 72, 80, "Times", 8, 570)], "bbox": (72, 564, 80, 572)}
    assert (
        len(visual_lines([small, {"spans": [span("34 notes", 72, 110, "Times", 8, 578)], "bbox": (72, 572, 110, 580)}]))
        == 2
    )


def test_layout_regions_split_glued_blocks_and_refine_labels():
    def line(text, y, size=10):
        return {
            "bbox": (50, y, 300, y + size),
            "spans": [
                {
                    "text": text,
                    "font": "Times-Bold" if size > 10 else "Times",
                    "size": size,
                    "flags": 0,
                    "color": 0,
                    "origin": (50, y + 0.8 * size),
                    "bbox": (50, y, 300, y + size),
                }
            ],
        }

    glued = {
        "kind": "text",
        "bbox": [50, 100, 300, 150],
        "text": "Results We find that the model works well.",
        "style": Style(),
        "list": False,
        "lines": [line("Results", 100, 12), line("We find that the model", 120), line("works well.", 132)],
    }
    regions = [([48, 98, 302, 113], "section-header"), ([48, 118, 302, 145], "text")]
    heading, body = split_by_regions([glued], regions)
    assert (heading["text"], heading["region"]) == ("Results", "section-header")
    assert (body["text"], body["region"]) == ("We find that the model works well.", "text")
    assert region_label(heading, "Paragraph") == "Section-title" and region_label(body, "Paragraph") == "Paragraph"
    assert region_label(heading, "Header") == "Header"  # our running-head and table labels win
    assert split_by_regions([glued], []) == [glued]  # no model: nothing changes


def test_underlines_side_by_side_are_found():
    pdf = pymupdf.open()
    page = pdf.new_page(width=400, height=300)
    page.insert_text((50, 100), "rains.[2][3]", fontsize=10)
    page.draw_rect(pymupdf.Rect(78, 101.5, 88, 102.2), fill=(0, 0, 1), color=None)  # [2]
    page.draw_rect(pymupdf.Rect(88, 101.5, 98, 102.2), fill=(0, 0, 1), color=None)  # [3], touching it
    assert len(underlines(page, keep=[])) == 2


def test_runs_styled_apart_are_tagged():
    def span(text, flags=0, color=0, font="Helvetica"):
        return {"text": text, "flags": flags, "color": color, "font": font, "size": 10}

    lines = [
        {"spans": [span("A "), span("monsoon", 16), span(" is a "), span("seasonal", 2), span(" wind,", 2)]},
        {
            "spans": [
                span("see "),
                span("Table 1", color=0x2222EE),
                span("."),
                span("2", 1),
                span(" x", 2, font="CMMI10"),
            ]
        },
    ]
    text = join_lines(lines)
    assert (
        rich_text(lines, Style(color="#000000"), text)
        == 'A <b>monsoon</b> is a <i>seasonal wind,</i> see <span style="color:#2222ee">Table 1</span>.² x'
    )
    plain = [{"spans": [span("Nothing "), span("styled", 2)]}]
    assert rich_text(plain, Style(color="#000000", italic=True), join_lines(plain)) is None


def test_a_label_with_an_open_bracket_continues_on_the_next_row():
    def piece(text, x0, y0, x1, y1):
        span = {"text": text, "flags": 0, "color": 0, "font": "Helvetica", "size": 8, "bbox": [x0, y0, x1, y1]}
        return {"bbox": [x0, y0, x1, y1], "text": text, "style": Style(font_size=8), "lines": [{"spans": [span]}]}

    items = [
        piece("Coin", 61, 137, 74, 148),
        piece("1,423", 470, 137, 495, 148),
        piece("Assets held, net (including $1,006 measured as of", 61, 282, 346, 290),
        piece("Note 6", 385, 284, 404, 295),
        piece("December 31, 2023, respectively)", 70, 289, 184, 300),
        piece("16,098", 474, 289, 495, 300),
        piece("Other assets", 61, 349, 94, 360),
        piece("1,352", 470, 349, 495, 360),
    ]
    [table] = grid_blocks(items)
    rows = {}
    for c in table["cells"]:
        rows.setdefault(c.row, []).append(c.text)
    assert rows[1] == [
        "Assets held, net (including $1,006 measured as of December 31, 2023, respectively)",
        "Note 6",
        "16,098",
    ]
    assert len(rows) == 3


def test_drawn_areas_are_pictures_and_line_art_not_rules():
    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=800)
    page.insert_image(pymupdf.Rect(400, 100, 550, 250), stream=png(60, 60))
    for k in range(12):  # a little chart
        page.draw_line((60 + 10 * k, 500), (70 + 10 * k, 450 - 3 * k))
    page.draw_line((40, 300), (560, 300))  # a rule under a heading
    page.draw_rect(pymupdf.Rect(0, 0, 600, 800), color=(0.9, 0.9, 0.9))  # a page frame
    areas = drawn_areas(page)
    assert [400.0, 100.0, 550.0, 250.0] in areas and any(a[0] <= 60 and a[2] >= 170 and a[1] <= 420 for a in areas)
    assert not any(a[1] >= 299 and a[3] <= 301 for a in areas) and not any(a[2] - a[0] > 590 for a in areas)


def test_infobox_rows_ruled_only_between_groups_are_split_into_pairs():
    page = pymupdf.open(ROOT / "documents" / "bn_wikipedia_taj-mahal.pdf")[0]
    [table] = [b for b in raw_blocks(page)[0] if b["kind"] == "table"]
    rows = {}
    for c in table["cells"]:
        if c.text:
            rows.setdefault(c.row, []).append(c.text)
    texts = list(rows.values())
    assert ["অবস্থান", "আগ্রা, ভারত"] in texts and ["স্থানাঙ্ক", "২৭°১০′৩০″ উত্তর ৭৮°০২′৩১″ পূর্ব"] in texts
    assert ["ইউনেস কো বিশ্ব ঐতিহ্যবাহী স্থান"] in texts and ["ধরন", "সাংস্কৃতিক"] in texts  # the heading row
