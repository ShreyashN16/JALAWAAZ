"""Spoken-number normaliser for Marathi, Hindi, Hinglish and English.

Prisma v3.0 with format=transcribe already writes most numbers as digits, so this is the
second line of defence: fractions and idioms (dedh, dhai, saade teen, sava, paune), Marathi
"दोनशे" style hundreds, numbers Prisma leaves as words, and format=verbatim output.

Design choices (documented in docs/decisions.md):
- Word ranges such as "do teen din" / "चार पाच घरे" collapse to the HIGHER value (conservative for priority).
- Fractions are kept as decimals ("3.5"); validators round durations UP.
- Hindi "tera"/"तेरा" (= "your") is deliberately not treated as Marathi 13.
Tables were written from standard number lists; a native speaker should review them (see tests).
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------- tables (1..100)
HI_ROMAN = """ek do teen char paanch chhah saat aath nau das gyarah barah terah chaudah pandrah solah satrah
atharah unnis bees ikkis bais teis chaubis pachchis chhabbis sattais athais untis tees iktis battis taintis
chauntis paintis chhattis saintis adtis untalis chalis iktalis bayalis taintalis chavalis paintalis chhiyalis
saintalis adtalis unchas pachas ikyavan bavan tirpan chauvan pachpan chhappan sattavan athavan unsath saath
iksath basath tirsath chaunsath painsath chhiyasath sadsath adsath unhattar sattar ikhattar bahattar tihattar
chauhattar pachhattar chhihattar sathattar athhattar unyasi assi ikyasi bayasi tirasi chaurasi pachasi
chhiyasi sattasi athasi navasi nabbe ikyanve banve tiranve chauranve pachanve chhiyanve sattanve athanve
ninyanve sau""".split()

HI_DEV = """एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस
इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस
सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास
पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ
सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी
इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पंचानवे
छियानवे सत्तानवे अट्ठानवे निन्यानवे सौ""".split()

MR_DEV = """एक दोन तीन चार पाच सहा सात आठ नऊ दहा अकरा बारा तेरा चौदा पंधरा सोळा सतरा अठरा एकोणीस वीस
एकवीस बावीस तेवीस चोवीस पंचवीस सव्वीस सत्तावीस अठ्ठावीस एकोणतीस तीस एकतीस बत्तीस तेहेतीस चौतीस पस्तीस
छत्तीस सदतीस अडतीस एकोणचाळीस चाळीस एक्केचाळीस बेचाळीस त्रेचाळीस चव्वेचाळीस पंचेचाळीस सेहेचाळीस
सत्तेचाळीस अठ्ठेचाळीस एकोणपन्नास पन्नास एक्कावन्न बावन्न त्रेपन्न चोपन्न पंचावन्न छप्पन्न सत्तावन्न
अठ्ठावन्न एकोणसाठ साठ एकसष्ठ बासष्ठ त्रेसष्ठ चौसष्ठ पासष्ठ सहासष्ठ सदुसष्ठ अडुसष्ठ एकोणसत्तर सत्तर
एक्काहत्तर बाहत्तर त्र्याहत्तर चौऱ्याहत्तर पंच्याहत्तर शहात्तर सत्त्याहत्तर अठ्ठ्याहत्तर एकोणऐंशी ऐंशी
एक्याऐंशी ब्याऐंशी त्र्याऐंशी चौऱ्याऐंशी पंच्याऐंशी शहाऐंशी सत्त्याऐंशी अठ्ठ्याऐंशी एकोणनव्वद नव्वद
एक्याण्णव ब्याण्णव त्र्याण्णव चौऱ्याण्णव पंच्याण्णव शहाण्णव सत्त्याण्णव अठ्ठ्याण्णव नव्व्याण्णव शंभर""".split()

MR_ROMAN = {
    "don": 2, "teen": 3, "paach": 5, "pach": 5, "saha": 6, "nav": 9, "daha": 10, "akra": 11, "bara": 12,
    "chauda": 14, "pandhra": 15, "sola": 16, "satra": 17, "athra": 18, "ekonis": 19, "vees": 20, "vis": 20,
    "ekvis": 21, "bavis": 22, "tevis": 23, "chovis": 24, "panchvis": 25, "savvis": 26, "sattavis": 27,
    "athavis": 28, "ekontis": 29, "chalis": 40, "challis": 40, "pannas": 50, "pachattar": 75, "aishi": 80,
    "aikshi": 80, "navvad": 90, "shambhar": 100, "shambar": 100,
}
EN = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
      "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
      "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
           "eighty": 80, "ninety": 90}
EXTRA = {"shunya": 0, "शून्य": 0, "sifar": 0, "chhe": 6, "chaar": 4, "das": 10, "nau": 9}
EXCLUDE = {"tera", "तेरा"}            # Hindi "your"; never a number in our transcripts

MULT = {"sau": 100, "sao": 100, "hundred": 100, "सौ": 100, "शंभर": 100, "shambhar": 100,
        "hazaar": 1000, "hazar": 1000, "hajar": 1000, "thousand": 1000, "हजार": 1000, "हज़ार": 1000,
        "lakh": 100000, "lac": 100000, "लाख": 100000}
FRACT = {"dedh": 1.5, "derh": 1.5, "डेढ़": 1.5, "डेढ": 1.5, "दीड": 1.5, "deed": 1.5, "did": 1.5,
         "dhai": 2.5, "adhai": 2.5, "dhaai": 2.5, "ढाई": 2.5, "अढाई": 2.5, "अडीच": 2.5, "adich": 2.5,
         "aadha": 0.5, "adha": 0.5, "आधा": 0.5, "अर्धा": 0.5, "ardha": 0.5}
MODS = {"saade": 0.5, "sade": 0.5, "saadhe": 0.5, "साढ़े": 0.5, "साढे": 0.5, "साडे": 0.5,
        "sava": 0.25, "savva": 0.25, "सवा": 0.25, "paune": -0.25, "पौने": -0.25, "पावणे": -0.25, "pavne": -0.25}


def canon(tok: str) -> str:
    """Spelling-tolerant key: 'Pachaas'->'pachas', 'chaleess'->'chalis', nukta and candrabindu folded."""
    t = unicodedata.normalize("NFC", tok.lower()).replace("‌", "").replace("‍", "")
    if re.match(r"^[a-z]+$", t):
        t = t.replace("ee", "i").replace("oo", "u").replace("w", "v")
        t = re.sub(r"(.)\1+", r"\1", t)
        return t
    t = t.replace("़", "").replace("ँ", "ं")          # nukta, candrabindu
    return t


UNITS: dict[str, int] = {}


def _add(word: str, val: int, table: dict) -> None:
    if word in EXCLUDE:
        return
    k = canon(word)
    if k in table and table[k] != val:
        raise ValueError(f"number table collision: {word!r} -> {val} vs {table[k]}")
    table[k] = val


for _i, _w in enumerate(HI_ROMAN, 1):
    _add(_w, _i, UNITS)
for _tbl in (HI_DEV, MR_DEV):
    assert len(_tbl) == 100, len(_tbl)
    for _i, _w in enumerate(_tbl, 1):
        _add(_w, _i, UNITS)
for _tbl in (MR_ROMAN, EN, EXTRA):
    for _w, _v in _tbl.items():
        _add(_w, _v, UNITS)
EN_TENS_C = {canon(k): v for k, v in EN_TENS.items()}
MULT_C = {canon(k): v for k, v in MULT.items()}
FRACT_C = {canon(k): v for k, v in FRACT.items()}
MODS_C = {canon(k): v for k, v in MODS.items()}
for _k in list(MULT_C):         # "sau"/"shambhar" are multipliers, not plain units
    UNITS.pop(_k, None)
UNITS.update({k: v for k, v in EN_TENS_C.items()})

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
TOKEN = re.compile(r"\d+(?:\.\d+)?|[A-Za-z]+|[ऀ-ॣॱ-ॿ‌‍]+")


def _kind(tok: str):
    k = canon(tok)
    if k in MODS_C:
        return "mod", MODS_C[k]
    if k in FRACT_C:
        return "frac", FRACT_C[k]
    if k in MULT_C:
        return "mult", MULT_C[k]
    if k in UNITS:
        return ("tens" if k in EN_TENS_C else "unit"), UNITS[k]
    # Marathi hundreds in one word: दोनशे, तीनशे, paachshe
    for suf in ("शे", "she"):
        if k.endswith(suf) and k[: -len(suf)] in UNITS and 1 <= UNITS[k[: -len(suf)]] <= 9:
            return "hundreds", UNITS[k[: -len(suf)]] * 100
    # approximate suffix: चाळीसेक / chalisek = "about forty"
    for suf in ("ेक", "ek"):
        base = k[: -len(suf)]
        if k.endswith(suf) and len(base) >= 2 and base in UNITS and UNITS[base] >= 10:
            return "unit", UNITS[base]
    return None


def _parse_run(toks: list[str]) -> tuple[float | None, int]:
    """Longest number at the start of toks -> (value, tokens consumed)."""
    total, cur, mod, used = 0.0, 0.0, 0.0, 0
    add_ok, add_limit, have = False, 0, False
    for t in toks:
        k = _kind(t)
        if k is None:
            break
        typ, val = k
        if typ == "mod":
            if have and cur:
                break
            mod = val
        elif typ == "frac":
            if cur and not add_ok:
                break
            cur, add_ok, have = cur + val, False, True
        elif typ in ("unit", "tens", "hundreds"):
            if not cur:
                cur = val + (mod if val >= 1 else 0)
                mod, have = 0.0, True
                add_ok, add_limit = (typ == "tens"), 10
                if typ == "hundreds":
                    add_ok, add_limit = True, 100
            elif add_ok and val < add_limit:
                cur += val
                add_ok = False
            else:
                break
        elif typ == "mult":
            if not have and not cur:
                cur = 1.0
            cur *= val
            have = True
            if val >= 1000:
                total, cur = total + cur, 0.0
                add_ok, add_limit = False, val
            else:
                add_ok, add_limit = True, 100
        used += 1
    if not have:
        return None, 0
    return total + cur, used


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def words_to_number(text_or_tokens) -> float | None:
    """Parse a phrase that is entirely a number ('saade teen', 'दोनशे पन्नास'); else None."""
    toks = TOKEN.findall(text_or_tokens) if isinstance(text_or_tokens, str) else list(text_or_tokens)
    if not toks:
        return None
    if len(toks) == 1 and re.fullmatch(r"\d+(?:\.\d+)?", toks[0].translate(_DEV_DIGITS)):
        return float(toks[0].translate(_DEV_DIGITS))
    v, used = _parse_run(toks)
    return v if used == len(toks) else None


def normalise(text: str) -> str:
    """Replace runs of number words with digits in place; digits already present are kept."""
    if not text:
        return text
    text = text.translate(_DEV_DIGITS)
    matches = list(TOKEN.finditer(text))
    words = [m.group() for m in matches]
    out, last, i = [], 0, 0
    prev_num: tuple[int, float] | None = None       # (index in out, value) of previous word-number
    while i < len(matches):
        v, used = _parse_run(words[i:])
        if v is not None and used:
            start, end = matches[i].start(), matches[i + used - 1].end()
            gap = text[last:start]
            if prev_num is not None and gap.strip(" -–,/") == "" and v > prev_num[1] and v - prev_num[1] <= 10:
                out[prev_num[0]] = _fmt(v)           # range "do teen" -> the higher value
                out.append("")
                prev_num = (prev_num[0], v)
            else:
                out.append(gap)
                out.append(_fmt(v))
                prev_num = (len(out) - 1, v)
            last = end
            i += used
        else:
            prev_num = None if matches[i].group().strip() else prev_num
            i += 1
    out.append(text[last:])
    return re.sub(r"[ \t]{2,}", " ", "".join(out)).strip()


def numbers_in(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", normalise(text))]
