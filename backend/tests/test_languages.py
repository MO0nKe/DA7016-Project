import pytest

from backend.core.languages import detect_language

SAMPLES = [
    (
        "This report summarises the results of the annual survey conducted in the district and the findings of the committee.",  # noqa: E501
        ("en", None),
    ),
    ("Gold certificates 11,037 Special drawing rights certificates 5,200 Coin 1,423 Loans Other loans", ("en", None)),
    (
        "El informe resume los resultados de la encuesta anual que se realizó en el distrito y las conclusiones del comité.",  # noqa: E501
        (None, "Spanish"),
    ),
    ("इस रिपोर्ट में ज़िले के ग्रामीण क्षेत्रों में स्वास्थ्य सेवाओं की स्थिति का सारांश दिया गया है और यह समिति के लिए है।", ("hi", None)),
    # Marathi and Nepali share Hindi's script: their own common words decide.
    (
        "महाराष्ट्र हे भारतातील एक राज्य आहे आणि मुंबई ही त्याची राजधानी आहे. या राज्याची भाषा मराठी आहे आणि लोकसंख्या मोठी आहे.",
        ("mr", None),
    ),
    (
        "नेपाल दक्षिण एसियामा अवस्थित एक देश हो। यसको राजधानी काठमाडौं हो र यहाँको भाषा नेपाली हो। यो देश हिमालयमा छ र पर्यटन पनि छ।",  # noqa: E501
        ("ne", None),
    ),
    # Assamese shares Bengali's script but has its own letters (ৰ, ৱ).
    ("অসম ভাৰতৰ উত্তৰ-পূৱ অঞ্চলৰ এখন ৰাজ্য। ইয়াৰ ৰাজধানী দিছপুৰ আৰু ইয়াৰ ভাষা অসমীয়া। ব্ৰহ্মপুত্ৰ নৈ ইয়াৰ মাজেৰে বৈ গৈছে।", ("as", None)),
    ("তাজমহল ভারতের উত্তর প্রদেশে আগ্রায় অবস্থিত একটি রাজকীয় সমাধি এবং এটি মুঘল সম্রাট শাহজাহানের তৈরি করা হয়েছে।", ("bn", None)),
    (
        "یہ رپورٹ ضلع کے دیہی علاقوں میں صحت کی خدمات کے بارے میں ہے اور اس میں کمیٹی کی سفارشات بھی شامل ہیں۔",
        ("ur", None),
    ),
    (
        "این گزارش درباره وضعیت خدمات بهداشتی در مناطق روستایی است و از نتایج آن برای برنامه ریزی استفاده می شود.",
        (None, "Persian"),
    ),
    (
        "Этот отчёт описывает результаты ежегодного опроса, проведённого в районе, и выводы комитета.",
        (None, "an unsupported language"),
    ),
    ("தாஜ் மகால் இந்தியாவிலுள்ள நினைவுச்சின்னங்களுள் உலக அதிசயங்களில் ஒன்றாகும்.", ("ta", None)),
    ("12 34 56", (None, None)),
]


@pytest.mark.parametrize("text,expected", SAMPLES)
def test_detects_the_source_language(text, expected):
    assert detect_language(text) == expected


def test_a_shared_script_without_telling_words_is_left_undecided():
    # Devanagari names and numbers only: Hindi, Marathi or Nepali? Don't guess (nothing gets greyed out).
    assert detect_language("राम श्याम मोहन सीता गीता १२३ ४५६ दिल्ली मुंबई कोलकाता चेन्नई पुणे") == (None, None)
