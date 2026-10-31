"""Target languages Bodhan's indic-translate accepts (bhb/bho are refused)."""

import re

LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "or": "Odia",
    "as": "Assamese",
    "ur": "Urdu",
    "ne": "Nepali",
    "sa": "Sanskrit",
    "kok": "Konkani",
    "mai": "Maithili",
    "doi": "Dogri",
    "brx": "Bodo",
    "sat": "Santali",
    "ks": "Kashmiri (Perso-Arabic)",
    "ks-Deva": "Kashmiri (Devanagari)",
    "mni": "Manipuri (Meitei)",
    "mni-Beng": "Manipuri (Bengali)",
    "sd": "Sindhi (Devanagari)",
    "sd-Arab": "Sindhi (Perso-Arabic)",
}

RTL = {"ur", "ks", "sd-Arab"}

# Unicode ranges of each target's script, for checking that output is really in that script.
_DEVANAGARI = [(0x0900, 0x097F), (0xA8E0, 0xA8FF)]
_ARABIC = [(0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)]
SCRIPT_RANGES = {
    **dict.fromkeys(["hi", "mr", "ne", "sa", "mai", "kok", "doi", "brx", "ks-Deva", "sd"], _DEVANAGARI),
    **dict.fromkeys(["bn", "as", "mni-Beng"], [(0x0980, 0x09FF)]),
    **dict.fromkeys(["ur", "ks", "sd-Arab"], _ARABIC),
    "pa": [(0x0A00, 0x0A7F)],
    "gu": [(0x0A80, 0x0AFF)],
    "or": [(0x0B00, 0x0B7F)],
    "ta": [(0x0B80, 0x0BFF)],
    "te": [(0x0C00, 0x0C7F)],
    "kn": [(0x0C80, 0x0CFF)],
    "ml": [(0x0D00, 0x0D7F)],
    "mni": [(0xABC0, 0xABFF)],
    "sat": [(0x1C50, 0x1C7F)],
    "en": [(0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F)],
}


def in_script_ratio(text, lang):
    """Share of letters (and Indic vowel signs) written in `lang`'s script; None if no letters."""
    ranges = SCRIPT_RANGES.get(lang)
    letters = [c for c in text if c.isalpha() or 0x0900 <= ord(c) <= 0x0DFF]
    if not ranges or not letters:
        return None
    return sum(any(a <= ord(c) <= b for a, b in ranges) for c in letters) / len(letters)


# ---------------------------------------------------------------- source language detection
# Script first (letters per Unicode range), then, where several languages share a script, their most common
# words. Words two candidates share are dropped (see _distinct), so only telling words count.

_SCRIPTS = {  # script -> the languages written in it: supported codes, or names of ones the app doesn't support
    "latin": ["en", "Spanish", "French", "German", "Portuguese", "Italian", "Dutch"],
    "devanagari": ["hi", "mr", "ne", "sa", "mai", "kok", "doi", "brx"],
    "bengali": ["bn", "as", "mni-Beng"],
    "arabic": ["ur", "sd-Arab", "ks", "Arabic", "Persian"],
    "gurmukhi": ["pa"],
    "gujarati": ["gu"],
    "oriya": ["or"],
    "tamil": ["ta"],
    "telugu": ["te"],
    "kannada": ["kn"],
    "malayalam": ["ml"],
    "meetei": ["mni"],
    "olchiki": ["sat"],
}
_SCRIPT_OF = {
    "latin": "en",
    "devanagari": "hi",
    "bengali": "bn",
    "arabic": "ur",
    "gurmukhi": "pa",
    "gujarati": "gu",
    "oriya": "or",
    "tamil": "ta",
    "telugu": "te",
    "kannada": "kn",
    "malayalam": "ml",
    "meetei": "mni",
    "olchiki": "sat",
}  # a code whose SCRIPT_RANGES cover the script
_PATTERNS = {
    s: re.compile("[" + "".join(f"\\u{a:04x}-\\u{b:04x}" for a, b in SCRIPT_RANGES[c]) + "]")
    for s, c in _SCRIPT_OF.items()
}

