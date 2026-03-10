from xreporter.i18n import resolve_language


def test_resolve_explicit_language() -> None:
    assert resolve_language("zh") == "zh"
    assert resolve_language("en") == "en"


def test_resolve_auto_chinese() -> None:
    assert resolve_language("auto", locale_name="zh_CN") == "zh"


def test_resolve_auto_english_fallback() -> None:
    assert resolve_language("auto", locale_name="fr_FR") == "en"
