"""Reviewer edits of one block's translation: prompt-edits through OpenRouter, and revert.

A prompt may reword the translation, fix garbled maths, or change how the block looks (`Translation.style`). Styled
runs travel as their tags, as in translation. The model also names the language it wrote in: a prompt asking for
another language lands in that language's translation (the route decides, see `reply_language`). A section not
translated yet is edited from its original text. Edits are recorded on the translation (`edits`), newest last;
revert pops the newest one, and removes a translation an edit created.
"""

import json
import re
import time

from ..core.languages import LANGUAGES, SCRIPT_RANGES, in_script_ratio
from ..core.models import Edit, Translation
from .markup import TAG_SPLIT, runs_intact, untagged

FENCE = re.compile(r"^```[\w-]*\n?|\n?```$")
COLOR = re.compile(r"#[0-9a-f]{6}")
ALIGNS = {"left", "center", "right", "justify"}
EDIT_MODEL = "anthropic/claude-sonnet-5.5"  # flash-lite added Markdown and ignored "keep the tags"; $0.002–0.01 an edit
EMPHASIS = re.compile(r"(\*\*?|__?)(?=\S)(.+?)(?<=\S)\1")  # Markdown *italic*, **bold**, _x_


def unmarkdown(after, before):
    """`after` without Markdown emphasis the model added (told not to, flash-lite still writes "*text*"); a * or _
    the text already had is kept."""
    return EMPHASIS.sub(lambda m: m.group(0) if m.group(1)[0] in before else m.group(2), after)


class EditError(Exception):
    """A prompt edit that can't be made: no text, an unusable reply, or nothing to undo."""

    pass


def current_value(block, t):
    """The translation as one string: text (with its styled runs' tags), or the cells as a JSON array."""
    if block.cells:
        return json.dumps(t.cells or [], ensure_ascii=False)
    if block.html:
        return t.html or ""
    return t.rich or t.text


def original_value(block):
    """The block's original in the form of `current_value`."""
    return (
        json.dumps([c.text for c in block.cells], ensure_ascii=False)
        if block.cells
        else block.html or block.rich or block.text
    )


def written_in(text, lang):
    """The language `text` is written in when it isn't `lang`'s script (an edit asked for English), else None."""
    ratio = in_script_ratio(text, lang)
    if ratio is None or ratio >= 0.5:
        return None
    return max(SCRIPT_RANGES, key=lambda code: in_script_ratio(text, code) or 0)  # first code of its script


def apply_value(block, t, value, lang):
    """Put `value` (cell list as JSON, table HTML, tagged or plain text) into the translation `t` in the block's form,
    and note the language it's written in."""
    if block.cells:
        cells = json.loads(value)
        if not (isinstance(cells, list) and len(cells) == len(block.cells) and all(isinstance(c, str) for c in cells)):
            raise EditError(f"expected a JSON array of {len(block.cells)} strings")
        t.cells = cells
    elif block.html:
        t.html = value
        t.text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()
    elif TAG_SPLIT.search(value):
        t.rich = value if runs_intact(value) else None  # broken tags: keep the words, drop the styling
        t.text = untagged(value)
    else:
        t.rich, t.text = None, value
    t.lang = written_in(t.text, lang) if not block.cells else None


def checked_style(raw):
    """The look changes a reply asked for, keeping only known keys with usable values."""
    out = {}
    for key, v in (raw if isinstance(raw, dict) else {}).items():
        if key in ("bold", "italic", "hanging") and isinstance(v, bool):
            out[key] = v
        elif key == "color" and isinstance(v, str) and COLOR.fullmatch(v.lower()):
            out[key] = v.lower()
        elif key == "align" and v in ALIGNS:
            out[key] = v
        elif key == "font_size" and isinstance(v, int | float) and not isinstance(v, bool) and 4 <= v <= 96:
            out[key] = round(float(v), 1)
    return out


