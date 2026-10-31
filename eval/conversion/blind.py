"""Blind image sets for the conversion comparison: per page orig.png, A.png, B.png, in two passes with A/B
swapped. Which converter is A is random per page (seeded) and recorded in key.json, outside the folders the
judges read. Usage (repo root, project venv): blind.py <work dir> <name 1> <name 2>"""

import asyncio
import json
import random
import re
import sys
from pathlib import Path

import pymupdf
from playwright.async_api import async_playwright


def original(stem, out):
    """Save the original page a stem ("<doc>-p<n>") names as a PNG at `out`."""
    doc, page = re.match(r"(.+)-p(\d+)$", stem).groups()
    pymupdf.open(f"documents/{doc}.pdf")[int(page) - 1].get_pixmap(dpi=110, alpha=False).save(out)


async def main(work, n1, n2):
    """Screenshot both converters' HTML for every page they share and write the blind A/B sets and key.json."""
    work = Path(work)
    stems = sorted({p.stem for p in (work / n1).glob("*.html")} & {p.stem for p in (work / n2).glob("*.html")})
    rng = random.Random(7)
    key = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        page = await browser.new_page(viewport={"width": 860, "height": 1000})
        for stem in stems:
            first = rng.choice([n1, n2])
            second = n2 if first == n1 else n1
            key[stem] = {"pass1": {"A": first, "B": second}, "pass2": {"A": second, "B": first}}
            shots = {}
            for name in (n1, n2):
                await page.goto((work / name / f"{stem}.html").resolve().as_uri())
                await page.wait_for_timeout(300)
                shots[name] = await page.screenshot(full_page=True)
            for pass_, ab in key[stem].items():
                d = work / "blind" / pass_ / stem
                d.mkdir(parents=True, exist_ok=True)
                original(stem, str(d / "orig.png"))
                for label, name in ab.items():
                    (d / f"{label}.png").write_bytes(shots[name])
        await browser.close()
    (work / "key.json").write_text(json.dumps(key, indent=1))
    print(len(stems), "pages")


asyncio.run(main(*sys.argv[1:]))
