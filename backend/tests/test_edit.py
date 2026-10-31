import asyncio
import json

from backend.api import edits
from backend.clients.openrouter import ChatResult
from backend.core.models import Block, Page, Style, Translation
from backend.pipeline.edit import clean_reply, is_edit, parse_reply, prompt_edit, reply_language, revert, unmarkdown
from backend.pipeline.render import render_block

from .conftest import fail_next, upload
from .test_render import translate


def test_prompt_edit_updates_only_that_block(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    translate(api, doc_id, "hi")
    before = api.get(f"/api/documents/{doc_id}").json()
    r = api.post(f"/api/documents/{doc_id}/blocks/p0-b3/edit", json={"lang": "hi", "instruction": "Make it formal"})
    assert r.status_code == 200, r.text
    body = r.json()
    t = body["block"]["translations"]["hi"]
    assert t["status"] == "edited" and "Make it formal" in t["text"]  # the mock echoes the instruction
    assert t["edits"][0]["model"] == "anthropic/claude-sonnet-5.5"
    assert body["html"].startswith('<div class="ds-block') and 'data-block-id="p0-b3"' in body["html"]
    after = api.get(f"/api/documents/{doc_id}").json()
    changed = [
        b["id"]
        for p0, p1 in zip(before["pages"], after["pages"])
        for b0, b in zip(p0["blocks"], p1["blocks"])
        if b0 != b
    ]
    assert changed == ["p0-b3"]


def test_table_edits_need_one_string_per_cell(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    translate(api, doc_id, "hi")
    table = next(b for b in api.get(f"/api/documents/{doc_id}").json()["pages"][0]["blocks"] if b["cells"])
    url = f"/api/documents/{doc_id}/blocks/{table['id']}"
    # The echo mock doesn't answer with a JSON array, so a prompt-edit of a table is rejected cleanly.
    assert api.post(f"{url}/edit", json={"lang": "hi", "instruction": "x"}).status_code == 400


def test_an_untranslated_section_is_edited_from_its_original_and_undo_removes_it(api, mock_app):
    doc_id = upload(api, "sample_en.pdf")["id"]
    url = f"/api/documents/{doc_id}/blocks/p0-b3"
    r = api.post(f"{url}/edit", json={"lang": "hi", "instruction": "Translate it"})
    assert r.status_code == 200 and r.json()["lang"] == "hi"
    t = r.json()["block"]["translations"]["hi"]
    assert t["status"] == "edited" and t["edits"][0]["created"] and "Translate it" in t["text"]
    assert api.post(f"{url}/revert", json={"lang": "hi"}).json()["block"]["translations"] == {}
    fail_next(mock_app, "401")
    assert api.post(f"{url}/edit", json={"lang": "hi", "instruction": "x"}).status_code == 502


def test_a_prompt_for_another_language_is_translated_by_bodhan(api, monkeypatch):
    doc_id = upload(api, "sample_en.pdf")["id"]
    translate(api, doc_id, "hi")
    url = f"/api/documents/{doc_id}/blocks/p0-b3"
    hindi = api.get(f"/api/documents/{doc_id}").json()["pages"][0]["blocks"][3]["translations"]["hi"]["text"]

    def replying(reply):
        async def ask(*args, **kwargs):
            return ChatResult(text=json.dumps(reply, ensure_ascii=False), finish_reason="stop")

        monkeypatch.setattr(edits, "ask_edit", ask)

    replying({"translation": None, "language": "ta", "style": {"bold": True}})  # the model leaves the words
    r = api.post(f"{url}/edit", json={"lang": "hi", "instruction": "Tamil, in bold"}).json()
    t = r["block"]["translations"]["ta"]
    assert r["lang"] == "ta" and t["text"] and t["text"] != hindi  # Bodhan's words, the model's look
    assert t["style"] == {"bold": True} and t["edits"][0]["model"].endswith("+ Bodhan")
    assert r["block"]["translations"]["hi"]["text"] == hindi
    replying({"translation": "मॉडल का पाठ", "language": "hi", "style": {}})  # a change within the language
    t = api.post(f"{url}/edit", json={"lang": "hi", "instruction": "simpler"}).json()["block"]["translations"]["hi"]
    assert t["text"] == "मॉडल का पाठ" and t["edits"][-1]["model"] == "anthropic/claude-sonnet-5.5"
    replying({"translation": None, "language": "en", "style": {}})  # "keep it in English": the original's text
    r = api.post(f"{url}/edit", json={"lang": "hi", "instruction": "keep it in English"}).json()
    block = r["block"]
    assert r["lang"] == "hi" and block["translations"]["hi"]["text"] == block["text"]


def test_another_language_lands_in_its_own_translation():
    block = edited_block()
    assert reply_language('{"translation": "x", "language": "ta"}') == "ta"
    assert reply_language('{"translation": "x", "language": "xx"}') is None and reply_language("plain") is None
    asyncio.run(prompt_edit(block, "ta", "in Tamil", Replies('{"translation": "• முதல் சொல்", "language": "ta"}')))
    assert block.translations["ta"].text == "• முதல் சொல்" and block.translations["ta"].edits[0].created
    assert block.translations["hi"].rich == "<b>पहला</b> शब्द और बाकी"  # the Hindi translation is untouched
    assert revert(block, "ta") is None and "ta" not in block.translations


def test_clean_reply():
    assert clean_reply('```\n"नमस्ते"\n```') == "नमस्ते"
    assert clean_reply("  plain  ") == "plain"


def test_dictionary(api):
    r = api.get("/api/define", params={"word": "Surveyed,"}).json()
    assert r["lemma"] == "survey" and any(s["pos"] == "verb" for s in r["senses"])
    assert api.get("/api/define", params={"word": "primary school"}).json()["senses"]
    assert api.get("/api/define", params={"word": "qwzxv"}).json()["senses"] == []
    assert api.get("/api/define", params={"word": "Equivalently"}).json()["lemma"] == "equivalent"  # no adverb entry
    assert api.get("/api/define", params={"word": "नमस्ते"}).status_code == 400


class Replies:
    """A stand-in OpenRouter client that answers with the given replies in turn."""

    default_model = "fake"

    def __init__(self, *replies):
        self.replies = list(replies)

    async def chat(self, messages, model=None, use_cache=True):
        return ChatResult(text=self.replies.pop(0), finish_reason="stop")


def edited_block():
    t = Translation(text="पहला शब्द और बाकी", rich="<b>पहला</b> शब्द और बाकी")
    return Block(
        id="b",
        order=0,
        label="List",
        type="Text",
        bbox=[10, 10, 200, 40],
        source="text_layer",
        text="• First word and the rest",
        style=Style(font_size=10),
        translations={"hi": t},
    )


def test_prompt_edit_keeps_runs_and_changes_the_look():
    block = edited_block()
    page = Page(
        index=0,
        width=300,
        height=300,
        source="text_layer",
        dpi=72,
        image="",
        background="x",
        text_quality=1,
        blocks=[block],
    )
    reply = json.dumps(
        {
            "translation": "• <b>पहला</b> शब्द, बाकी",
            "style": {"align": "center", "hanging": True, "bold": "yes", "size": 30},
        }
    )
    t = asyncio.run(prompt_edit(block, "hi", "centre it, bullet hangs", Replies(reply)))
    assert t.rich == "• <b>पहला</b> शब्द, बाकी" and t.text == "• पहला शब्द, बाकी"
    assert t.style == {"align": "center", "hanging": True}  # unknown keys and bad values dropped
    html = render_block(block, page, "hi")
    assert "text-align:center" in html and "ds-hanging" in html and '<span class="ds-mark">•</span>' in html
    assert "<b>पहला</b>" in html and 'lang="hi"' in html
    revert(block, "hi")
    assert t.rich == "<b>पहला</b> शब्द और बाकी" and t.style == {} and t.status == "done"


def test_prompt_edit_can_switch_the_language():
    block = edited_block()
    t = asyncio.run(
        prompt_edit(block, "hi", "keep it in English", Replies('{"translation": "First word and the rest"}'))
    )
    assert t.lang == "en" and t.rich is None
    page = Page(
        index=0,
        width=300,
        height=300,
        source="text_layer",
        dpi=72,
        image="",
        background="x",
        text_quality=1,
        blocks=[block],
    )
    assert 'lang="en"' in render_block(block, page, "hi")
    asyncio.run(prompt_edit(block, "hi", "Urdu please", Replies('{"translation": "پہلا لفظ اور باقی"}')))
    assert t.lang == "ur" and 'dir="rtl"' in render_block(block, page, "hi")
    asyncio.run(prompt_edit(block, "hi", "back to Hindi", Replies('{"translation": "पहला शब्द"}')))
    assert t.lang is None


def test_parse_reply():
    assert parse_reply('{"style": {"font_size": 12, "bold": "yes"}}') == ("", {"font_size": 12.0})  # checked
    assert parse_reply('{"style": {"font_size": 400}}') == ("", {})
    assert parse_reply('```json\n{"translation": "नमस्ते", "style": {}}\n```') == ("नमस्ते", {})
    assert parse_reply("plain words") == ("plain words", {})  # not JSON: the whole reply is the text
    assert parse_reply('{"translation": ["a", "b"]}') == ('["a", "b"]', {})  # a table's cells
    assert parse_reply('{"style": {"italic": true, "color": "#AA0000"}}') == ("", {"italic": True, "color": "#aa0000"})
    # NIST slides p1-b8: prose after the JSON is not part of the text
    reply = (
        '{"translation": "• 11 ஆவணங்கள்", "language": "ta", "style": {"hanging": true}}\n\nI couldn\'t reduce the size.'
    )
    assert parse_reply(reply) == ("• 11 ஆவணங்கள்", {"hanging": True}) and reply_language(reply) == "ta"
    assert parse_reply("{htouvron, glample}@meta.com") == ("{htouvron, glample}@meta.com", {})  # braces in text
    # NIST slides p1-b9: reasoning before the JSON
    reply = 'The current translation is "March 2025", which is English text…\n\n'
    reply += '{"translation": null, "language": "mr", "style": {}}'
    assert parse_reply(reply) == ("", {}) and reply_language(reply) == "mr" and is_edit(reply)
    assert not is_edit("I can't change the font size: the style options don't include it.")
    assert is_edit('["आइटम", "120"]')  # a table's cells


def test_markdown_the_model_added_is_dropped():
    assert unmarkdown("• *১১ মার্চ, ২০২৫ করে।* and **bold** _x_", "• ১১ মার্চ") == "• ১১ মার্চ, ২০২৫ করে। and bold x"
    assert unmarkdown("a * b * c", "a b c") == "a * b * c"  # spaced asterisks aren't emphasis
    assert unmarkdown("x_1 and *y*", "x_1 and *y*") == "x_1 and *y*"  # already in the text: kept
