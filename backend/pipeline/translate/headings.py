"""The heading pass: OpenRouter revises short headings Bodhan translated on their own, given the start
of the section each introduces. Recorded as a prompt edit, so it can be undone."""

import asyncio

from ...clients import ApiError
from ..edit import EditError, prompt_edit, revert
from ..markup import SUPERSCRIPTS, untagged
from .units import HEADINGS, already_in, english_case

HEADING_WORDS = 6  # longer headings carry enough context of their own


HEADING_MODEL = "anthropic/claude-sonnet-5.5"  # flash-lite kept "Used oil" for the surahs; ~$0.001 a heading


def heading_instruction(following):
    """The prompt-edit instruction for a heading, with the start of its section (`following`) as context."""
    return (
        'This heading was machine-translated on its own, so it may be a fragment or too literal ("Effect of" '
        'for a heading meaning "Influence"). Translate what the original heading itself says, as a proper '
        "heading: no more words than it needs, none taken from the section, no article it doesn't need, sentence "
        "case, no full stop." + (f" For context only, the section begins: {following[:300]}" if following else "")
    )


async def refine_headings(page, results, lang, openrouter):
    """OpenRouter revises the short headings Bodhan translated on a page (`results`: block id -> Translation),
    given the start of the section each one introduces. Recorded as a prompt-edit, so it shows as edited and can
    be undone; a reply that isn't a heading (empty, several lines, far longer) is undone at once."""
    blocks = sorted(page.blocks, key=lambda b: b.order)

    async def one(n, b):
        """Revise heading block `b` (the `n`th in reading order) if it qualifies, undoing a reply that isn't a
        heading."""
        t = results.get(b.id)
        if (
            b.label not in HEADINGS
            or not t
            or t.status != "done"
            or not t.text
            or b.cells
            or b.html
            or len(b.text.split()) > HEADING_WORDS
            or already_in(b.text, lang)
        ):
            return
        following = next((c.text for c in blocks[n + 1 :] if c.text and c.label not in HEADINGS), "")
        bodhan_text = t.text
        b.translations[lang] = t
        try:
            await prompt_edit(b, lang, heading_instruction(following), openrouter, model=HEADING_MODEL)
        except (EditError, ApiError):
            return
        if lang == "en":
            t.text = english_case(t.text, heading=True)
            t.rich = t.rich and english_case(t.rich, heading=True)
        if bodhan_text.rstrip().endswith((":", "ঃ", "：")) and not t.text.rstrip().endswith(":"):
            t.text = (
                t.text.rstrip() + ":"
            )  # "Bengali translation:" introduces what follows; told "no full stop", models drop it
            t.rich = t.rich and t.rich.rstrip() + ":"
        t.edits[-1].after = t.rich or t.text
        words = len(untagged(t.text).split())
        marks = lambda x: sorted(c for c in x if c.isdigit() or c in SUPERSCRIPTS + "∗*†‡")  # noqa: E731
        if (
            t.text == bodhan_text
            or "\n" in t.text
            or words > max(len(bodhan_text.split()), len(b.text.split()) + 1)
            or marks(t.text) != marks(bodhan_text)
        ):
            revert(b, lang)  # unchanged, not a heading (a sentence, words from the section), or numbers/markers lost

    await asyncio.gather(*(one(n, b) for n, b in enumerate(blocks)))
