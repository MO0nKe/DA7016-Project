"""Pairwise vision judge: which conversion of a PDF page into a flowing document captures it better?
Usage (repo root, project venv): judge.py <work dir> <name A> <name B> [page stems...]
<work dir>/<name>/<stem>.html are the candidates; originals are rendered from documents/<doc>.pdf.
Each page is judged twice with A and B swapped; a point counts only where both orders agree.
Spends OpenRouter credits (cached, so re-runs are free)."""

import asyncio
import base64
import io
import json
import os
import re
import sys
from pathlib import Path

import pymupdf
from PIL import Image
from playwright.async_api import async_playwright

sys.path.insert(0, ".")
os.environ.setdefault("BODHAN_BASE_URL", "https://api.bodhan.ai")
os.environ.setdefault("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
from backend.clients import make_clients
from backend.core.config import load_settings

MODEL = "anthropic/claude-opus-5.5"
POINTS = ["reading_order", "headings", "lists", "tables", "figures", "inline_formatting", "completeness", "noise"]
PROMPT = """You are checking two conversions (A and B) of one PDF page into a flowing, reflowable document, like a
reader view. Image 1 is the original page. Image 2 is conversion A, image 3 is conversion B.

The conversions are NOT meant to look like the page: text reflows, layout changes. Ignore looks, fonts and spacing.
Judge only how faithfully each one captures the page's content and structure:
- reading_order: text in the order a person reads the page (columns, sidebars, captions in sensible places)
- headings: titles and section headings present, as headings, at sensible levels
- lists: bullet/numbered items as list items, with nesting where the page nests
- tables: tables as tables, with the right rows, columns and header
- figures: pictures, charts and equations present where they belong (as images is fine), captions with them
- inline_formatting: bold, italic, superscripts/subscripts, links where the page has them
- completeness: no missing, duplicated or garbled text
- noise: no running headers/footers, page numbers or stray fragments left in the flow

For each point answer "A", "B", "tie" (both equally good or equally bad) or "na" (the page has nothing of that kind).
Reply with JSON only:
{"reading_order": ..., "headings": ..., "lists": ..., "tables": ..., "figures": ..., "inline_formatting": ...,
 "completeness": ..., "noise": ..., "overall": "A"|"B"|"tie",
 "issues_A": ["<short, specific problem quoting the text involved>", ...], "issues_B": [...]}"""


def data_url(img, max_side=1600):
    """The image as a JPEG data URL, scaled down to at most `max_side` pixels."""
    img = img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def original(stem):
    """The original page a stem ("<doc>-p<n>") names, as an image."""
    doc, page = re.match(r"(.+)-p(\d+)$", stem).groups()
    pix = pymupdf.open(f"documents/{doc}.pdf")[int(page) - 1].get_pixmap(dpi=110, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


async def shots(paths):
    """Full-page screenshots of the candidate HTML files (long pages are scaled down by data_url)."""
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        page = await browser.new_page(viewport={"width": 860, "height": 1000})
        for path in paths:
            await page.goto(path.resolve().as_uri())
            await page.wait_for_timeout(300)
            out[path] = Image.open(io.BytesIO(await page.screenshot(full_page=True)))
        await browser.close()
    return out


async def main(work, a, b, stems):
    """Judge each page's two conversions in both orders and write the verdicts, keeping only points both orders agree
    on."""
    work = Path(work)
    stems = stems or sorted({p.stem for p in (work / a).glob("*.html")} & {p.stem for p in (work / b).glob("*.html")})
    images = await shots([work / n / f"{s}.html" for s in stems for n in (a, b)])
    settings = load_settings()
    _, openrouter = make_clients(settings)
    results = {}
    async with openrouter:
        for stem in stems:
            orig = data_url(original(stem))
            cand = {n: data_url(images[work / n / f"{stem}.html"]) for n in (a, b)}
            verdicts = []
            for first, second in ((a, b), (b, a)):
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PROMPT},
                            {"type": "image_url", "image_url": {"url": orig}},
                            {"type": "image_url", "image_url": {"url": cand[first]}},
                            {"type": "image_url", "image_url": {"url": cand[second]}},
                        ],
                    }
                ]
                r = await openrouter.chat(messages, model=MODEL, max_tokens=1500, temperature=0)
                m = re.search(r"\{.*\}", r.text, re.S)
                v = json.loads(m.group(0)) if m else {}
                name = {"A": first, "B": second}
                verdicts.append(
                    {k: name.get(v.get(k), v.get(k)) for k in POINTS + ["overall"]}
                    | {f"issues_{first}": v.get("issues_A", []), f"issues_{second}": v.get("issues_B", [])}
                )
            v1, v2 = verdicts
            agreed = {k: (v1[k] if v1[k] == v2[k] else "tie") for k in POINTS + ["overall"]}
            results[stem] = {"agreed": agreed, "runs": verdicts}
            print(stem, json.dumps(agreed))
        (work / f"verdicts-{a}-vs-{b}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
        print(openrouter.ledger.summary()[-1] if openrouter.ledger.summary() else "")


asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]))
