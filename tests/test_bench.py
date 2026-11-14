from bench.wer import corpus_wer, norm, wer


def test_wer_normalisation_and_maths():
    assert norm("हातपंप बंद आहे।") == ["हातपंप", "बंद", "आहे"]
    assert wer("a b c d", "a b c d") == 0.0
    assert wer("a b c d", "a x c") == 0.5                 # 1 substitution + 1 deletion over 4
    assert wer("", "") == 0.0 and wer("", "x") == 1.0
    assert wer("३ दिवस", "3 दिवस") == 0.0                   # Devanagari digits fold
    assert corpus_wer([("a b", "a b"), ("c d", "x d")]) == 0.25
