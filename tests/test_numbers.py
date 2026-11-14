"""Number normaliser: 100+ curated phrase cases plus full 1..100 table round trips.

NATIVE-SPEAKER REVIEW WANTED: rows marked '# review' are spellings we are least sure about.
"""
import pytest

from app.nlp.numbers import HI_DEV, HI_ROMAN, MR_DEV, normalise, numbers_in, words_to_number

PHRASES = [
    # --- Hindi (romanised / Hinglish)
    ("pump 3 din se band hai", "pump 3 din se band hai"),
    ("teen din se pani nahi", "3 din se pani nahi"),
    ("pachas ghar", "50 ghar"),
    ("Pachaas gharon mein", "50 gharon mein"),
    ("pachattar ghar", "75 ghar"),
    ("ek sau bees ghar", "120 ghar"),
    ("dedh sau log", "150 log"),
    ("dhai din", "2.5 din"),
    ("adhai din", "2.5 din"),
    ("saade teen din", "3.5 din"),
    ("sava do din", "2.25 din"),
    ("paune teen din", "2.75 din"),
    ("do hazaar paanch sau", "2500"),
    ("ek lakh", "100000"),
    ("das din", "10 din"),
    ("bees ghar", "20 ghar"),
    ("chalis ghar", "40 ghar"),
    ("chaalees ghar", "40 ghar"),
    ("assi ghar", "80 ghar"),
    ("nabbe ghar", "90 ghar"),
    ("chaubis ghante", "24 ghante"),
    ("pandrah din", "15 din"),
    ("ikkis din", "21 din"),
    ("do teen din", "3 din"),                       # range -> higher value
    ("char paanch ghar", "5 ghar"),
    ("das bees ghar", "20 ghar"),
    ("tera ghar band hai", "tera ghar band hai"),   # "your", not 13
    ("kal se band hai", "kal se band hai"),
    ("ek hafte se", "1 hafte se"),
    ("sau ghar", "100 ghar"),
    ("paanch sau", "500"),
    ("do sau pachas", "250"),
    # --- English and mixes
    ("forty ghar", "40 ghar"),
    ("forty five houses", "45 houses"),
    ("twenty days", "20 days"),
    ("three days no water", "3 days no water"),
    ("one hundred families", "100 families"),
    ("two thousand people", "2000 people"),
    ("fifteen din se", "15 din se"),
    ("handpump number 3", "handpump number 3"),
    ("ninety nine", "99"),
    # --- Marathi romanised
    ("teen divas", "3 divas"),
    ("don divas", "2 divas"),
    ("paach divas", "5 divas"),
    ("pannas ghar", "50 ghar"),
    ("shambhar ghar", "100 ghar"),
    ("ekvis divas", "21 divas"),
    ("chalis ghar", "40 ghar"),
    ("daha divas", "10 divas"),
    ("pandhra divas", "15 divas"),
    ("athra ghar", "18 ghar"),          # review
    # --- Marathi Devanagari
    ("शिवापूर मध्ये हातपंप तीन दिवस बंद आहे", "शिवापूर मध्ये हातपंप 3 दिवस बंद आहे"),
    ("चाळीस घरे", "40 घरे"),
    ("चाळीसेक घरं", "40 घरं"),
    ("पन्नास घरांना फटका", "50 घरांना फटका"),
    ("दोनशे पन्नास घरे", "250 घरे"),
    ("तीनशे घरे", "300 घरे"),
    ("शंभर घरे", "100 घरे"),
    ("दीड दिवस", "1.5 दिवस"),
    ("अडीच दिवस", "2.5 दिवस"),
    ("साडे तीन दिवस", "3.5 दिवस"),
    ("पावणे तीन दिवस", "2.75 दिवस"),
    ("दहा दिवस", "10 दिवस"),
    ("पंधरा दिवस", "15 दिवस"),
    ("चार पाच घरे", "5 घरे"),
    ("एकवीस दिवस", "21 दिवस"),
    ("पंचवीस घरे", "25 घरे"),
    ("सत्तर घरे", "70 घरे"),
    ("ऐंशी घरे", "80 घरे"),
    ("नव्वद घरे", "90 घरे"),
    ("एक हजार लोक", "1000 लोक"),
    ("दोन दिवसांपासून", "2 दिवसांपासून"),
    ("पंच्याहत्तर घरे", "75 घरे"),     # review
    # --- Hindi Devanagari
    ("तीन दिन से पानी नहीं", "3 दिन से पानी नहीं"),
    ("पचास घर", "50 घर"),
    ("डेढ़ सौ घर", "150 घर"),
    ("ढाई दिन", "2.5 दिन"),
    ("साढ़े तीन दिन", "3.5 दिन"),
    ("सवा दो दिन", "2.25 दिन"),
    ("पौने तीन दिन", "2.75 दिन"),
    ("दो सौ घर", "200 घर"),
    ("पाँच दिन", "5 दिन"),
    ("पांच दिन", "5 दिन"),
    ("चालीस घर", "40 घर"),
    ("अड़तालीस घंटे", "48 घंटे"),
    ("अडतालीस घंटे", "48 घंटे"),
    ("तेरा घर", "तेरा घर"),               # "your house"
    ("दो तीन दिन", "3 दिन"),
    ("एक लाख", "100000"),
    ("बारह घर", "12 घर"),
    ("सौ घर", "100 घर"),
    # --- digits and Devanagari digits stay digits
    ("३ दिवस ४० घरे", "3 दिवस 40 घरे"),
    ("40 ghar 3 din", "40 ghar 3 din"),
    ("", ""),
    ("pump kharab hai", "pump kharab hai"),
    ("saath ghar", "60 ghar"),
    ("unchas ghar", "49 ghar"),
    ("chhappan ghar", "56 ghar"),
    ("बावीस घरे", "22 घरे"),
    ("अठ्ठावीस दिवस", "28 दिवस"),
    ("इक्कीस दिन", "21 दिन"),
    ("twenty one days", "21 days"),
]


@pytest.mark.parametrize("src,expected", PHRASES)
def test_phrases(src, expected):
    assert normalise(src) == expected


def test_case_count():
    assert len(PHRASES) >= 100


@pytest.mark.parametrize("table,name", [(HI_ROMAN, "hi_roman"), (HI_DEV, "hi_dev"), (MR_DEV, "mr_dev")])
def test_tables_round_trip(table, name):
    assert len(table) == 100
    bad = [(i, w) for i, w in enumerate(table, 1)
           if w not in ("तेरा",) and words_to_number(w) != i]
    assert not bad, f"{name}: {bad[:5]}"


@pytest.mark.parametrize("src,val", [
    ("saade teen", 3.5), ("dhai", 2.5), ("dedh", 1.5), ("pachas", 50), ("pachattar", 75), ("ekvis", 21),
    ("sau", 100), ("shambhar", 100), ("hazaar", 1000), ("lakh", 100000), ("ek sau ek", 101),
    ("40", 40), ("दोनशे", 200), ("seventy seven", 77),
])
def test_words_to_number(src, val):
    assert words_to_number(src) == val


def test_words_to_number_rejects_non_numbers():
    assert words_to_number("pani nahi") is None
    assert words_to_number("ek do") is None            # a range, not one number
    assert words_to_number("") is None


def test_numbers_in():
    assert numbers_in("teen din, chalis ghar") == [3.0, 40.0]
