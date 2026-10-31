"""Evaluate the pipeline on one PDF and one target language; writes a JSON + Markdown report.

    uv run scripts/evaluate.py fixtures/inputs/sample_en.pdf --lang hi            # free metrics
    uv run scripts/evaluate.py fixtures/inputs/sample_en.pdf --lang hi --back-translate --judge 5

Uses whatever APIs the settings point at (the mock by default). Against the live APIs it prints
the cost estimate and stops unless you pass --yes. Everything is cached, so re-runs are free.
Reports go to data/eval/.
"""

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.clients import make_clients  # noqa: E402
from backend.core.config import load_settings  # noqa: E402
from backend.core.jobs import Job  # noqa: E402
from backend.core.store import DocumentStore  # noqa: E402
from backend.pipeline import evaluate as ev  # noqa: E402
from backend.pipeline.export import export_pdf  # noqa: E402
from backend.pipeline.ingest import ingest_pdf  # noqa: E402
from backend.pipeline.translate import estimate, translate_document  # noqa: E402


async def main(args):
    """Translate one PDF and write its evaluation report (JSON and Markdown) under the data directory's eval/."""
    settings = load_settings()
    store = DocumentStore(settings.data_dir / "documents")
    pdf = Path(args.pdf).read_bytes()
    doc = ingest_pdf(pdf, Path(args.pdf).name, store)
    if pending := [p.index for p in doc.pages if p.source == "pending_ocr"]:
        print(f"note: pages {pending} need OCR and are not evaluated")

    bodhan, openrouter = make_clients(settings)
    async with bodhan, openrouter:
        cost = estimate(doc, args.lang, bodhan)
        where = "LIVE APIs (spends credits)" if settings.spends_credits else "mock APIs"
        print(
            f"{where}: translation needs {cost['calls']} calls ({cost['cached_calls']} cached), "
            f"~{cost['est_output_tokens']} output tokens"
            + (", back-translation roughly doubles that" if args.back_translate else "")
        )
        if settings.spends_credits and not args.yes:
            print("re-run with --yes to spend them")
            return

        job = Job(id="eval", kind="translate", doc_id=doc.id, langs=[args.lang], started="")
        await translate_document(store, doc.id, args.lang, bodhan, job)
        doc = store.load(doc.id)

        report = {
            "pdf": args.pdf,
            "lang": args.lang,
            "apis": where,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "pages": len(doc.pages),
        }
        with tempfile.TemporaryDirectory() as tmp:
            scratch = DocumentStore(Path(tmp))
            # 1. Reconstruction: original text over the text-free background, read back.
            src_path, src_fit = await export_pdf(doc, None, store)
            rebuilt = ingest_pdf(src_path.read_bytes(), "rebuilt.pdf", scratch)
            report["reconstruction"] = ev.structure_metrics(doc, rebuilt, compare_text=True)
            # 2. Translation: same check on the translated export (text differs, layout shouldn't).
            out_path, out_fit = await export_pdf(doc, args.lang, store)
            translated = ingest_pdf(out_path.read_bytes(), "translated.pdf", scratch)
            report["translated_structure"] = ev.structure_metrics(doc, translated)
        report["fit"] = ev.fit_metrics(out_fit)
        report["coverage"] = ev.coverage_metrics(doc, args.lang)
        report["exported_pdf"] = str(out_path)
        if args.back_translate:
            report["back_translation"] = await ev.back_translation_chrf(doc, args.lang, args.source_lang, bodhan)
        if args.judge:
            report["judge"] = await ev.judge(doc, args.lang, openrouter, args.judge)
        report["usage"] = bodhan.ledger.summary()

    out_dir = settings.data_dir / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{Path(args.pdf).stem}-{args.lang}"
    (out_dir / f"{stem}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    (out_dir / f"{stem}.md").write_text(markdown(report))
    print(markdown(report))
    print(f"written to {out_dir / stem}.{{json,md}}")


def markdown(r):
    """The evaluation report as Markdown tables."""

    def table(title, d):
        """One section of scalar metrics as a Markdown table."""
        rows = "\n".join(f"| {k} | {v} |" for k, v in d.items() if not isinstance(v, (list, dict)))
        return f"### {title}\n\n| metric | value |\n|---|---|\n{rows}\n"

    parts = [
        f"# Evaluation: {r['pdf']} → {r['lang']}\n\n{r['apis']}, {r['ts']}, {r['pages']} pages\n",
        table("Reconstruction (source text re-rendered, read back)", r["reconstruction"]),
        table("Translated layout vs original", r["translated_structure"]),
        table("Text fitting", r["fit"]),
        table("Coverage", r["coverage"]),
    ]
    if "back_translation" in r:
        parts.append(table("Back-translation", r["back_translation"]))
    if "judge" in r:
        parts.append(table("LLM judge", r["judge"]))
    return "\n".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf")
    parser.add_argument("--lang", required=True, help="target language code, e.g. hi")
    parser.add_argument("--source-lang", default="en", help="language to back-translate into (default en)")
    parser.add_argument("--back-translate", action="store_true", help="chrF of a back-translation (Bodhan credits)")
    parser.add_argument("--judge", type=int, default=0, metavar="N", help="LLM-judge N sections (OpenRouter credits)")
    parser.add_argument("--yes", action="store_true", help="allow spending credits on the live APIs")
    asyncio.run(main(parser.parse_args()))
