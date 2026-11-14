"""Every sentence the assistant speaks. Read-backs are templates, never LLM sentences.

Each rendered sentence is a `Say`: a normal string (the on-screen caption) that also carries
`.speech`, the version sent to Timbre. The speech version writes quantities as words, reads ticket
numbers one digit at a time, and marks pauses with catalog.PAUSE (the Timbre adapter turns that into
the <pauses> audio tag on timbre-v3.0, or a comma).

NATIVE-SPEAKER REVIEW REQUIRED before any pilot (docs/TESTING.md has the checklist).
'hinglish' is code-mixed Hindi written in Devanagari so Timbre (hi-IN) reads it naturally.
"""
from __future__ import annotations

import re

from ..config import settings
from ..gnani.catalog import PAUSE, pauses_as_commas
from ..nlp.spoken import digit_words, number_words


class Say(str):
    """A caption that also knows how it should be spoken."""
    speech: str

    def __new__(cls, display: str, speech: str | None = None):
        obj = super().__new__(cls, display)
        obj.speech = display if speech is None else speech
        return obj

    def __add__(self, other):
        return Say(str(self) + str(other), self.speech + getattr(other, "speech", str(other)))

    def __radd__(self, other):
        return Say(str(other) + str(self), getattr(other, "speech", str(other)) + self.speech)


def speech_of(x) -> str:
    return getattr(x, "speech", str(x))


def plain_speech(x) -> str:
    """Speech text for voices that do not understand audio tags (browser voice, captions)."""
    return pauses_as_commas(speech_of(x))


