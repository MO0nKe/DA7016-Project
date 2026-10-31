"""Evaluation metrics for the report.

Free (no API calls):
  structure   re-ingest an exported PDF and match its blocks to the original's by box overlap:
              how many original blocks reappear in place (IoU), with the same label
  fit         how much text had to shrink to fit its box, and what still overflows
  coverage    translated / truncated / failed sections
  script      share of translated letters actually in the target script (catches untranslated text)

Costs credits on the live APIs (opt-in):
  back-translation chrF   translate the output back to the source language with Bodhan, compare
  judge                   an OpenRouter model rates adequacy and fluency of a sample of sections
"""

import asyncio
import json
import random
import re
from difflib import SequenceMatcher

from sacrebleu.metrics import CHRF

from ..core.languages import LANGUAGES, in_script_ratio
from .translate import translate_text


def iou(a, b):
    """Intersection over union of two boxes."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match_blocks(original, other):
    """Greedy best-IoU matching of blocks, page by page. Returns [(orig, other|None, iou)]."""
    pairs = []
    for p_orig, p_other in zip(original.pages, other.pages):
        candidates = sorted(
            ((iou(a.bbox, b.bbox), i, j) for i, a in enumerate(p_orig.blocks) for j, b in enumerate(p_other.blocks)),
            reverse=True,
        )
        used_a, used_b, found = set(), set(), {}
        for score, i, j in candidates:
            if score < 0.1 or i in used_a or j in used_b:
                continue
            used_a.add(i)
            used_b.add(j)
            found[i] = (p_other.blocks[j], score)
        for i, a in enumerate(p_orig.blocks):
            b, score = found.get(i, (None, 0.0))
            pairs.append((a, b, score))
    return pairs


def structure_metrics(original, rebuilt, compare_text=False):
    """How well `rebuilt` (a re-ingested export) keeps the original's blocks: share matched at IoU 0.5, mean IoU, label
    agreement and, optionally, text similarity."""
    pairs = match_blocks(original, rebuilt)
    matched = [(a, b, s) for a, b, s in pairs if b is not None]
    out = {
        "original_blocks": len(pairs),
        "rebuilt_blocks": sum(len(p.blocks) for p in rebuilt.pages),
        "matched_at_iou_0.5": round(sum(s >= 0.5 for *_, s in pairs) / max(1, len(pairs)), 3),
        "mean_iou": round(sum(s for *_, s in pairs) / max(1, len(pairs)), 3),
        "label_agreement": round(sum(a.label == b.label for a, b, _ in matched) / max(1, len(matched)), 3),
    }
    if compare_text:
        out["text_similarity"] = round(
            sum(SequenceMatcher(None, a.text, b.text).ratio() for a, b, _ in matched) / max(1, len(matched)), 3
        )
    return out


def fit_metrics(report):
    """Summary of a render's fit report: how far translated text had to shrink, and how many boxes overflow or are left
    underfilled."""
    blocks = [r for r in report if r["status"] != "source"] or report
    scales = sorted(r["scale"] for r in blocks)
    return {
        "blocks": len(blocks),
        "median_scale": round(scales[len(scales) // 2], 3) if scales else None,
        "shrunk_below_0.8": round(sum(s < 0.8 for s in scales) / max(1, len(scales)), 3),
        "overflowing": sum(r["overflow"] for r in blocks),
        # A translation that leaves a fifth of its box empty: shrunk or tightened by its group, not by its own length.
        "underfilled": sum(r["status"] == "translated" and r.get("fill", 1) < 0.8 for r in blocks),
    }


def size_spread(doc, report):
    """How unevenly fitting sized blocks that started alike (same label and original font size): the worst
    largest/smallest scale ratio within such a group, and how many groups differ by more than 15%."""
    style = {b.id: (b.label, b.style.font_size) for p in doc.pages for b in p.blocks if b.style.font_size}
    groups = {}
    for r in report:
        if r["status"] == "translated" and r["id"] in style:
            groups.setdefault(style[r["id"]], []).append(r["scale"])
    spreads = [max(s) / max(min(s), 0.01) for s in groups.values() if len(s) > 1]
    return {"size_spread": round(max(spreads, default=1.0), 3), "uneven_groups": sum(s > 1.15 for s in spreads)}


def translated_text(block, t):
    """The translation's text (a table's cells joined)."""
    return " ".join(t.cells or []) if block.cells else t.text


def coverage_metrics(doc, lang):
    """How much of the document is translated into `lang`, by status, and how much of it is in the target script."""
    # Figure text counts only where the user chose to translate it.
    blocks = [b for p in doc.pages for b in p.blocks if b.translatable and (not b.in_figure or lang in b.translations)]
    statuses = [b.translations[lang].status if lang in b.translations else "missing" for b in blocks]
    ratios = [
        r
        for b in blocks
        if lang in b.translations
        for r in [in_script_ratio(translated_text(b, b.translations[lang]), lang)]
        if r is not None
    ]
    return {
        "translatable_blocks": len(blocks),
        **{s: statuses.count(s) for s in ("done", "edited", "truncated", "error", "missing")},
        "mean_in_script_ratio": round(sum(ratios) / len(ratios), 3) if ratios else None,
        "blocks_mostly_wrong_script": sum(r < 0.5 for r in ratios),
    }


async def back_translation_chrf(doc, lang, source_lang, bodhan):
    """chrF between the source text and the translation translated back into `source_lang`."""
    pairs = [
        (b.text, translated_text(b, b.translations[lang]))
        for p in doc.pages
        for b in p.blocks
        if b.translatable and lang in b.translations and b.translations[lang].status != "error"
    ]
    results = await asyncio.gather(*(translate_text(t, source_lang, bodhan) for _, t in pairs), return_exceptions=True)
    kept = [(src, r[0]) for (src, _), r in zip(pairs, results) if not isinstance(r, Exception)]
    failed = len(pairs) - len(kept)
    pairs = kept
    hyps, refs = [h for _, h in kept], [src for src, _ in kept]
    score = CHRF().corpus_score(hyps, [refs]).score if pairs else None
    return {
        "sections": len(pairs),
        "failed": failed,
        "chrf": round(score, 2) if score is not None else None,
        "examples": [{"source": s, "back": h} for s, h in list(zip(refs, hyps))[:3]],
    }


JUDGE_PROMPT = """Rate this translation from the original document into {lang}.
Original: {src}
Translation: {tgt}
Reply with JSON only: {{"adequacy": 1-5, "fluency": 1-5, "comment": "<one short sentence>"}}"""


async def judge(doc, lang, openrouter, sample=5, seed=0):
    """An OpenRouter model's mean adequacy and fluency scores for a random sample of translated sections, with each
    answer and the cost."""
    blocks = [
        b
        for p in doc.pages
        for b in p.blocks
        if b.translatable and lang in b.translations and not b.cells and len(b.text) > 20
    ]
    chosen = random.Random(seed).sample(blocks, min(sample, len(blocks)))

    async def one(b):
        """The judge's scores for one section, or its unparsed reply."""
        prompt = JUDGE_PROMPT.format(lang=LANGUAGES.get(lang, lang), src=b.text, tgt=b.translations[lang].text)
        r = await openrouter.chat([{"role": "user", "content": prompt}], max_tokens=150, temperature=0)
        m = re.search(r"\{.*\}", r.text, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
            return {
                "block": b.id,
                "adequacy": float(data["adequacy"]),
                "fluency": float(data["fluency"]),
                "comment": data.get("comment", ""),
                "cost_usd": r.cost_usd,
            }
        except (ValueError, KeyError, TypeError):
            return {"block": b.id, "unparsed": r.text[:200], "cost_usd": r.cost_usd}

    results = await asyncio.gather(*(one(b) for b in chosen))
    scored = [r for r in results if "adequacy" in r]
    mean = lambda k: round(sum(r[k] for r in scored) / len(scored), 2) if scored else None  # noqa: E731
    return {
        "sampled": len(results),
        "parsed": len(scored),
        "adequacy": mean("adequacy"),
        "fluency": mean("fluency"),
        "cost_usd": round(sum(r["cost_usd"] for r in results), 6),
        "details": results,
    }
