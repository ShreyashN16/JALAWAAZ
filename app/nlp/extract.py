"""Complaint extraction: Evon (JSON) with a transparent rule-based fallback.

Pipeline per utterance: normalise numbers -> Evon (temperature 0, no reasoning trace) ->
strip fences / <think> -> json.loads -> retry once with "Return valid JSON only" -> on a second
failure (or no Evon) use rule_extract() and label the source. Then validators clean the result,
anti-hallucination guards drop numbers that are not in the transcript, and the new values merge
over the previous report (non-null wins). missing_fields is always recomputed in code.
"""
from __future__ import annotations

import json
import re
import time

from ..core.validators import clean, empty_report, missing
from .numbers import normalise, numbers_in
from .yesno import parse_yes_no

SYSTEM_PROMPT = """You extract water-fault reports from Indian phone-call transcripts
(Marathi, Hindi or Hinglish; the transcript may contain speech-recognition errors).
Return ONLY one JSON object with exactly these keys. No prose, no code fences.
{"village": null, "taluka": null, "district": null,
 "source_type": "handpump|tap|borewell|well|tanker|tank|other|null",
 "fault": "no_water|low_pressure|leakage|contamination|broken_part|power|other|null",
 "duration_days": null, "households_affected": null, "drinking_source": null,
 "health_symptoms": [], "smell_colour_taste": null, "language_detected": "mr|hi|hinglish",
 "evidence_quote": ""}
Rules:
- If a field is not clearly stated, set it to null. Never guess. Never invent a village or a number.
- Numbers in the transcript are already digits. Copy them; do not compute new ones.
- village: the place name exactly as spoken (without words like gaon, madhe, mein).
- health_symptoms: only symptoms the caller explicitly mentions, from
  diarrhoea, vomiting, fever, skin, stomach_pain; otherwise [].
- drinking_source: true only if the caller says people drink this water; false if they say they do not.
- If two problems are mentioned, put the main one in fault and the other in smell_colour_taste.
- evidence_quote: the shortest span of the transcript that supports the fault and village.
- Do not give advice. Do not diagnose.

Examples:
T: शिवापूर मध्ये हातपंप 3 दिवस बंद आहे, 40 घरांना पाणी नाही
J: {"village":"शिवापूर","taluka":null,"district":null,"source_type":"handpump","fault":"no_water","duration_days":3,"households_affected":40,"drinking_source":null,"health_symptoms":[],"smell_colour_taste":null,"language_detected":"mr","evidence_quote":"शिवापूर मध्ये हातपंप 3 दिवस बंद"}
T: pump kharab hai, 3 din se pani nahi aa raha
J: {"village":null,"taluka":null,"district":null,"source_type":"handpump","fault":"broken_part","duration_days":3,"households_affected":null,"drinking_source":null,"health_symptoms":[],"smell_colour_taste":null,"language_detected":"hinglish","evidence_quote":"pump kharab hai"}
T: Donje gaon mein nal se ganda paani aa raha hai, bachchon ko ulti aur dast ho rahe hain, hum yahi paani peete hain
J: {"village":"Donje","taluka":null,"district":null,"source_type":"tap","fault":"contamination","duration_days":null,"households_affected":null,"drinking_source":true,"health_symptoms":["vomiting","diarrhoea"],"smell_colour_taste":null,"language_detected":"hinglish","evidence_quote":"nal se ganda paani"}
T: विहिरीचे पाणी पिवळे झाले आहे आणि वास येतो, पोट दुखतंय, हेच पिण्याचे पाणी आहे
J: {"village":null,"taluka":null,"district":null,"source_type":"well","fault":"contamination","duration_days":null,"households_affected":null,"drinking_source":true,"health_symptoms":["stomach_pain"],"smell_colour_taste":"yellow colour, smell","language_detected":"mr","evidence_quote":"विहिरीचे पाणी पिवळे झाले"}
T: सिवापुर मधला बोअरवेल गळतोय आणि दाब पण कमी आहे
J: {"village":"सिवापुर","taluka":null,"district":null,"source_type":"borewell","fault":"leakage","duration_days":null,"households_affected":null,"drinking_source":null,"health_symptoms":[],"smell_colour_taste":"low pressure","language_detected":"mr","evidence_quote":"बोअरवेल गळतोय"}
T: गाँव की टंकी का मोटर जल गया, बिजली की दिक्कत है, 2 दिन से
J: {"village":null,"taluka":null,"district":null,"source_type":"tank","fault":"power","duration_days":2,"households_affected":null,"drinking_source":null,"health_symptoms":[],"smell_colour_taste":null,"language_detected":"hi","evidence_quote":"मोटर जल गया, बिजली की दिक्कत"}
"""