T: dict[str, dict[str, str]] = {
    "greet": {
        "mr": "नमस्कार, मी जल आवाज, एक एआय सहायक आहे. हा प्रायोगिक प्रकल्प आहे, सरकारी सेवा नाही. पाण्याची तक्रार नोंदवायची आहे. कोणत्या गावात आणि काय अडचण आहे, सांगा.",
        "hi": "नमस्ते, मैं जल आवाज़ हूँ, एक एआई सहायक। यह एक प्रायोगिक प्रोजेक्ट है, सरकारी सेवा नहीं। पानी की शिकायत दर्ज करनी है। किस गाँव में और क्या दिक्कत है, बताइए।",
        "hinglish": "नमस्ते, मैं जल आवाज़ हूँ, एक एआई असिस्टेंट। ये एक प्रायोगिक प्रोजेक्ट है, सरकारी सर्विस नहीं। आपके गाँव में पानी की क्या प्रॉब्लम है, बताइए।",
    },
    "ask_village": {"mr": "कोणत्या गावात?", "hi": "किस गाँव में?", "hinglish": "कौन से गाँव में?"},
    "ask_village_again": {"mr": "गावाचे नाव समजले नाही. गावाचे नाव आणि तालुका सांगा.",
                          "hi": "गाँव का नाम समझ नहीं आया। गाँव और तहसील का नाम बताइए।",
                          "hinglish": "गाँव का नाम क्लियर नहीं हुआ। गाँव और तहसील का नाम बताइए।"},
    "confirm_village": {"mr": "{village}, बरोबर? हो किंवा नाही सांगा.", "hi": "{village}, सही है? हाँ या नहीं बोलिए।",
                        "hinglish": "{village}, सही है? हाँ या नहीं बोलिए।"},
    "ask_source": {"mr": "हातपंप, नळ, विहीर की बोअरवेल?", "hi": "हैंडपंप, नल, कुआँ या बोरवेल?",
                   "hinglish": "हैंडपंप, नल, कुआँ या बोरवेल?"},
    "ask_fault": {"mr": "काय बिघाड आहे? पाणी नाही, कमी दाब, गळती की दूषित पाणी?",
                  "hi": "क्या खराबी है? पानी नहीं, कम दबाव, लीकेज या गंदा पानी?",
                  "hinglish": "क्या प्रॉब्लम है? पानी नहीं आ रहा, प्रेशर कम, लीकेज या गंदा पानी?"},
    "ask_duration": {"mr": "किती दिवस झाले?", "hi": "कितने दिन हो गए?", "hinglish": "कितने दिन से?"},
    "ask_households": {"mr": "किती घरांना फटका बसला आहे?", "hi": "कितने घर प्रभावित हैं?", "hinglish": "कितने घर अफेक्टेड हैं?"},
    "ask_drinking": {"mr": "हे पिण्याचे पाणी आहे का?", "hi": "क्या यह पीने का पानी है?", "hinglish": "क्या ये पीने का पानी है?"},
    "ask_symptoms": {"mr": "कोणाला पोटदुखी, जुलाब, उलट्या किंवा ताप आहे का?",
                     "hi": "क्या किसी को पेट दर्द, दस्त, उल्टी या बुखार है?",
                     "hinglish": "क्या किसी को पेट दर्द, दस्त, उल्टी या बुखार है?"},
    "readback_q": {"mr": "ही माहिती बरोबर आहे का? हो किंवा नाही सांगा.", "hi": "क्या यह सही है? हाँ या नहीं बोलिए।",
                   "hinglish": "क्या ये डिटेल्स सही हैं? हाँ या नहीं बोलिए।"},
    "yes_or_no": {"mr": "कृपया फक्त हो किंवा नाही सांगा.", "hi": "कृपया सिर्फ़ हाँ या नहीं बोलिए।",
                  "hinglish": "प्लीज़ सिर्फ़ हाँ या नहीं बोलिए।"},
    "which_wrong": {"mr": "काय चुकीचे आहे? योग्य माहिती पुन्हा सांगा.", "hi": "क्या गलत है? सही जानकारी फिर से बताइए।",
                    "hinglish": "क्या गलत है? सही डिटेल फिर से बताइए।"},
    "ticket": {"mr": "तुमची तक्रार नोंदवली आहे. तक्रार क्रमांक {digits}. पुन्हा सांगते, {digits}. इंजिनिअरला कळवले आहे. दुरुस्तीनंतर आम्ही तुम्हाला फोन करून खात्री करू.",
               "hi": "आपकी शिकायत दर्ज हो गई है। शिकायत क्रमांक {digits}। फिर से, {digits}। इंजीनियर को बता दिया गया है। मरम्मत के बाद हम आपको फ़ोन करके पक्का करेंगे।",
               "hinglish": "आपकी कंप्लेंट दर्ज हो गई है। कंप्लेंट नंबर {digits}। फिर से, {digits}। इंजीनियर को बता दिया है। रिपेयर के बाद हम कॉल करके कन्फर्म करेंगे।"},
    "no_hear": {"mr": "मला समजले नाही, पुन्हा सांगा.", "hi": "मुझे समझ नहीं आया, फिर से बताइए।",
                "hinglish": "समझ नहीं आया, प्लीज़ फिर से बोलिए।"},
    "handoff": {"mr": "माफ करा, मला पूर्ण माहिती मिळाली नाही. तक्रार नोंदवली नाही. एक व्यक्ती तुम्हाला फोन करेल.",
                "hi": "माफ़ कीजिए, पूरी जानकारी नहीं मिली। शिकायत दर्ज नहीं हुई। एक व्यक्ति आपको फ़ोन करेगा।",
                "hinglish": "सॉरी, पूरी डिटेल नहीं मिली। कंप्लेंट दर्ज नहीं हुई। एक व्यक्ति आपको कॉल करेगा।"},
    "verify": {"mr": "नमस्कार, मी जल आवाज, एक एआय सहायक बोलत आहे. तक्रार क्रमांक {digits}. {village} गावातील {source} आता चालू झाला आहे का? हो किंवा नाही सांगा.",
               "hi": "नमस्ते, मैं जल आवाज़, एक एआई सहायक बोल रही हूँ। शिकायत क्रमांक {digits}। क्या {village} गाँव का {source} अब चालू हो गया है? हाँ या नहीं बोलिए।",
               "hinglish": "नमस्ते, मैं जल आवाज़, एक एआई असिस्टेंट। कंप्लेंट नंबर {digits}। क्या {village} गाँव का {source} अब ठीक से चल रहा है? हाँ या नहीं बोलिए।"},
    "verified_thanks": {"mr": "धन्यवाद. पाणी सुरू झाल्याची नोंद केली. तक्रार बंद केली आहे.",
                        "hi": "धन्यवाद। पानी चालू होने की पुष्टि दर्ज हो गई। शिकायत बंद कर दी गई है।",
                        "hinglish": "थैंक यू। कन्फर्मेशन दर्ज हो गया। कंप्लेंट बंद कर दी गई है।"},
    "reopened": {"mr": "क्षमस्व. तक्रार पुन्हा उघडली आहे आणि प्राधान्य वाढवले आहे. इंजिनिअरला पुन्हा कळवले आहे.",
                 "hi": "क्षमा कीजिए। शिकायत फिर से खोली गई है और प्राथमिकता बढ़ा दी गई है। इंजीनियर को फिर से बताया गया है।",
                 "hinglish": "सॉरी। कंप्लेंट फिर से खोल दी गई है और प्रायोरिटी बढ़ा दी है।"},
    "verify_unclear": {"mr": "उत्तर समजले नाही. आम्ही नंतर पुन्हा फोन करू.", "hi": "जवाब समझ नहीं आया। हम बाद में फिर फ़ोन करेंगे।",
                       "hinglish": "जवाब क्लियर नहीं था। हम बाद में फिर कॉल करेंगे।"},
    "safety_line": {"mr": "पाणी उकळून प्या किंवा दुसरा स्रोत वापरा, आणि आरोग्य सेविकेला कळवा.",
                    "hi": "पानी उबालकर पिएँ या दूसरा स्रोत इस्तेमाल करें, और स्वास्थ्य कार्यकर्ता को बताइए।",
                    "hinglish": "पानी उबालकर पिएँ या दूसरा सोर्स इस्तेमाल करें, और आशा दीदी को बताइए।"},
}

