from civican.scraper.utils import fix_mojibake


def test_fix_mojibake_french_accents():
    assert fix_mojibake("cour supÃ©rieure") == "cour supérieure"
    assert fix_mojibake("AssemblÃ©e nationale") == "Assemblée nationale"
    assert fix_mojibake("dâ€™un dÃ©cret") == "d'un décret"


def test_fix_mojibake_quotes_and_dashes():
    assert fix_mojibake("â€“ and â€”") == "\u2013 and \u2014"
    assert fix_mojibake("â€œandâ€\x9d") == '"and"'


def test_fix_mojibake_clean_text():
    assert fix_mojibake("Normal text without mojibake") == "Normal text without mojibake"
    assert fix_mojibake("") == ""