# ------------------------------------------------------------------ rule-based fallback
SOURCE_KW = [  # order matters: tanker before tank
    ("tanker", ["tanker", "टँकर", "टैंकर", "टेंकर"]),
    ("borewell", ["borewell", "bore well", "bore", "boring", "बोअरवेल", "बोरवेल", "बोअर", "बोर", "बोरिंग"]),
    ("handpump", ["handpump", "hand pump", "hatpump", "haatpump", "हातपंप", "हँडपंप", "हैंडपंप", "हैंड पंप", "हातपंपा"]),
    ("tank", ["tank", "tanki", "taaki", "taki", "टाकी", "टंकी", "टैंक", "टाकीचे"]),
    ("well", ["well", "vihir", "vihir", "kuan", "kuwa", "kuaan", "kuen", "विहीर", "विहिरी", "विहिरीचे", "कुआँ", "कुआं", "कुएं", "कुएँ", "कुँआ", "कुंआ", "कुआ"]),
    ("tap", ["tap", "nal", "nalka", "pipeline", "नळ", "नळाला", "नळाचे", "नल", "नलका", "पाइपलाइन", "पाईपलाईन"]),
    ("handpump", ["pump", "पंप"]),          # a bare "pump" in a village is usually the handpump; read-back confirms
]
FAULT_KW = [  # priority order: first match wins
    ("contamination", ["ganda", "gandha", "gadhul", "dirty", "contaminated", "smell", "badbu", "keede", "kide",
                       "गढूळ", "गदळ", "दूषित", "घाण", "वास", "पिवळे", "पिवळं", "गंदा", "गंदा", "बदबू", "मटमैला",
                       "कीड़े", "किडे", "dushit", "pivla", "matmaila"]),
    ("broken_part", ["kharab", "tuta", "tutla", "toota", "tootla", "broken", "bighadla", "handle", "khrab",
                     "खराब", "तुटला", "तुटले", "तुटलं", "टूटा", "टूट", "बिघडला", "बिघडले", "हँडल", "हैंडल"]),
    ("leakage", ["leak", "leakage", "galti", "riss", "tapak", "burst", "phutli", "phutla", "phat gaya", "phat gayi",
                 "गळती", "गळतोय", "गळते", "गळत", "फुटली", "फुटला", "फुटलं", "फुटले", "लीक", "लीकेज", "रिस", "टपक", "फट गया", "फट गई"]),
    ("low_pressure", ["kami dab", "kam dabav", "kam pressure", "low pressure", "pressure kam", "dhire", "dheere",
                      "pani kam", "paani kam", "pani kami", "कमी दाब", "दाब कमी", "कम दबाव", "दबाव कम", "हळू", "धीरे",
                      "पानी कम", "पाणी कमी", "कमी पाणी", "कम पानी"]),
    ("power", ["light nahi", "bijli", "vij", "power", "motor jali", "motor jal", "current nahi", "electricity",
               "वीज", "बिजली", "लाईट", "लाइट", "मोटर जळ", "मोटर जल"]),
    ("no_water", ["pani nahi", "paani nahi", "pani nai", "pani band", "band", "bandh", "no water", "not working",
                  "chalat nahi", "nahi aaya", "nahi aya", "aaya nahi", "nahi aa raha", "sukh gaya", "sookh gaya", "dry",
                  "पाणी नाही", "पानी नहीं", "पाणी येत नाही", "पानी नही", "बंद", "चालत नाही", "आला नाही", "आले नाही", "आलं नाही", "आलेलं नाही", "आलेले नाही",
                  "आली नाही", "नहीं आया", "नहीं आई", "नहीं आ रहा", "सूख गया", "सुकली", "आटली", "कोरडी"]),
]
SYMPTOM_KW = [
    ("diarrhoea", ["julab", "dast", "loose motion", "diarrhoea", "diarrhea", "जुलाब", "दस्त", "हगवण"]),
    ("vomiting", ["ulti", "ultya", "vomit", "vomiting", "उलटी", "उलट्या", "उल्टी", "उल्टियां"]),
    ("fever", ["taap", "bukhar", "fever", "ताप", "बुखार"]),
    ("skin", ["khaj", "khujli", "itching", "skin", "rash", "खाज", "खुजली", "चट्टे", "पुरळ"]),
    ("stomach_pain", ["pot dukh", "pet dard", "pot dukhtay", "stomach", "पोटदुखी", "पोट दुख", "पेट दर्द", "पेट में दर्द"]),
]
DRINK_KW = ["pinyache", "pinyacha", "piney", "pine ka", "peene", "peete", "pite", "drinking", "drink",
            "पिण्याचे", "पिण्याच्या", "पिण्याचं", "पितो", "पितात", "पीने", "पीते", "पिते", "पीने का"]
