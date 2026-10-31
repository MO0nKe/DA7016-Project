"""Pinned term translations, shared by all documents ("enrolment" in Hindi is always "नामांकन").

Bodhan takes no glossary, so terms are enforced after translation: `misses` finds sections whose
source uses a term but whose translation doesn't use the pinned word, and prompt-edits
(OpenRouter) are told the pinned terms that occur in the section they revise.
"""

import json
import re
import uuid
from pathlib import Path

from pydantic import BaseModel, Field


class Term(BaseModel):
    """A glossary term: how `source` must be translated into `lang`."""

    id: str = ""
    source: str = Field(min_length=1, max_length=200)
    lang: str
    target: str = Field(min_length=1, max_length=200)


class Glossary:
    """The user's glossary, kept in one JSON file."""

    def __init__(self, path):
        self.path = Path(path)

    def terms(self):
        """Every saved term."""
        return [Term.model_validate(t) for t in json.loads(self.path.read_text())] if self.path.exists() else []

    def _save(self, terms):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([t.model_dump() for t in terms], ensure_ascii=False, indent=1))

    def add(self, term):
        """Save a term (replacing an earlier one for the same word and language) and return it with its new id."""
        terms = [t for t in self.terms() if not (t.source.lower() == term.source.lower() and t.lang == term.lang)]
        term.id = uuid.uuid4().hex[:10]
        self._save([*terms, term])  # re-pinning a term replaces its old translation
        return term

    def remove(self, term_id):
        """Delete a term; whether it existed."""
        terms = self.terms()
        self._save([t for t in terms if t.id != term_id])
        return len(terms) != len(self.terms())


def source_text(block):
    """The block's original text (a table's cells joined)."""
    return " ".join(c.text for c in block.cells) if block.cells else block.text


def translated_text(t):
    """The translation's text (a table's cells joined)."""
    return " ".join(t.cells or []) if t.cells else t.text


def occurs(term, text):
    """Whole-word, case-insensitive match (so "rice" doesn't match "price")."""
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.I) is not None


def terms_for(block, lang, terms):
    """The glossary terms for `lang` that occur in the block's original."""
    return [t for t in terms if t.lang == lang and occurs(t.source, source_text(block))]


def misses(doc, lang, terms):
    """Translated sections whose source uses a pinned term but whose translation lacks its target."""
    out = []
    for page in doc.pages:
        for b in page.blocks:
            t = b.translations.get(lang)
            if not t or t.status == "error":
                continue
            missing = [x for x in terms_for(b, lang, terms) if x.target not in translated_text(t)]
            if missing:
                out.append(
                    {
                        "block_id": b.id,
                        "page": page.index,
                        "text": source_text(b)[:160],
                        "missing": [m.model_dump() for m in missing],
                    }
                )
    return out
