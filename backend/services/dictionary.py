"""Offline English dictionary (WordNet via nltk). One-time setup:
uv run python -m nltk.downloader wordnet
"""

import re
from functools import cache

WORD = re.compile(r"^[A-Za-z][A-Za-z'\- ]{0,48}$")
POS_NAMES = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}


class DictionaryUnavailable(Exception):
    """The WordNet data isn't installed."""


@cache
def _wordnet():
    from nltk.corpus import wordnet

    try:
        wordnet.ensure_loaded()
    except LookupError as exc:
        raise DictionaryUnavailable("WordNet data is missing: run `uv run python -m nltk.downloader wordnet`") from exc
    return wordnet


def define(word, limit=8):
    """Senses of an English word or short phrase, looked up by its base form ("surveyed" → "survey").
    Returns None for input that isn't a word."""
    word = word.strip().strip('.,;:!?"“”‘’()[]').lower()
    if not WORD.match(word):
        return None
    wn = _wordnet()
    key = word.replace(" ", "_")
    synsets = list(wn.synsets(key))
    if not synsets and key.endswith("ly"):  # WordNet lacks many adverbs: "equivalently" → "equivalent"
        bases = (key[:-3] + "y",) if key.endswith("ily") else (key[:-2], key[:-2] + "le")  # "happily", "gently"
        key = next((k for k in bases if wn.synsets(k)), key)
        synsets = list(wn.synsets(key))
    lemma = key
    # An inflected word ("surveyed") also gets its base form's senses ("survey").
    for pos in ("v", "n", "a", "r"):
        base = wn.morphy(key, pos)
        if base and base != key:
            lemma = lemma if lemma != key else base
            synsets += [x for x in wn.synsets(base) if x not in synsets]
    senses = []
    for s in synsets[:limit]:
        synonyms = [l.name().replace("_", " ") for l in s.lemmas() if l.name().lower() != lemma][:5]
        senses.append(
            {
                "pos": POS_NAMES.get(s.pos(), s.pos()),
                "definition": s.definition(),
                "examples": s.examples()[:2],
                "synonyms": synonyms,
            }
        )
    return {"word": word, "lemma": lemma.replace("_", " "), "senses": senses}
