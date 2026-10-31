"""Reconstruction check: re-render each PDF's own text over its text-free background, read the
result back, and save the original and the re-render side by side to look at. Free (no APIs).

    uv run scripts/check_render.py                       # every PDF in documents/
    uv run scripts/check_render.py documents/en_paper_mamba-equations.pdf --page 2
    uv run scripts/check_render.py --lang hi             # fake translations (the mock's, ~1.3x longer)
    uv run scripts/check_render.py --lang hi --live --estimate   # live Bodhan calls a run would make
    uv run scripts/check_render.py --lang hi --live      # real Bodhan (OCR on scans) + OpenRouter headings
    uv run scripts/check_render.py --lang hi --live --structure   # + the vision structure review first

Writes data/check/<name>-p<page>.png and prints the structure and fit metrics per document (an
unchanged source text should need no shrinking). With --lang it fills every translatable block with
the mock's fake text in that language's script, and also prints how unevenly alike blocks were sized
and how many font families each translated block was drawn in (read back from the printed PDF).
With --live it translates for real instead (cached, paced to the rate limit; spends a little), OCRs
pages without a text layer, and writes every page to data/check/live/.
"""

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from types import SimpleNamespace  # noqa: E402

from backend.clients import make_clients  # noqa: E402
from backend.core.config import load_settings  # noqa: E402
from backend.core.models import Translation  # noqa: E402
from backend.core.store import DocumentStore  # noqa: E402
from backend.pipeline.evaluate import fit_metrics, size_spread, structure_metrics  # noqa: E402
from backend.pipeline.export import export_pdf  # noqa: E402
from backend.pipeline.ingest import ingest_pdf, ocr_page  # noqa: E402
from backend.pipeline.markup import runs_intact, untagged  # noqa: E402
from backend.pipeline.structure import link_next_pages, review_page  # noqa: E402
from backend.pipeline.translate import estimate, translate_document  # noqa: E402
from backend.pipeline.translate.units import finish, prepare  # noqa: E402
from mock_server.synthetic import pseudo_text  # noqa: E402


def page_image(pdf_bytes, index, dpi=100):
    """Page `index` of the PDF (the last page if past the end) as an image."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
        pix = pdf[min(index, len(pdf) - 1)].get_pixmap(dpi=dpi, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def fake_translate(doc, lang):
    """Fake text the way translate.py sends it: formulas as placeholders and markers left out, put back afterwards."""
    for p in doc.pages:
        for b in p.blocks:
            if b.translatable and not b.in_figure:
                sent, formulas, marks = prepare(b)
                out = finish(pseudo_text(sent, lang), formulas, marks) or pseudo_text(b.text, lang)
                b.translations[lang] = Translation(
                    text=untagged(out),
                    rich=out if b.rich and runs_intact(out) else None,
                    cells=[pseudo_text(c.text, lang) for c in b.cells] if b.cells else None,
                )


def fonts_per_block(pdf_bytes, doc, report):
    """Distinct font families (subset prefix and style dropped: Bold and Regular are one) drawing each
    translated block, from the printed PDF."""
    translated = {r["id"] for r in report if r["status"] == "translated"}
    counts = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
        for p in doc.pages:
            for b in (b for b in p.blocks if b.id in translated):
                spans = [
                    s
                    for blk in pdf[p.index].get_text("dict", clip=pymupdf.Rect(b.bbox))["blocks"]
                    for line in blk.get("lines", [])
                    for s in line["spans"]
                    if s["text"].strip()
                ]
                counts.append(len({s["font"].split("+")[-1].split("-")[0] for s in spans}))
    return {
        "mean_families": round(sum(counts) / max(1, len(counts)), 2),
        "blocks_3plus_families": sum(c >= 3 for c in counts),
    }


async def live_translate(doc, lang, store, clients, structure=False):
    """Translate for real: OCR the pages without a text layer, optionally review their structure, then the
    translate job's own path."""
    bodhan, openrouter = clients
    fixes = cost = 0
    for p in doc.pages:
        if p.source == "pending_ocr":
            await ocr_page(doc, p.index, store, bodhan)
        elif structure:
            done = await review_page(doc, p.index, store, openrouter) or {}
            fixes += sum(len(v) for v in done.values())
            cost += p.review["cost_usd"] if p.review else 0
    link_next_pages(doc)
    store.save(doc)
    await translate_document(
        store, doc.id, lang, bodhan, SimpleNamespace(total=0, done=0, failed=0), openrouter=openrouter
    )
    doc = store.load(doc.id)
    ts = [b.translations[lang] for p in doc.pages for b in p.blocks if lang in b.translations]
    return doc, {
        "errors": sum(t.status == "error" for t in ts),
        "truncated": sum(t.status == "truncated" for t in ts),
        "headings_revised": sum(t.status == "edited" for t in ts),
        **({"structure_fixes": fixes, "structure_usd": round(cost, 3)} if structure else {}),
    }


