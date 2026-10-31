from backend.core.languages import in_script_ratio
from backend.core.models import Block, Document, Page, Translation
from backend.pipeline.evaluate import coverage_metrics, fit_metrics, iou, size_spread, structure_metrics


def block(id, bbox, label="Paragraph", text="Some text here", **kw):
    return Block(id=id, order=0, label=label, type="Text", bbox=bbox, text=text, source="text_layer", **kw)


def doc(*blocks):
    page = Page(
        index=0,
        width=600,
        height=800,
        source="text_layer",
        dpi=150,
        image="a.png",
        background="b.png",
        text_quality=1.0,
        blocks=list(blocks),
    )
    return Document(id="d", filename="x.pdf", created="", pages=[page])


def test_iou():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0
    assert round(iou([0, 0, 10, 10], [5, 0, 15, 10]), 3) == 0.333


def test_structure_metrics_match_moved_and_missing_blocks():
    original = doc(block("a", [0, 0, 100, 20], "Title", "Hello"), block("b", [0, 50, 100, 70]))
    rebuilt = doc(block("x", [1, 0, 100, 20], "Title", "Hello"))
    m = structure_metrics(original, rebuilt, compare_text=True)
    assert m["original_blocks"] == 2 and m["matched_at_iou_0.5"] == 0.5
    assert m["label_agreement"] == 1.0 and m["text_similarity"] == 1.0


def test_coverage_and_script_check():
    d = doc(
        block("a", [0, 0, 1, 1], translations={"hi": Translation(text="नमस्ते दुनिया")}),
        block("b", [0, 0, 1, 1], translations={"hi": Translation(text="hello world", status="truncated")}),
        block("c", [0, 0, 1, 1]),
    )
    m = coverage_metrics(d, "hi")
    assert (m["done"], m["truncated"], m["missing"]) == (1, 1, 1)
    assert m["blocks_mostly_wrong_script"] == 1 and m["mean_in_script_ratio"] == 0.5
    assert in_script_ratio("கூட்டம்", "ta") == 1.0 and in_script_ratio("123", "ta") is None


def test_fit_metrics():
    report = [
        {"status": "translated", "scale": 1.0, "fill": 0.6, "overflow": False},
        {"status": "translated", "scale": 0.7, "fill": 1.0, "overflow": True},
        {"status": "source", "scale": 1.0, "overflow": False},
    ]
    assert fit_metrics(report) == {
        "blocks": 2,
        "median_scale": 1.0,
        "shrunk_below_0.8": 0.5,
        "overflowing": 1,
        "underfilled": 1,
    }


def test_size_spread_compares_blocks_that_started_alike():
    a, b, c = (block(i, [0, 0, 1, 1]) for i in "abc")
    for x, size in ((a, 10), (b, 10), (c, 12)):
        x.style.font_size = size
    report = [
        {"id": "a", "status": "translated", "scale": 1.0},
        {"id": "b", "status": "translated", "scale": 0.5},
        {"id": "c", "status": "translated", "scale": 0.6},
    ]
    assert size_spread(doc(a, b, c), report) == {"size_spread": 2.0, "uneven_groups": 1}