DAY_UNITS = r"(?:din|dino|dinon|divas|diwas|days?|दिवस\S*|दिन\S*)"
WEEK_UNITS = r"(?:hafte|hafta|hafton|aathavda|athavda|weeks?|हफ्ते|हफ़्ते|हफ्ता|आठवडा|आठवडे|आठवड्या\S*)"
MONTH_UNITS = r"(?:mahina|mahine|mahinya|months?|महिना|महिने|महिन्या\S*|महीना|महीने)"
HOUR_UNITS = r"(?:ghante|ghanta|hours?|ghanton|घंटे|घंटा|तास)"
HH_UNITS = r"(?:ghar|gharo|gharon|gharan|gharanna|houses?|homes?|families|family|kutumb|parivar|घर\S*|कुटुंब\S*|परिवार\S*)"
NUM = r"(\d+(?:\.\d+)?)"


def _has(text_l: str, kws: list[str]) -> bool:
    for k in kws:
        k = k.lower()
        if re.fullmatch(r"[a-z ]+", k):
            pat = r"(?<![a-z])" + re.escape(k) + r"(?:s|es)?(?![a-z])"
        else:                       # Devanagari: prefix match so suffixes (विहिरीचे, घरांना) still hit
            pat = r"(?<![ऀ-ॿ])" + re.escape(k)
        if re.search(pat, text_l):
            return True
    return False


def rule_extract(text: str, expecting: str | None = None) -> dict:
    t = normalise(text or "")
    tl = t.lower()
    r = empty_report()
    r["source_type"] = next((s for s, kws in SOURCE_KW if _has(tl, kws)), None)
    r["fault"] = next((f for f, kws in FAULT_KW if _has(tl, kws)), None)
    r["health_symptoms"] = [s for s, kws in SYMPTOM_KW if _has(tl, kws)]
    if _has(tl, DRINK_KW):
        r["drinking_source"] = not _has(tl, ["nahi", "nahin", "नाही", "नहीं", "nako", "not"])
    m = re.search(NUM + r"\s*" + DAY_UNITS, tl)
    if m:
        r["duration_days"] = float(m.group(1))
    elif (m := re.search(NUM + r"\s*" + WEEK_UNITS, tl)):
        r["duration_days"] = float(m.group(1)) * 7
    elif (m := re.search(NUM + r"\s*" + MONTH_UNITS, tl)):
        r["duration_days"] = float(m.group(1)) * 30
    elif (m := re.search(NUM + r"\s*" + HOUR_UNITS, tl)):
        r["duration_days"] = max(1.0, float(m.group(1)) / 24)
    elif _has(tl, ["kal se", "kal pasun", "कालपासून", "कल से", "since yesterday"]):
        r["duration_days"] = 1
    m = re.search(NUM + r"\s*" + HH_UNITS, tl)
    if m:
        r["households_affected"] = float(m.group(1))
    nums = numbers_in(t)
    if expecting == "duration_days" and r["duration_days"] is None and len(nums) == 1:
        r["duration_days"] = nums[0]
    if expecting == "households_affected" and r["households_affected"] is None and len(nums) == 1:
        r["households_affected"] = nums[0]
    if expecting == "drinking_source" and r["drinking_source"] is None:
        r["drinking_source"] = parse_yes_no(t)
    if expecting == "health_symptoms" and not r["health_symptoms"] and parse_yes_no(t) is False:
        r["health_symptoms"] = ["none"]
    if expecting == "village":
        r["village"] = t.strip(" .।?!")[:60] or None
    r["evidence_quote"] = t[:120]
    return r


# ------------------------------------------------------------------ JSON handling
FENCE = re.compile(r"^```(?:json)?|```$", re.M)