LABELS = {
    "source": {"handpump": {"mr": "हातपंप", "hi": "हैंडपंप"}, "tap": {"mr": "नळ", "hi": "नल"},
               "well": {"mr": "विहीर", "hi": "कुआँ"}, "borewell": {"mr": "बोअरवेल", "hi": "बोरवेल"},
               "tank": {"mr": "टाकी", "hi": "टंकी"}, "tanker": {"mr": "टँकर", "hi": "टैंकर"},
               "other": {"mr": "पाण्याचा स्रोत", "hi": "पानी का स्रोत"}},
    "fault": {"no_water": {"mr": "पाणी येत नाही", "hi": "पानी नहीं आ रहा"},
              "low_pressure": {"mr": "कमी दाब", "hi": "कम दबाव"},
              "leakage": {"mr": "गळती", "hi": "लीकेज"},
              "contamination": {"mr": "दूषित पाणी", "hi": "गंदा पानी"},
              "broken_part": {"mr": "भाग तुटला आहे", "hi": "पुर्ज़ा टूटा है"},
              "power": {"mr": "वीज समस्या", "hi": "बिजली की समस्या"},
              "other": {"mr": "इतर अडचण", "hi": "दूसरी समस्या"}},
}


def L(lang: str) -> str:
    return lang if lang in ("mr", "hi", "hinglish") else "hi"


def t(key: str, lang: str, **kw) -> Say:
    row = T[key]
    s = row.get(L(lang)) or row["hi"]
    if not kw:
        return Say(s)
    return Say(s.format(**{k: str(v) for k, v in kw.items()}), s.format(**{k: speech_of(v) for k, v in kw.items()}))


def label(kind: str, value: str | None, lang: str) -> str:
    if not value:
        return ""
    l2 = "mr" if lang == "mr" else "hi"
    return LABELS[kind].get(value, LABELS[kind]["other"])[l2]


def spoken_village(report: dict, village_row: dict | None, lang: str) -> str:
    """Prefer a Devanagari spelling for Timbre; fall back to the canonical name."""
    if village_row:
        dev = [v for v in [village_row["name"], *village_row.get("variants", [])] if re.search(r"[ऀ-ॿ]", v)]
        if dev:
            return dev[0]
        return village_row["name"]
    return report.get("village") or ""


def digits(ref: str, lang: str = "hi") -> Say:
    """Ticket numbers: shown as '44712', spoken one digit at a time after a short pause."""
    ref = "".join(ch for ch in str(ref) if ch.isdigit())
    return Say(ref, f"{PAUSE} {digit_words(ref, lang)}")


def num(n, lang: str) -> Say:
    """Quantities: shown as digits, spoken as words (docs ask for numbers written as words)."""
    if n is None:
        return Say("")
    if settings.cfg.get("tts", {}).get("spell_numbers", True) and float(n) == int(n):
        return Say(str(int(n)), number_words(int(n), lang))
    return Say(str(n))


def readback(report: dict, village_name: str, lang: str) -> Say:
    lg = L(lang)
    src, flt = label("source", report.get("source_type"), lg), label("fault", report.get("fault"), lg)
    d, h, drink = report.get("duration_days"), report.get("households_affected"), report.get("drinking_source")
    sym = [s for s in report.get("health_symptoms") or [] if s != "none"]
    parts: list[Say] = []
    if lg == "mr":
        parts += [Say(f"{village_name} गावातील {src}"), Say(flt)]
        if d is not None:
            parts.append(num(d, lg) + " दिवसांपासून")
        if h is not None:
            parts.append(num(h, lg) + " घरांना फटका")
        if drink:
            parts.append(Say("पिण्याचे पाणी"))
        if sym:
            parts.append(Say("आरोग्य तक्रार नोंदवली"))
    else:
        parts += [Say(f"{village_name} गाँव का {src}"), Say(flt)]
        if d is not None:
            parts.append(num(d, lg) + " दिन से")
        if h is not None:
            parts.append(num(h, lg) + " घर प्रभावित")
        if drink:
            parts.append(Say("पीने का पानी"))
        if sym:
            parts.append(Say("सेहत की शिकायत दर्ज"))
    parts = [p for p in parts if str(p)]
    head = Say(", ".join(str(p) for p in parts), ", ".join(p.speech for p in parts))
    end = "." if lg == "mr" else "।"
    q = t("readback_q", lg)
    return Say(f"{head}{end} {q}", f"{head.speech}{end} {PAUSE} {q.speech}")


def needs_safety_line(report: dict) -> bool:
    sym = [s for s in report.get("health_symptoms") or [] if s != "none"]
    return bool(report.get("drinking_source")) and (bool(sym) or report.get("fault") == "contamination")


STATIC_KEYS = [k for k, row in T.items() if all("{" not in v for v in row.values())]
