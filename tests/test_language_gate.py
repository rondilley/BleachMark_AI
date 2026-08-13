"""Language-matched meaning gate (FR-27a).

Each language uses its own metric and a calibrated threshold. A Chinese pair
must not be scored as English words. A Spanish paraphrase must pass. An
unrelated sentence must fail.
"""

from bleachmark.bleach.gate import MeaningGate, spec_for
from bleachmark.bleach.language import detect_language
from bleachmark.bleach.meaning_calibrate import calibrate_language_thresholds


def test_detects_english_spanish_chinese_japanese_arabic():
    assert detect_language("The committee delayed the vote for the city.") == "en"
    assert detect_language("El comite decidio retrasar la votacion en la ciudad.") == "es"
    assert detect_language("北京今天天气很好。") == "zh"
    assert detect_language("今日は天気がとても良い。") == "ja"
    assert detect_language("القطة السوداء تنام في البيت الكبير.") == "ar"


def test_cjk_uses_character_metric_not_words():
    assert spec_for("zh")["metric"] == "char"
    assert spec_for("ja")["metric"] == "char"
    assert spec_for("en")["metric"] == "word_char"
    assert spec_for("es")["metric"] == "word_char"


def test_spanish_paraphrase_passes_and_unrelated_fails():
    gate = MeaningGate()
    a = "El gato negro duerme en la casa grande."
    para = "El gato oscuro duerme en la vivienda grande."
    other = "Los trenes salen de la estacion a las cinco."
    s_para = gate.similarity(a, para, language="es")
    s_other = gate.similarity(a, other, language="es")
    assert s_para > s_other
    assert gate.passes(s_para, language="es")
    assert not gate.passes(s_other, language="es")


def test_chinese_paraphrase_passes_and_unrelated_fails():
    gate = MeaningGate()
    a = "北京今天天气很好。"
    para = "北京今日天气不错。"
    other = "火车五点离开车站。"
    s_para = gate.similarity(a, para, language="zh")
    s_other = gate.similarity(a, other, language="zh")
    assert s_para > s_other
    assert gate.passes(s_para, language="zh")
    assert not gate.passes(s_other, language="zh")


def test_similarity_detects_language_when_none_given():
    gate = MeaningGate()
    zh = gate.similarity("北京今天天气很好。", "北京今日天气不错。")
    en = gate.similarity("The black cat sleeps in the large house.",
                         "The dark cat sleeps in the big house.")
    assert gate.passes(zh, language="zh")
    assert gate.passes(en, language="en")
    assert zh >= spec_for("zh")["threshold"]
    assert en >= spec_for("en")["threshold"]


def test_calibration_separates_every_bundled_language():
    cal = calibrate_language_thresholds(target_false_accept=0.0)
    for lang, row in cal.items():
        assert row["auc"] == 1.0, (lang, row)
        assert row["false_accept_rate"] == 0.0, (lang, row)
        assert row["true_accept_rate"] == 1.0, (lang, row)
        assert row["detected"] == lang, (lang, row)
        # the calibrated threshold is language-specific, not one English number
        assert row["threshold"] != 0.76
