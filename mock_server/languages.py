"""Language codes accepted by Bodhan, and the Unicode script each one is written in."""

TRANSLATE_LANGS = {
    "as",
    "bn",
    "brx",
    "doi",
    "en",
    "gu",
    "hi",
    "kn",
    "kok",
    "ks",
    "ks-Deva",
    "mai",
    "ml",
    "mni",
    "mni-Beng",
    "mr",
    "ne",
    "or",
    "pa",
    "sa",
    "sat",
    "sd",
    "sd-Arab",
    "ta",
    "te",
    "ur",
}
TRANSLITERATE_LANGS = TRANSLATE_LANGS - {"en"}

# Codes that appear in Bodhan's speech list but are refused by translate.
REFUSED_LANGS = {"bhb": "Bhili", "bho": "Bhojpuri"}

LANG_SCRIPT = {
    **dict.fromkeys(["hi", "mr", "ne", "sa", "mai", "kok", "doi", "brx", "ks-Deva", "sd"], "devanagari"),
    **dict.fromkeys(["bn", "as", "mni-Beng"], "bengali"),
    **dict.fromkeys(["ur", "ks", "sd-Arab"], "arabic"),
    "pa": "gurmukhi",
    "gu": "gujarati",
    "or": "oriya",
    "ta": "tamil",
    "te": "telugu",
    "kn": "kannada",
    "ml": "malayalam",
    "mni": "meetei",
    "sat": "olchiki",
    "en": "latin",
}