_WORDS = {
    "en": "the of and to in is that for it with as was on are by this be from or an at which not have were has its",
    "Spanish": "el la los las de del que y en un una por para con no es se su al lo como más pero sus le ya",
    "French": "le la les de des du et est un une que qui dans pour pas sur au aux avec ce sont par plus ne il",
    "German": "der die das und ist nicht ein eine zu den von mit sich des auf für im dem auch es an werden",
    "Portuguese": "o a os as de do da dos das que e em um uma para com não por se mais na no ao foi",
    "Italian": "il lo la gli le di del della che e è un una per con non sono nel alla anche si da",
    "Dutch": "de het een en van is dat op te zijn voor met niet aan er ook als bij door werd",
    "hi": "है हैं और के की का में से ने पर यह था थे थी लिए भी नहीं किया गया एक जो कि तो हुआ रहा अपने इस उन वह",
    "mr": "आहे आहेत आणि च्या चे ची हा ही हे या व मध्ये होते होता केले म्हणून असे नाही त्यांच्या त्याचे आपल्या",
    "ne": "छ छन् र मा ले हो थियो गरेको पनि भएको यो लागि गर्न हुन्छ थिए यस यसको उनको गरी भने",
    "sa": "अस्ति सन्ति इति च एव तु अपि वा अत्र तत्र सः सा तत् यत् भवति किम् अहम् त्वम् तस्य यथा",
    "mai": "अछि छल आ केर सँ मे एहि ओ छलाह जे कें हमर अहाँ छथि",
    "kok": "आसा आनी हें जाल्यार म्हूण ना आसले कडेन खातीर जावन आमी तांणी",
    "doi": "ऐ ते दा दी दे च कन्नै बी जेहड़ा नेईं होंदा इक",
    "brx": "आरो जों नि खौ आव जायो मोनसे दं बादि थांनाय जानाय",
    "bn": "এবং ও এই করে হয় থেকে জন্য সঙ্গে একটি যে না তার ছিল হয়েছে করা তিনি এর",
    "mni-Beng": "অমসুং অমা মসি অদু হায়রিবা লৈবা ওই দা গী বু",
    "ur": "ہے ہیں کے کی میں اور سے کا کو نے یہ تھا تھے لیے بھی نہیں",
    "sd-Arab": "۾ جو جي آهي ۽ کي جا تي هن ته آهن ٿو ٿي",
    "ks": "چھُ تہٕ منز ہٕنز چھِ یِم",
    "Arabic": "في من على إلى التي الذي أن هذا عن مع كان هذه ما لا",
    "Persian": "است در به از که این را با برای هم شد می",
}
_PUNCT = "".join(chr(c) for c in range(0x21, 0x40)) + "[]{}।॥،؛۔؟“”‘’«»—–…"


def _distinct():
    """Each script's candidates' word sets, minus the words another candidate of the same script also has."""
    out = {}
    for langs in _SCRIPTS.values():
        for lang in langs:
            others = set().union(*(set(_WORDS.get(o, "").split()) for o in langs if o != lang))
            out[lang] = set(_WORDS.get(lang, "").split()) - others
    return out


_DISTINCT = _distinct()
_LETTERS_ONLY = {
    "as": re.compile("[\u09f0\u09f1]"),  # ৰ ৱ: Assamese, not Bengali
    "sd-Arab": re.compile("[\u0684\u0683\u0687\u068f\u068c\u068a\u068d\u067b\u067d\u067a\u0680\u067f]"),
}


def detect_language(text):
    """(code, unsupported): the language `text` is written in, as a code of LANGUAGES when it's one the app
    supports, else the name of the language (or "an unsupported language") in `unsupported`. (None, None)
    when there's too little text, or when the script is shared and the words don't settle which language."""
    letters = sum(c.isalpha() for c in text)
    counts = {s: len(p.findall(text)) for s, p in _PATTERNS.items()}
    script = max(counts, key=counts.get)
    if letters < 20:
        return None, None
    if counts[script] < 0.5 * letters:  # mostly Cyrillic, Chinese, Greek, Thai...
        return None, "an unsupported language"
    langs = _SCRIPTS[script]
    if len(langs) == 1:
        return langs[0], None
    for lang, letters_only in _LETTERS_ONLY.items():
        if lang in langs and len(letters_only.findall(text)) >= 5:
            return lang, None
    tokens = [w.strip(_PUNCT).lower() for w in text.split()]
    tokens = [w for w in tokens if w]
    hits = {lang: sum(w in _DISTINCT[lang] for w in tokens) for lang in langs}
    ranked = sorted(hits, key=hits.get, reverse=True)
    best, second = ranked[0], hits[ranked[1]]
    if hits[best] < max(3, 0.02 * len(tokens)) or hits[best] < 2 * second:
        # Too few telling words: Latin text with almost no prose (tables, lists) is most likely English.
        return ("en", None) if script == "latin" and hits[best] < 3 else (None, None)
    return (best, None) if best in LANGUAGES else (None, best)
