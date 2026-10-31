"""Reviewer edits of one block's translation: a prompt edit (OpenRouter, with Bodhan translating when the prompt
asks for another language) and undo. Each returns the block, the language the change landed in, and the block's new
HTML in it, so the studio swaps just that section."""

import dataclasses
import json
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException

from ..clients import ApiError
from ..core.models import Block
from ..pipeline.edit import (
    EDIT_MODEL,
    EditError,
    apply_edit,
    ask_edit,
    current_value,
    is_edit,
    original_value,
    parse_reply,
    reply_language,
    revert,
    usable,
    written_in,
)
from ..pipeline.glossary import terms_for
from ..pipeline.render import render_block
from ..pipeline.translate.run import translate_block
from .deps import Services, ServicesDep, asset_url, background_url, find_block, font_urls
from .schemas import EditRequest, LangRequest

router = APIRouter(prefix="/api/documents/{doc_id}/blocks/{block_id}", tags=["edits"])


async def _change_block(
    svc: Services, doc_id: str, block_id: str, lang: str, change: Callable[[Block], Awaitable[None]]
) -> dict:
    """Apply `change(block)` under the document lock and save; the block and its new HTML in `lang`."""
    async with svc.store.locks[doc_id]:
        doc = svc.document(doc_id)
        page, block = find_block(doc, block_id)
        try:
            await change(block)
        except EditError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ApiError as exc:
            raise HTTPException(502, f"OpenRouter: {exc}") from exc
        svc.store.save(doc)
        return {
            "block": block.model_dump(),
            "page": page.index,
            "lang": lang,
            "html": render_block(
                block, page, lang, fonts=font_urls(doc), crop=background_url(doc_id, page), asset=asset_url(doc_id)
            ),
        }


@router.post("/edit")
async def edit_block(doc_id: str, block_id: str, req: EditRequest, svc: ServicesDep):
    """Prompt-edit one block's translation. A prompt asking for another language lands in that language's
    translation (the document's own language stays in this one: "keep it in English"). The model only names the
    language: Bodhan translates, and the document's own language is the original's text. The model is asked before
    taking the document lock, so several sections are edited at once (the answer is applied to the block as it is
    then, should another edit of it have landed meanwhile)."""
    doc = svc.document(doc_id)
    _, block = find_block(doc, block_id)
    try:
        result = await ask_edit(
            block,
            req.lang,
            req.instruction,
            svc.openrouter,
            req.regenerate,
            terms_for(block, req.lang, svc.glossary.terms()),
        )
    except EditError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ApiError as exc:
        raise HTTPException(502, f"OpenRouter: {exc}") from exc

    if not is_edit(result.text):
        raise HTTPException(502, "The model didn't answer with an edit. Try again.")
    written = reply_language(result.text)
    lang = written if written and written != doc.source_lang else req.lang
    shown = usable(block, req.lang)
    # The language of the text the model was given, by its script: Bodhan can answer in the wrong language.
    edited = (shown.lang or written_in(shown.text or "", req.lang) or req.lang) if shown else doc.source_lang
    model = EDIT_MODEL
    if written and written != edited:  # another language: the model leaves the text to Bodhan, or to the original
        if written == doc.source_lang:
            value = original_value(block)
        else:
            value = await bodhan_translation(block, written, svc)
            model = f"{EDIT_MODEL} + Bodhan"
        _, style = parse_reply(result.text)
        reply = {"translation": value, "language": written, "style": style}
        result = dataclasses.replace(result, text=json.dumps(reply, ensure_ascii=False))

    async def change(block):
        """Apply the edit's answer to the block."""
        apply_edit(block, lang, req.instruction, result, model)

    return await _change_block(svc, doc_id, block_id, lang, change)


async def bodhan_translation(block, lang, svc):
    """Bodhan's translation of the block's original into `lang`, in the form of `edit.current_value`."""
    t = await translate_block(block, lang, svc.bodhan)
    if t.status == "error":
        raise HTTPException(502, f"Bodhan: {t.error}")
    return current_value(block, t)


@router.post("/revert")
async def revert_block(doc_id: str, block_id: str, req: LangRequest, svc: ServicesDep):
    """Undo the last edit (one that created the translation removes it)."""

    async def change(block):
        """Undo the block's last edit in `req.lang`."""
        revert(block, req.lang)

    return await _change_block(svc, doc_id, block_id, req.lang, change)
