"""PDF export: print the rendered document with headless Chrome (proper Indic shaping, same
fitting as the studio). Uses the system Chrome via Playwright (`channel="chrome"`)."""

from playwright.async_api import async_playwright

from .render import render_document


def export_html(doc, lang, store, pages=None):
    """Write the printable HTML next to the page images (relative URLs) and return its path."""
    doc_dir = store.dir(doc.id)
    path = doc_dir / f"export-{lang or 'source'}.html"
    path.write_text(render_document(doc, lang, lambda p: p.background, pages))
    return path


async def measure_and_print(html_path, width_pt, height_pt):
    """Load the HTML in Chrome, wait for fonts and fitting, and return (pdf bytes, fit report).

    The fit report has one entry per block: {id, scale, fill, overflow} — how much the text had to shrink
    how much of its box the text fills, and whether it still overflows it."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        try:
            page = await browser.new_page()
            await page.goto(html_path.resolve().as_uri())
            await page.wait_for_function("document.body.dataset.fitted === '1'", timeout=30_000)
            report = await page.evaluate("""() => [...document.querySelectorAll('[data-block-id]')].map(el => {
                const fitted = [el, ...el.querySelectorAll('[data-fit]')].filter(e => e.dataset.fit);
                const scales = fitted.map(e => parseFloat(e.dataset.scale || '1'));
                const range = document.createRange();
                range.selectNodeContents(el);
                return {id: el.dataset.blockId, status: el.dataset.status,
                        scale: scales.length ? Math.min(...scales) : 1,
                        // against the original box: growing into the empty space below isn't a gap
                        fill: range.getBoundingClientRect().height
                              / (parseFloat((el.dataset.box || '').split('|')[0]) * 96 / 72 || el.clientHeight || 1),
                        overflow: fitted.some(e => e.scrollHeight > e.clientHeight + 2 || e.scrollWidth > e.clientWidth + 2)};
            })""")
            pdf = await page.pdf(
                width=f"{width_pt / 72:.4f}in",
                height=f"{height_pt / 72:.4f}in",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                prefer_css_page_size=True,
            )
            return pdf, report
        finally:
            await browser.close()


async def export_pdf(doc, lang, store, pages=None):
    """Render and print; saves translated-<lang>.pdf in the document dir. Returns (path, fit report)."""
    html_path = export_html(doc, lang, store, pages)
    first = doc.pages[0]
    pdf, report = await measure_and_print(html_path, first.width, first.height)
    out = store.dir(doc.id) / f"translated-{lang or 'source'}.pdf"
    out.write_bytes(pdf)
    return out, report