async def check(path, page, store, scratch, out_dir, lang=None, clients=None, only_estimate=False, structure=False):
    """Ingest one PDF, translate it (fake, or live with `clients`), export it and save side-by-side images; its
    structure and fit metrics, or only the cost with `only_estimate`."""
    original = path.read_bytes()
    doc = ingest_pdf(original, path.name, store)
    if clients and only_estimate:
        e = estimate(doc, lang, clients[0])
        ocr = sum(p.source == "pending_ocr" for p in doc.pages)
        return {"calls": e["calls"], "uncached": e["calls"] - e["cached_calls"], "ocr_pages": ocr}
    if all(p.source == "pending_ocr" for p in doc.pages) and not clients:
        return {"skipped": "needs OCR"}
    live = {}
    if clients:
        doc, live = await live_translate(doc, lang, store, clients, structure)
    elif lang:
        fake_translate(doc, lang)
    exported, report = await export_pdf(doc, lang, store)
    rebuilt = ingest_pdf(exported.read_bytes(), "rebuilt.pdf", scratch)
    for n in range(len(doc.pages)) if clients else [page]:
        a, b = page_image(original, n), page_image(exported.read_bytes(), n)
        side = Image.new("RGB", (a.width + b.width + 10, max(a.height, b.height)), "#888")
        side.paste(a, (0, 0))
        side.paste(b, (a.width + 10, 0))
        side.save(out_dir / f"{path.stem}{'-' + lang if lang else ''}{'-s' if structure else ''}-p{n + 1}.png")
    shrunk = sorted((r["scale"], r["id"]) for r in report if r["scale"] < 0.9)
    extra = {**size_spread(doc, report), **fonts_per_block(exported.read_bytes(), doc, report)} if lang else {}
    return {
        **live,
        **structure_metrics(doc, rebuilt, compare_text=not lang),
        **fit_metrics(report),
        **extra,
        "most_shrunk": [f"{i}:{s}" for s, i in shrunk[:3]],
        "underfilled_at": [
            f"{r['id']}:{r['scale']}:{r['fill']:.2f}"
            for r in report
            if r["status"] == "translated" and r.get("fill", 1) < 0.8
        ][:6],
    }


async def main(args):
    """Check every PDF given (default: documents/) and print one line of metrics each."""
    pdfs = [Path(p) for p in args.pdfs] or sorted((ROOT / "documents").glob("*.pdf"))
    out_dir = ROOT / "data" / "check" / ("live" if args.live else "")
    out_dir.mkdir(parents=True, exist_ok=True)
    clients = None
    if args.live:
        if not args.lang:
            raise SystemExit("--live needs --lang")
        os.environ.setdefault("BODHAN_BASE_URL", "https://api.bodhan.ai")
        os.environ.setdefault("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        clients = make_clients(load_settings())
    try:
        with tempfile.TemporaryDirectory() as tmp:  # fresh ingest every run, so pipeline changes show
            store, scratch = DocumentStore(Path(tmp) / "a"), DocumentStore(Path(tmp) / "b")
            for path in pdfs:
                m = await check(
                    path, args.page - 1, store, scratch, out_dir, args.lang, clients, args.estimate, args.structure
                )
                print(f"{path.stem:50} " + "  ".join(f"{k}={v}" for k, v in m.items()), flush=True)
    finally:
        for c in clients or ():
            await c.aclose()
    if not args.estimate:
        print(f"side-by-side images in {out_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdfs", nargs="*")
    parser.add_argument("--page", type=int, default=1, help="1-based page to compare (default 1)")
    parser.add_argument("--lang", help="draw fake translations in this language (e.g. hi, ta, bn)")
    parser.add_argument("--live", action="store_true", help="translate with the real APIs instead of fake text")
    parser.add_argument("--estimate", action="store_true", help="with --live: only count the calls")
    parser.add_argument(
        "--structure",
        action="store_true",
        help="with --live: review each page's blocks with a vision model first (pages saved as *-s-p<n>)",
    )
    asyncio.run(main(parser.parse_args()))