def parse_json(s: str) -> dict | None:
    if not s:
        return None
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.S)
    s = FENCE.sub("", s).strip()
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        obj = json.loads(s[a:b + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def detect_lang(text: str, stt_code: str | None, current: str) -> str:
    """mr / hi / hinglish from the first caller utterance."""
    t = text or ""
    dev = len(re.findall(r"[ऀ-ॿ]", t))
    lat = len(re.findall(r"[A-Za-z]", t))
    mr_markers = ["आहे", "नाही", "मध्ये", "झाले", "झाला", "दिवस", "घरे", "गावात", "पाणी", "आणि", "का?", "होय"]
    mr_roman = ["aahe", "ahe", "nahi aahe", "madhe", "divas", "jhala", "zala", "pani nahi aahe", "aani", "gavat"]
    if dev >= lat and dev:
        if any(m in t for m in mr_markers) or (stt_code or "").startswith("mr"):
            return "mr"
        return "hi"
    if lat:
        tl = t.lower()
        if any(re.search(r"\b" + re.escape(m) + r"\b", tl) for m in mr_roman):
            return "mr"
        if re.search(r"\b(hai|nahi|nahin|pani|paani|din|ghar|gaon|mein|ka|ki)\b", tl):
            return "hinglish"
    return current


def merge(prev: dict, new: dict) -> dict:
    out = dict(prev)
    for k, v in new.items():
        if k == "health_symptoms":
            vals = [x for x in dict.fromkeys((prev.get(k) or []) + (v or []))]
            if len(vals) > 1 and "none" in vals:
                vals.remove("none")
            out[k] = vals
        elif v is not None and v != "":
            out[k] = v
    return out


def _guard(obj: dict, text: str, prev: dict) -> tuple[dict, list[str]]:
    """Drop model numbers that are not in the transcript; flag unsupported evidence."""
    flags = []
    nums = numbers_in(text)
    for k in ("duration_days", "households_affected"):
        v = obj.get(k)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            obj[k] = None
            continue
        allowed = set(nums) | {n * 7 for n in nums} | {n * 30 for n in nums}
        if fv not in allowed and not (k == "duration_days" and fv == 1):
            obj[k] = None
            flags.append(f"dropped unsupported {k}={v}")
    ev = obj.get("evidence_quote")
    if ev and isinstance(ev, str) and ev[:20] not in normalise(text) and ev[:20] not in text:
        flags.append("evidence_quote not found in transcript")
    return obj, flags


async def extract(text: str, prev: dict | None, llm=None, expecting: str | None = None) -> tuple[dict, dict]:
    """Returns (merged_report, meta). meta: source, ms, flags, needs_review."""
    prev = prev or empty_report()
    t = normalise(text or "")
    meta = {"source": "rules", "ms": 0.0, "flags": [], "needs_review": False}
    obj = None
    if llm is not None and t.strip():
        user = f"Transcript: {t}"
        if expecting:
            user = f"The assistant just asked the caller about: {expecting}.\n" + user
        t0 = time.perf_counter()
        try:
            out = await llm.complete(SYSTEM_PROMPT, user, max_tokens=350)
            obj = parse_json(out)
            if obj is None:
                out = await llm.complete(SYSTEM_PROMPT + "\nReturn valid JSON only.", user, max_tokens=350)
                obj = parse_json(out)
            meta["source"] = "evon" if obj is not None else "evon-invalid-json→rules"
        except Exception as e:  # network, HTTP or parse: fall back, never crash the call
            meta["source"] = "evon-error→rules"
            meta["flags"].append(type(e).__name__)
        meta["ms"] = (time.perf_counter() - t0) * 1000
    if obj is None:
        obj = rule_extract(t, expecting)
        if meta["source"] != "rules":
            meta["needs_review"] = True
    else:
        obj, flags = _guard(obj, t, prev)
        meta["flags"] += flags
        # fill gaps the model left that the rules can see (e.g. a bare "40" answering a question)
        rules = rule_extract(t, expecting)
        for k in ("duration_days", "households_affected", "drinking_source"):
            if obj.get(k) is None and rules.get(k) is not None:
                obj[k] = rules[k]
        if expecting == "village" and not obj.get("village"):
            obj["village"] = rules.get("village")
    new = clean(obj)
    merged = clean(merge(prev, new))
    merged["_missing"] = missing(merged)
    return merged, meta