def restyle(block, t, changes):
    """`t.style` with `changes`, dropping any that only repeat the block's own look."""
    merged = {**t.style, **changes}
    t.style = {k: v for k, v in merged.items() if getattr(block.style, k) != v}


def look(block, t):
    """The translation's current look in words ("bold, aligned left, 10 pt"), for the model."""
    s = block.style.model_copy(update=t.style)
    parts = [
        "bold" if s.bold else "",
        "italic" if s.italic else "",
        f"colour {s.color}" if s.color else "",
        f"aligned {s.align}",
        "hanging indent" if s.hanging else "",
        f"{s.font_size:g} pt" if s.font_size else "",
    ]
    return ", ".join(p for p in parts if p)


def build_messages(block, lang, current, instruction, terms=(), t=None):
    """The chat messages asking the model to revise the block's translation `current` as `instruction` says, keeping
    glossary `terms`."""
    name = LANGUAGES.get(lang, lang)
    shape = "a string"
    if block.cells:
        shape = f"a JSON array of exactly {len(block.cells)} strings, one per table cell, in the same order"
    elif block.html:
        shape = "the full table HTML, changing only the text"
    system = (
        f"You revise one section of a document translated into {name} ({lang}), as the reader instructs. "
        "The instruction may ask to change the wording; to put the section in another language (only this "
        "section changes) or another script; to fix maths that shows as LaTeX or garbled symbols (write it in "
        "plain Unicode, such as x², √2 or Σᵢ aᵢ); to break lines (\\n); or to change how the section looks.\n"
        'Reply with only a JSON object: {"translation": the whole revised translation as ' + shape + ", "
        f'"language": the code of the language the revised section is in ("{lang}" unless the instruction asks for '
        "another: en, hi, bn, ta, te, kn, ml, mr, gu, pa, or, as, ur, ne, sa…), "
        '"style": the look changes asked for, else {}}.\n'
        "Whenever the revised section would be in another language than the current translation is written in, "
        '"translation" is null: a translation service writes it. Still give "language" and "style". Never translate '
        "yourself: when the instruction asks for a translation, give null and the language it asks for.\n"
        f"Keep the translation in {name} in its usual script, and keep numbers, names, maths exactly as written "
        "(such as 𝑥(𝑡) or ∈R) and footnote markers (¹²³), unless the instruction says otherwise. Words styled "
        'apart from the rest are wrapped in <b>, <i> or <span style="color:#rrggbb"> tags: keep the tags around '
        "the same words, and add or remove them only to style words as asked. The translation is plain text: "
        "no Markdown (never * or _ for emphasis).\n"
        '"style" is only for the whole section (style some words with tags alone): "bold" and "italic" (true or '
        'false), "color" ("#rrggbb"), '
        '"align" ("left", "center", "right" or "justify"), "hanging" (true: in a list item, wrapped lines '
        'start under the text after the bullet or number, not under the bullet), and "font_size" (points, for '
        "larger or smaller text; text too long for its place is made smaller anyway)."
    )
    if terms:
        pinned = "; ".join(f'"{term.source}" → "{term.target}"' for term in terms)
        system += f" Always translate these terms exactly as given: {pinned}."
    source = (
        json.dumps([c.text for c in block.cells], ensure_ascii=False) if block.cells else (block.html or block.text)
    )
    looks = f"\nCurrent look: {look(block, t)}" if t else ""
    user = (
        f"Section type: {block.label}{looks}\n\nOriginal text:\n{source}\n\n"
        f"Current translation:\n{current}\n\nInstruction: {instruction}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def clean_reply(text):
    """The model's reply without Markdown code fences or wrapping quotes."""
    text = FENCE.sub("", text.strip()).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'“”":
        text = text[1:-1].strip()
    return text


REPLY_KEYS = {"translation", "language", "style"}


def reply_json(text):
    """The reply's JSON object, ignoring any prose the model wrote around it ("{…}\n\nI couldn't reduce the font
    size…"). A table's bare array, or text that only contains braces, is not one."""
    text = clean_reply(text)
    start = text.find("{")
    try:
        data, _ = json.JSONDecoder().raw_decode(text, start) if start >= 0 else (None, 0)
    except ValueError:
        return None
    return data if isinstance(data, dict) and REPLY_KEYS & data.keys() else None


def is_edit(text):
    """Whether a reply is an edit: its JSON object, or a table's bare array of cells. Anything else is the model
    talking (reasoning, a refusal), never a section's text."""
    if reply_json(text) is not None:
        return True
    try:
        return isinstance(json.loads(clean_reply(text)), list)
    except ValueError:
        return False


def parse_reply(text):
    """(value, look changes) from the model's JSON reply; a reply that isn't a JSON object is all value."""
    data = reply_json(text)
    if data is None:
        return clean_reply(text), {}
    value = data.get("translation")
    if isinstance(value, list):
        value = json.dumps(value, ensure_ascii=False)
    return (value.strip() if isinstance(value, str) else ""), checked_style(data.get("style"))


def reply_language(text):
    """The language code the model says its reply is written in, if it's one the app translates into."""
    code = (reply_json(text) or {}).get("language")
    return code if code in LANGUAGES else None


def record(t, instruction, before, after, model, cost=0.0, style_before=None, created=False):
    """Append an edit to the translation's history (for undo) and mark it edited."""
    t.edits.append(
        Edit(
            instruction=instruction,
            before=before,
            after=after,
            model=model,
            ts=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            cost_usd=cost,
            style_before=t.style if style_before is None else style_before,
            created=created,
        )
    )
    t.status = "edited"


def usable(block, lang):
    """The block's translation into `lang`, or None when it has none yet (or only a failed one)."""
    t = block.translations.get(lang)
    return t if t and t.status != "error" else None


async def ask_edit(block, lang, instruction, openrouter, regenerate=False, terms=(), model=EDIT_MODEL):
    """The model's answer to `instruction` for the block's translation (its original text when there is none
    yet); changes nothing (see apply_edit)."""
    if not (block.text or block.cells or block.html):
        raise EditError("this section has no text")
    t = usable(block, lang)
    current = current_value(block, t) if t else original_value(block)
    return await openrouter.chat(
        build_messages(block, lang, current, instruction, terms, t), model=model, use_cache=not regenerate
    )


def apply_edit(block, lang, instruction, result, model):
    """`ask_edit`'s answer applied to the block's translation into `lang`, created if there is none yet, and
    recorded as an edit."""
    t = usable(block, lang)
    created = t is None
    t = t or Translation()  # attached once the reply is applied
    before, style_before = current_value(block, t), dict(t.style)
    after, changes = parse_reply(result.text)
    if not after and not changes:
        raise EditError("the model returned an empty reply")
    after = unmarkdown(after, before) or before  # empty: only the look changed
    try:
        apply_value(block, t, after, lang)
    except (ValueError, EditError) as exc:
        raise EditError(f"unusable reply ({exc}): {after[:200]}") from exc
    restyle(block, t, changes)
    record(t, instruction, before, after, model, result.cost_usd, style_before, created)
    block.translations[lang] = t
    return t


async def prompt_edit(block, lang, instruction, openrouter, regenerate=False, terms=(), model=EDIT_MODEL):
    """Ask the model for an edit and apply it; the edited translation."""
    result = await ask_edit(block, lang, instruction, openrouter, regenerate, terms, model)
    return apply_edit(block, lang, instruction, result, model)


def revert(block, lang):
    """Undo the translation's last edit; the restored translation, or None when that edit had created it."""
    t = block.translations.get(lang)
    if t is None or not t.edits:
        raise EditError("nothing to revert")
    last = t.edits.pop()
    if last.created:
        del block.translations[lang]  # the edit made this translation: undoing it leaves none
        return None
    apply_value(block, t, last.before, lang)
    t.style = last.style_before
    if not t.edits:
        t.status = "done"
    return t
